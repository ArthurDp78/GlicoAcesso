"""Executor das etapas da SAGA de confirmação.

Cada etapa é uma intenção durável (método, caminho, corpo e chave) gravada antes da chamada.
O executor trava a etapa e a execução (FOR UPDATE SKIP LOCKED), chama o participante e grava o
resultado e a próxima etapa na mesma transação. Resposta incerta repete o mesmo comando com backoff.
"""
import logging
import os
import threading

import httpx
from psycopg.types.json import Jsonb

from servicos.banco import conectar


BANCO = "ORQUESTRADOR_DATABASE_URL"
SERVICOS = {
    "reservas": ("RESERVAS_URL", "http://127.0.0.1:8004"),
    "estoque": ("ESTOQUE_URL", "http://127.0.0.1:8003"),
    "retiradas": ("RETIRADAS_URL", "http://127.0.0.1:8007"),
}
BACKOFF_MAXIMO = 30
log = logging.getLogger("uvicorn.error")


def nova_etapa(conexao, saga_id, etapa_id, destino, metodo, caminho, corpo=None, cabecalhos=None):
    comando = {"metodo": metodo, "caminho": caminho, "corpo": corpo, "cabecalhos": cabecalhos or {}}
    conexao.execute("""
        INSERT INTO saga_etapas (saga_id, etapa_id, operacao, destino, idempotency_key, estado_tecnico,
            dados_comando, proximo_retry_em, criada_em, atualizada_em)
        VALUES (%s, %s, %s, %s, %s, 'PENDENTE', %s, now(), now(), now())
    """, (saga_id, etapa_id, etapa_id, destino, f"{saga_id}:{etapa_id}", Jsonb(comando)))
    conexao.execute("""
        UPDATE saga_execucoes SET etapa_atual = %s, versao = versao + 1, atualizada_em = now() WHERE saga_id = %s
    """, (etapa_id, saga_id))


def mudar_estado(conexao, saga_id, estado, motivo=None, encerrar=False):
    conexao.execute("""
        UPDATE saga_execucoes SET estado = %s, motivo_encerramento = COALESCE(%s, motivo_encerramento),
            etapa_atual = CASE WHEN %s THEN NULL ELSE etapa_atual END,
            encerrada_em = CASE WHEN %s THEN now() ELSE encerrada_em END,
            versao = versao + 1, atualizada_em = now()
        WHERE saga_id = %s
    """, (estado, motivo, encerrar, encerrar, saga_id))


def avancar(conexao, etapa, status: int, corpo: dict) -> bool:
    """Decide a próxima etapa a partir de um resultado conclusivo. False = resultado não tratado (repetir)."""
    saga, reserva = etapa["saga_id"], etapa["reserva_id"]
    codigo = corpo.get("codigo")
    comando_saga = {"sagaId": str(saga)}
    cabecalho_saga = {"X-Saga-Id": str(saga)}

    def compensar(primeira: str):
        mudar_estado(conexao, saga, "COMPENSANDO", codigo)
        etapas[primeira]()

    etapas = {
        "FALHAR_CONFIRMACAO": lambda: nova_etapa(conexao, saga, "FALHAR_CONFIRMACAO", "reservas", "POST",
                                                 f"/internal/v1/reservas/{reserva}/falhar-confirmacao", comando_saga),
        "LIBERAR_ALOCACAO": lambda: nova_etapa(conexao, saga, "LIBERAR_ALOCACAO", "estoque", "DELETE",
                                               f"/internal/v1/alocacoes/{reserva}", None, cabecalho_saga),
        "CANCELAR_AUTORIZACAO": lambda: nova_etapa(conexao, saga, "CANCELAR_AUTORIZACAO", "retiradas", "POST",
                                                   f"/internal/v1/autorizacoes/{reserva}/cancelar", None, cabecalho_saga),
    }
    match etapa["etapa_id"], status, codigo:
        case "ACEITAR_RESERVA", 200, _:
            dados = {"sagaId": str(saga), "reservaId": str(reserva), "unidadeId": corpo["unidadeId"],
                     "itemId": corpo["itemId"], "quantidade": corpo["quantidade"]}
            nova_etapa(conexao, saga, "ALOCAR_ESTOQUE", "estoque", "POST", "/internal/v1/alocacoes", dados)
        case ("ACEITAR_RESERVA", 403 | 404, _) | ("ACEITAR_RESERVA", 409, "ESTADO_INCOMPATIVEL"):
            # Aceite recusado sem efeitos distribuídos: nada a compensar.
            mudar_estado(conexao, saga, "INTERROMPIDA", codigo or f"HTTP_{status}", encerrar=True)
        case "ALOCAR_ESTOQUE", 201, _:
            nova_etapa(conexao, saga, "PREPARAR_AUTORIZACAO", "retiradas", "POST", "/internal/v1/autorizacoes",
                       etapa["dados_comando"]["corpo"])
        case ("ALOCAR_ESTOQUE", 404, _) | ("ALOCAR_ESTOQUE", 409, "SALDO_INSUFICIENTE" | "RESERVA_NAO_PERMITIDA"):
            compensar("FALHAR_CONFIRMACAO")  # Nada foi alocado.
        case "PREPARAR_AUTORIZACAO", 201, _:
            nova_etapa(conexao, saga, "CONFIRMAR_RESERVA", "reservas", "POST",
                       f"/internal/v1/reservas/{reserva}/confirmar", comando_saga)
        case "PREPARAR_AUTORIZACAO", 422, "AUTORIZACAO_NAO_CRIADA":
            compensar("LIBERAR_ALOCACAO")  # Prova de que não há autorização: só liberar.
        case ("PREPARAR_AUTORIZACAO", 409, "AUTORIZACAO_INCOMPATIVEL") | ("CONFIRMAR_RESERVA", 409, "ESTADO_INCOMPATIVEL"):
            compensar("CANCELAR_AUTORIZACAO")  # A autorização pode existir: revogar antes de liberar.
        case "CONFIRMAR_RESERVA", 200, _:
            mudar_estado(conexao, saga, "CONCLUIDA", encerrar=True)
        case ("CANCELAR_AUTORIZACAO", 200, _) | ("CANCELAR_AUTORIZACAO", 404, "AUTORIZACAO_NAO_ENCONTRADA"):
            etapas["LIBERAR_ALOCACAO"]()
        case "LIBERAR_ALOCACAO", 204, _:
            etapas["FALHAR_CONFIRMACAO"]()
        case "FALHAR_CONFIRMACAO", 200, _:
            mudar_estado(conexao, saga, "COMPENSADA", encerrar=True)
        case _:
            return False
    return True


