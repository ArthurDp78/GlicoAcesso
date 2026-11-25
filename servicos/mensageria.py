"""Topologia do RabbitMQ, publicação da Outbox e consumo com Inbox, comuns aos serviços."""
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
from servicos.comandos import INTEIRO_MAXIMO


EXCHANGE = "glico.eventos"
EXCHANGE_ERROS = "glico.eventos.erros"
FILA_PROJECAO = "estoque.projecao-disponibilidade"
RETIRADA_CONCLUIDA = "retirada.concluida.v1"
FILA_RETIRADA_ESTOQUE = "estoque.baixa-retirada"
FILA_RETIRADA_RESERVAS = "reservas.retirada-concluida"
FILA_RETIRADA_ORQUESTRADOR = "orquestrador.retirada-concluida"
FILAS_RETIRADA = (FILA_RETIRADA_ESTOQUE, FILA_RETIRADA_RESERVAS, FILA_RETIRADA_ORQUESTRADOR)
log = logging.getLogger("uvicorn.error")
logging.getLogger("pika").setLevel(logging.CRITICAL)  # Quedas do broker já são registradas abaixo.


def fila_de_erros(fila: str) -> str:
    return fila + ".erros"


def todas_as_filas() -> list[str]:
    filas = [FILA_PROJECAO, *FILAS_RETIRADA]
    return filas + [fila_de_erros(fila) for fila in filas]


def declarar(canal) -> None:
    """Declara todos os vínculos: um produtor nunca publica antes de existirem as filas dos consumidores."""
    canal.exchange_declare(EXCHANGE, "topic", durable=True)
    canal.exchange_declare(EXCHANGE_ERROS, "fanout", durable=True)
    canal.queue_declare(fila_de_erros(FILA_PROJECAO), durable=True)
    canal.queue_bind(fila_de_erros(FILA_PROJECAO), EXCHANGE_ERROS)
    canal.queue_declare(FILA_PROJECAO, durable=True, arguments={"x-dead-letter-exchange": EXCHANGE_ERROS})
    canal.queue_bind(FILA_PROJECAO, EXCHANGE, routing_key="estoque.#")
    for fila in FILAS_RETIRADA:
        canal.queue_declare(fila_de_erros(fila), durable=True)
        canal.queue_declare(fila, durable=True, arguments={
            "x-dead-letter-exchange": "", "x-dead-letter-routing-key": fila_de_erros(fila)})
        canal.queue_bind(fila, EXCHANGE, routing_key=RETIRADA_CONCLUIDA)


# --- Outbox ---

def gravar_outbox(conexao, tipo: str, agregado_tipo: str, agregado_id, correlacao: UUID | None, ocorrido_em,
                  payload: dict, causacao: UUID | None = None) -> None:
    """Grava o fato na mesma transação da alteração de negócio."""
    conexao.execute("""
        INSERT INTO outbox (event_id, event_type, event_version, aggregate_type, aggregate_id,
            correlation_id, causation_id, occurred_at, payload)
        VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s)
    """, (uuid4(), tipo, agregado_tipo, str(agregado_id), correlacao or uuid4(), causacao, ocorrido_em, Jsonb(payload)))


def reservar_pendente(banco: str):
    """Registra o início da tentativa e adia a próxima antes de publicar; uma queda deixa o evento recuperável."""
    with conectar(banco) as conexao:
        return conexao.execute("""
            UPDATE outbox SET attempts = attempts + 1,
                next_retry_at = now() + make_interval(secs => least(power(2, least(attempts, 5)), 30))
            WHERE event_id = (
                SELECT event_id FROM outbox WHERE status = 'PENDENTE' AND next_retry_at <= now()
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            RETURNING event_id, event_type, event_version, aggregate_type, aggregate_id, correlation_id,
                causation_id, occurred_at, payload
        """).fetchone()


def publicar_pendentes(banco: str, canal, limite: int = 50) -> int:
    tentados = 0
    while tentados < limite and (evento := reservar_pendente(banco)) is not None:
        tentados += 1
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
        except (AMQPError, OSError) as erro:
            with conectar(banco) as conexao:
                conexao.execute("UPDATE outbox SET last_error = %s WHERE event_id = %s",
                                (type(erro).__name__, evento["event_id"]))
            if isinstance(erro, (UnroutableError, NackError)):
                continue
            raise  # Conexão perdida: o laço reconecta e o evento já está adiado.
        with conectar(banco) as conexao:
            conexao.execute("""
                UPDATE outbox SET status = 'PUBLICADO', published_at = now(), last_error = NULL
                WHERE event_id = %s AND status = 'PENDENTE'
            """, (evento["event_id"],))
    return tentados


def publicador(banco: str):
    def publicar(canal, parar: threading.Event) -> None:
        canal.confirm_delivery()
        while not parar.is_set():
            if publicar_pendentes(banco, canal) == 0:
                canal.connection.process_data_events(time_limit=0.5)  # Espera mantendo os heartbeats.
    return publicar


# --- Inbox e consumo ---

class DadosRetirada(BaseModel):
    retiradaId: UUID
    reservaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: int = Field(strict=True, ge=1, le=INTEIRO_MAXIMO)


class EventoRetirada(BaseModel):
    eventId: UUID
    eventType: str = Field(pattern=r"^retirada\.concluida\.v1$")
    occurredAt: AwareDatetime
    correlationId: UUID
    payload: DadosRetirada


def registrar_inbox(conexao, consumidor: str, event_id: UUID) -> bool:
    """False = evento já processado por este consumidor."""
    return conexao.execute("""
        INSERT INTO inbox (consumer, event_id, processed_at) VALUES (%s, %s, now())
        ON CONFLICT DO NOTHING RETURNING event_id
    """, (consumidor, event_id)).fetchone() is not None


def consumidor(fila: str, processar):
    def consumir(canal, parar: threading.Event) -> None:
        canal.basic_qos(prefetch_count=10)
        for metodo, _propriedades, corpo in canal.consume(fila, inactivity_timeout=1):
            if parar.is_set():
                break
            if metodo is None:
                continue
            try:
                processar(corpo)
            except BancoIndisponivel:
                canal.basic_nack(metodo.delivery_tag, requeue=True)  # Falha transitória: tentar de novo.
                parar.wait(2)
                continue
            except Exception:
                # Evento inválido ou divergente: fica observável na fila de erros, sem confirmar sucesso.
                log.exception("Evento enviado à fila de erros de %s", fila)
                canal.basic_nack(metodo.delivery_tag, requeue=False)
                continue
            canal.basic_ack(metodo.delivery_tag)  # ACK só depois do commit.
    return consumir


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


def iniciar(trabalhos: dict, parar: threading.Event) -> None:
    for nome, trabalho in trabalhos.items():
        threading.Thread(target=rodar, args=(nome, trabalho, parar), name=nome, daemon=True).start()
