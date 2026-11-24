"""Outbox, publicação no RabbitMQ e projeção CQRS de disponibilidade.

Fluxo: alteração de `saldos` + `outbox` na mesma transação -> publicador -> RabbitMQ ->
consumidor da projeção -> `disponibilidade` (com `inbox` e comparação de `estoqueVersion`).
"""
import json
import logging
import os
import threading
from uuid import UUID, uuid4

import pika
from pika.exceptions import AMQPError, NackError, UnroutableError
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, Field

from servicos.banco import BancoIndisponivel, conectar


BANCO = "ESTOQUE_DATABASE_URL"
EXCHANGE = "glico.eventos"
EXCHANGE_ERROS = "glico.eventos.erros"
FILA_PROJECAO = "estoque.projecao-disponibilidade"
FILA_ERROS = "estoque.projecao-disponibilidade.erros"
CONSUMIDOR = "projecao-disponibilidade"
log = logging.getLogger("uvicorn.error")
logging.getLogger("pika").setLevel(logging.CRITICAL)  # Quedas do broker já são registradas abaixo.


def registrar_evento(conexao, tipo: str, agregado_tipo: str, agregado_id, correlacao: UUID | None, saldo, extra: dict):
    """Grava o fato na Outbox, na transação que alterou o saldo, com o estado resultante completo."""
    payload = {
        "unidadeId": str(saldo["unidade_id"]), "itemId": str(saldo["item_id"]),
        "estoqueVersion": saldo["estoque_version"], "estoqueFisicoAtual": saldo["estoque_fisico_atual"],
        "quantidadeAlocada": saldo["quantidade_alocada"], "permiteReserva": saldo["permite_reserva"], **extra,
    }
    conexao.execute("""
        INSERT INTO outbox (event_id, event_type, event_version, aggregate_type, aggregate_id,
            correlation_id, occurred_at, payload)
        VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
    """, (uuid4(), tipo, agregado_tipo, str(agregado_id), correlacao or uuid4(), saldo["updated_at"], Jsonb(payload)))


def declarar(canal) -> None:
    canal.exchange_declare(EXCHANGE, "topic", durable=True)
    canal.exchange_declare(EXCHANGE_ERROS, "fanout", durable=True)
    canal.queue_declare(FILA_ERROS, durable=True)
    canal.queue_bind(FILA_ERROS, EXCHANGE_ERROS)
    canal.queue_declare(FILA_PROJECAO, durable=True, arguments={"x-dead-letter-exchange": EXCHANGE_ERROS})
    canal.queue_bind(FILA_PROJECAO, EXCHANGE, routing_key="estoque.#")


# --- Publicador ---

def publicar_pendentes(canal) -> int:
    with conectar(BANCO) as conexao:
        eventos = conexao.execute("""
            SELECT event_id, event_type, event_version, aggregate_type, aggregate_id, correlation_id,
                   causation_id, occurred_at, payload, attempts
            FROM outbox WHERE status = 'PENDENTE' AND next_retry_at <= now()
            ORDER BY created_at LIMIT 50
            FOR UPDATE SKIP LOCKED
        """).fetchall()
        for evento in eventos:
            envelope = {
                "eventId": str(evento["event_id"]), "eventType": evento["event_type"],
                "eventVersion": evento["event_version"], "occurredAt": evento["occurred_at"].isoformat(),
                "aggregateType": evento["aggregate_type"], "aggregateId": evento["aggregate_id"],
                "correlationId": str(evento["correlation_id"]),
                "causationId": str(evento["causation_id"]) if evento["causation_id"] else None,
                "payload": evento["payload"],
            }
            propriedades = pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                                message_id=envelope["eventId"])
            try:
                # mandatory + publisher confirms: sem rota ou sem confirmação, o evento continua pendente.
                canal.basic_publish(EXCHANGE, evento["event_type"], json.dumps(envelope).encode(),
                                    propriedades, mandatory=True)
            except (UnroutableError, NackError) as erro:
                conexao.execute("""
                    UPDATE outbox SET attempts = attempts + 1, last_error = %s,
                        next_retry_at = now() + make_interval(secs => %s)
                    WHERE event_id = %s
                """, (type(erro).__name__, min(2 ** evento["attempts"], 30), evento["event_id"]))
                continue
            conexao.execute("""
                UPDATE outbox SET status = 'PUBLICADO', published_at = now(), attempts = attempts + 1,
                    last_error = NULL
                WHERE event_id = %s
            """, (evento["event_id"],))
        return len(eventos)