def chamar(cliente: httpx.Client, etapa) -> tuple[int | None, dict, str | None]:
    comando = etapa["dados_comando"]
    variavel, padrao = SERVICOS[etapa["destino"]]
    cabecalhos = {
        "Authorization": "Bearer " + os.environ.get("GLICO_ORQUESTRADOR_SERVICE_TOKEN", ""),
        "Idempotency-Key": etapa["idempotency_key"],
        "X-Correlation-Id": str(etapa["correlation_id"]),
        **comando["cabecalhos"],
    }
    try:
        resposta = cliente.request(comando["metodo"], os.environ.get(variavel, padrao).rstrip("/") + comando["caminho"],
                                   json=comando["corpo"], headers=cabecalhos)
    except httpx.HTTPError as erro:
        return None, {}, f"{type(erro).__name__}: resultado incerto"
    if resposta.status_code >= 500 or resposta.status_code == 401:
        return None, {}, f"HTTP {resposta.status_code}"
    try:
        corpo = resposta.json() if resposta.content else {}
    except ValueError:
        corpo = {}
    return resposta.status_code, corpo if isinstance(corpo, dict) else {}, None


def executar_uma(cliente: httpx.Client) -> bool:
    with conectar(BANCO) as conexao:
        etapa = conexao.execute("""
            SELECT e.saga_id, e.etapa_id, e.destino, e.idempotency_key, e.dados_comando, e.tentativas,
                   s.reserva_id, s.correlation_id, s.estado
            FROM saga_etapas e JOIN saga_execucoes s USING (saga_id)
            WHERE e.estado_tecnico = 'PENDENTE' AND e.proximo_retry_em <= now()
            ORDER BY e.proximo_retry_em
            LIMIT 1
            FOR UPDATE OF e, s SKIP LOCKED
        """).fetchone()
        if etapa is None:
            return False
        # A chamada ocorre com a etapa travada: só este trabalhador decide o passo seguinte.
        try:
            status, corpo, erro = chamar(cliente, etapa)
            with conexao.transaction():  # Decisão parcial é desfeita; a etapa só recebe backoff.
                tratado = status is not None and avancar(conexao, etapa, status, corpo)
        except Exception as falha:
            log.exception("SAGA %s: erro ao processar %s", etapa["saga_id"], etapa["etapa_id"])
            status, corpo, erro, tratado = None, {}, f"{type(falha).__name__}: {falha}", False
        if tratado:
            conexao.execute("""
                UPDATE saga_etapas SET estado_tecnico = %s, resultado = %s, tentativas = tentativas + 1,
                    ultima_tentativa_em = now(), proximo_retry_em = NULL, erro_tecnico = NULL, atualizada_em = now()
                WHERE saga_id = %s AND etapa_id = %s
            """, ("CONCLUIDA" if status < 300 else "FALHOU", Jsonb({"status": status, "corpo": corpo}),
                  etapa["saga_id"], etapa["etapa_id"]))
            conexao.execute("""
                UPDATE saga_execucoes SET estado = 'COMPENSANDO' WHERE saga_id = %s AND estado = 'COMPENSACAO_PENDENTE'
            """, (etapa["saga_id"],))
            log.info("SAGA %s: %s -> HTTP %s", etapa["saga_id"], etapa["etapa_id"], status)
            return True
        espera = min(2 ** etapa["tentativas"], BACKOFF_MAXIMO)
        erro = erro or f"HTTP {status} {corpo.get('codigo', '')} sem tratamento conclusivo".strip()
        conexao.execute("""
            UPDATE saga_etapas SET tentativas = tentativas + 1, ultima_tentativa_em = now(),
                proximo_retry_em = now() + make_interval(secs => %s), erro_tecnico = %s, atualizada_em = now()
            WHERE saga_id = %s AND etapa_id = %s
        """, (espera, erro[:500], etapa["saga_id"], etapa["etapa_id"]))
        if etapa["estado"] == "COMPENSANDO":
            mudar_estado(conexao, etapa["saga_id"], "COMPENSACAO_PENDENTE")
        log.warning("SAGA %s: %s nova tentativa em %ss (%s)", etapa["saga_id"], etapa["etapa_id"], espera, erro)
        return True


def laco(parar: threading.Event) -> None:
    with httpx.Client(timeout=4.0, trust_env=False) as cliente:
        while not parar.is_set():
            try:
                trabalhou = executar_uma(cliente)
            except Exception:  # O laço não pode morrer: a etapa continua pendente e será retomada.
                log.exception("Falha no executor da SAGA")
                trabalhou = False
            if not trabalhou:
                parar.wait(0.5)
