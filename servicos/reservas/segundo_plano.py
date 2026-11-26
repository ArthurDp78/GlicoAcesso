"""Expiração por prazo e consumo de `retirada.concluida.v1`."""
import logging
import os
import threading

from servicos import mensageria
from servicos.banco import BancoIndisponivel, conectar
from servicos.reservas.transicoes import transicionar


BANCO = "RESERVAS_DATABASE_URL"
CONSUMIDOR = "retirada-concluida"
log = logging.getLogger("uvicorn.error")


def expirar_vencidas() -> int:
    """Expira um lote de SOLICITADA vencidas; a trava e o estado condicional disputam com as decisões."""
    with conectar(BANCO) as conexao:
        vencidas = conexao.execute("""
            SELECT reserva_id FROM reservas
            WHERE status = 'SOLICITADA' AND decisao_ate <= now()
            ORDER BY decisao_ate LIMIT 100
            FOR UPDATE SKIP LOCKED
        """).fetchall()
        for linha in vencidas:
            transicionar(conexao, linha["reserva_id"], "SOLICITADA", "EXPIRADA", motivo="PRAZO_DECISAO_VENCIDO")
        return len(vencidas)


def laco_expiracao(parar: threading.Event) -> None:
    intervalo = float(os.environ.get("GLICO_EXPIRACAO_INTERVALO", "5"))
    while not parar.is_set():
        try:
            if expirar_vencidas() > 0:
                continue
        except BancoIndisponivel as erro:
            log.warning("Expiração adiada: %s", erro)
        except Exception:
            log.exception("Falha na expiração de reservas")
        parar.wait(intervalo)


class RetiradaInesperada(RuntimeError):
    """A reserva não está em um estado que admita a retirada: exige reconciliação."""


def processar_retirada(corpo: bytes) -> bool:
    """False = duplicata. Inbox, transição e auditoria são confirmadas juntas."""
    evento = mensageria.EventoRetirada.model_validate_json(corpo)
    dados = evento.payload
    with conectar(BANCO) as conexao:
        if not mensageria.registrar_inbox(conexao, CONSUMIDOR, evento.eventId):
            return False
        reserva = conexao.execute("SELECT status FROM reservas WHERE reserva_id = %s FOR UPDATE",
                                  (dados.reservaId,)).fetchone()
        if reserva is None:
            raise RetiradaInesperada(f"Reserva {dados.reservaId} inexistente")
        if reserva["status"] == "RETIRADA":
            return True
        if reserva["status"] not in ("CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO"):
            raise RetiradaInesperada(f"Reserva {dados.reservaId} está {reserva['status']}")
        transicionar(conexao, dados.reservaId, reserva["status"], "RETIRADA", motivo="RETIRADA_CONCLUIDA",
                     event_id=evento.eventId, retirada_id=dados.retiradaId)
        return True


def iniciar(parar: threading.Event) -> None:
    threading.Thread(target=laco_expiracao, args=(parar,), name="expiracao-reservas", daemon=True).start()
    mensageria.iniciar({
        "retirada-reservas": mensageria.consumidor(mensageria.FILA_RETIRADA_RESERVAS, processar_retirada),
    }, parar)