def publicar(canal, parar: threading.Event) -> None:
    canal.confirm_delivery()
    while not parar.is_set():
        if publicar_pendentes(canal) == 0:
            canal.connection.process_data_events(time_limit=0.5)  # Espera mantendo os heartbeats.


# --- Projeção CQRS ---

class EstadoSaldo(BaseModel):
    unidadeId: UUID
    itemId: UUID
    estoqueVersion: int = Field(ge=0)
    estoqueFisicoAtual: int = Field(ge=0)
    quantidadeAlocada: int = Field(ge=0)
    permiteReserva: bool


class EventoEstoque(BaseModel):
    eventId: UUID
    eventType: str
    occurredAt: AwareDatetime
    payload: EstadoSaldo


def aplicar(corpo: bytes) -> bool:
    """Aplica o estado do evento. False = duplicata já processada (Inbox)."""
    evento = EventoEstoque.model_validate_json(corpo)
    estado = evento.payload
    with conectar(BANCO) as conexao:
        novo = conexao.execute("""
            INSERT INTO inbox (consumer, event_id, processed_at) VALUES (%s, %s, now())
            ON CONFLICT DO NOTHING RETURNING event_id
        """, (CONSUMIDOR, evento.eventId)).fetchone()
        if novo is None:
            return False
        # Só uma versão maior substitui o estado: duplicatas e eventos atrasados não regridem a leitura.
        conexao.execute("""
            INSERT INTO disponibilidade (unidade_id, item_id, estoque_fisico_atual, quantidade_alocada,
                permite_reserva, atualizado_em, estoque_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unidade_id, item_id) DO UPDATE SET
                estoque_fisico_atual = EXCLUDED.estoque_fisico_atual,
                quantidade_alocada = EXCLUDED.quantidade_alocada,
                permite_reserva = EXCLUDED.permite_reserva,
                atualizado_em = EXCLUDED.atualizado_em,
                estoque_version = EXCLUDED.estoque_version
            WHERE disponibilidade.estoque_version < EXCLUDED.estoque_version
        """, (estado.unidadeId, estado.itemId, estado.estoqueFisicoAtual, estado.quantidadeAlocada,
              estado.permiteReserva, evento.occurredAt, estado.estoqueVersion))
        return True


def consumir(canal, parar: threading.Event) -> None:
    canal.basic_qos(prefetch_count=10)
    for metodo, _propriedades, corpo in canal.consume(FILA_PROJECAO, inactivity_timeout=1):
        if parar.is_set():
            break
        if metodo is None:
            continue
        try:
            aplicar(corpo)
        except BancoIndisponivel:
            canal.basic_nack(metodo.delivery_tag, requeue=True)  # Falha transitória: tentar de novo.
            parar.wait(2)
            continue
        except Exception:
            # Evento inválido ou que viola o modelo: fica observável na fila de erros, sem confirmar sucesso.
            log.exception("Evento enviado à fila de erros da projeção")
            canal.basic_nack(metodo.delivery_tag, requeue=False)
            continue
        canal.basic_ack(metodo.delivery_tag)  # ACK só depois do commit.


# --- Execução em segundo plano ---

def rodar(nome: str, trabalho, parar: threading.Event) -> None:
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    while not parar.is_set():
        try:
            conexao = pika.BlockingConnection(pika.URLParameters(url))
            try:
                canal = conexao.channel()
                declarar(canal)
                log.info("%s conectado ao RabbitMQ", nome)
                trabalho(canal, parar)
            finally:
                if conexao.is_open:
                    conexao.close()
        except (AMQPError, OSError) as erro:
            log.warning("%s sem RabbitMQ (%s); nova tentativa em 3s", nome, type(erro).__name__)
        except Exception:
            log.exception("%s falhou; nova tentativa em 3s", nome)
        parar.wait(3)


def iniciar(parar: threading.Event) -> None:
    for nome, trabalho in (("publicador-outbox", publicar), ("projecao-disponibilidade", consumir)):
        threading.Thread(target=rodar, args=(nome, trabalho, parar), name=nome, daemon=True).start()
