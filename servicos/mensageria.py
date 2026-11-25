"""Publicação Outbox e consumo de eventos duráveis no RabbitMQ."""
import json
import logging
import os
import threading
from functools import partial

import pika
from pika.exceptions import AMQPError, NackError, UnroutableError
from psycopg.errors import DeadlockDetected, LockNotAvailable, SerializationFailure

from servicos.banco import BancoIndisponivel, conectar


EXCHANGE = "glico.eventos"
EXCHANGE_ERROS_RETIRADA = "glico.retirada.erros"
TIPO_RETIRADA = "retirada.concluida.v1"
FILAS_RETIRADA = {
    servico: f"{servico}.retirada-concluida"
    for servico in ("reservas", "estoque", "orquestrador")
}
log = logging.getLogger("uvicorn.error")
logging.getLogger("pika").setLevel(logging.CRITICAL)


def declarar_retiradas(canal):
    canal.exchange_declare(EXCHANGE, "topic", durable=True)
    canal.exchange_declare(EXCHANGE_ERROS_RETIRADA, "direct", durable=True)
    for fila in FILAS_RETIRADA.values():
        canal.queue_declare(f"{fila}.erros", durable=True)
        canal.queue_bind(f"{fila}.erros", EXCHANGE_ERROS_RETIRADA, routing_key=fila)
        canal.queue_declare(fila, durable=True, arguments={
            "x-dead-letter-exchange": EXCHANGE_ERROS_RETIRADA,
            "x-dead-letter-routing-key": fila,
        })
        canal.queue_bind(fila, EXCHANGE, routing_key=TIPO_RETIRADA)


def registrar_inbox(conexao, consumidor, evento_id) -> bool:
    return conexao.execute("""
        INSERT INTO inbox (consumer, event_id, processed_at) VALUES (%s, %s, now())
        ON CONFLICT DO NOTHING RETURNING event_id
    """, (consumidor, evento_id)).fetchone() is not None


def publicar_pendentes(canal, banco) -> int:
    with conectar(banco) as conexao:
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
                """, (type(erro).__name__, 2 ** min(evento["attempts"], 5), evento["event_id"]))
                continue
            conexao.execute("""
                UPDATE outbox SET status = 'PUBLICADO', published_at = now(), attempts = attempts + 1,
                    last_error = NULL
                WHERE event_id = %s
            """, (evento["event_id"],))
        return len(eventos)


def publicar(canal, parar: threading.Event, banco: str) -> None:
    canal.confirm_delivery()
    while not parar.is_set():
        if publicar_pendentes(canal, banco) == 0:
            canal.connection.process_data_events(time_limit=0.5)  # Espera mantendo os heartbeats.


def consumir(canal, parar: threading.Event, fila: str, aplicar) -> None:
    canal.basic_qos(prefetch_count=10)
    for metodo, _propriedades, corpo in canal.consume(fila, inactivity_timeout=1):
        if parar.is_set():
            break
        if metodo is None:
            continue
        try:
            aplicar(corpo)
        except (BancoIndisponivel, DeadlockDetected, LockNotAvailable, SerializationFailure):
            canal.basic_nack(metodo.delivery_tag, requeue=True)  # Falha transitória: tentar de novo.
            parar.wait(2)
            continue
        except Exception:
            # Evento inválido ou que viola o modelo: fica observável na fila de erros, sem confirmar sucesso.
            log.exception("Evento enviado à fila de erros de %s", fila)
            canal.basic_nack(metodo.delivery_tag, requeue=False)
            continue
        canal.basic_ack(metodo.delivery_tag)  # ACK só depois do commit.


def rodar(nome: str, declarar, trabalho, parar: threading.Event) -> None:
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    parametros = pika.URLParameters(url)
    parametros.blocked_connection_timeout = 10
    while not parar.is_set():
        try:
            conexao = pika.BlockingConnection(parametros)
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


def iniciar_trabalhador(nome, declarar, trabalho, parar):
    threading.Thread(target=rodar, args=(nome, declarar, trabalho, parar), name=nome, daemon=True).start()


def iniciar_publicador(banco, declarar, parar):
    iniciar_trabalhador(f"outbox:{banco}", declarar, partial(publicar, banco=banco), parar)


def iniciar_consumidor(fila, declarar, aplicar, parar):
    iniciar_trabalhador(fila, declarar, partial(consumir, fila=fila, aplicar=aplicar), parar)
