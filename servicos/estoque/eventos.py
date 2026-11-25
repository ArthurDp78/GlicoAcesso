"""Eventos de Estoque e projeção CQRS de disponibilidade."""
import threading
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, Field

from servicos.banco import conectar
from servicos.mensageria import EXCHANGE, iniciar_consumidor, iniciar_publicador

BANCO = "ESTOQUE_DATABASE_URL"
EXCHANGE_ERROS = "glico.eventos.erros"
FILA_PROJECAO = "estoque.projecao-disponibilidade"
FILA_ERROS = "estoque.projecao-disponibilidade.erros"
CONSUMIDOR = "projecao-disponibilidade"


def registrar_evento(conexao, tipo: str, agregado_tipo: str, agregado_id, correlacao: UUID | None, saldo, extra: dict, *, causacao: UUID | None = None):
    """Grava o fato na Outbox, na transação que alterou o saldo, com o estado resultante completo."""
    payload = {
        "unidadeId": str(saldo["unidade_id"]), "itemId": str(saldo["item_id"]),
        "estoqueVersion": saldo["estoque_version"], "estoqueFisicoAtual": saldo["estoque_fisico_atual"],
        "quantidadeAlocada": saldo["quantidade_alocada"], "permiteReserva": saldo["permite_reserva"], **extra,
    }
    conexao.execute("""
        INSERT INTO outbox (event_id, event_type, event_version, aggregate_type, aggregate_id,
            correlation_id, causation_id, occurred_at, payload)
        VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s)
    """, (uuid4(), tipo, agregado_tipo, str(agregado_id), correlacao or uuid4(), causacao, saldo["updated_at"], Jsonb(payload)))


def declarar(canal) -> None:
    canal.exchange_declare(EXCHANGE, "topic", durable=True)
    canal.exchange_declare(EXCHANGE_ERROS, "fanout", durable=True)
    canal.queue_declare(FILA_ERROS, durable=True)
    canal.queue_bind(FILA_ERROS, EXCHANGE_ERROS)
    canal.queue_declare(FILA_PROJECAO, durable=True, arguments={"x-dead-letter-exchange": EXCHANGE_ERROS})
    canal.queue_bind(FILA_PROJECAO, EXCHANGE, routing_key="estoque.#")


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


def iniciar(parar: threading.Event) -> None:
    iniciar_publicador(BANCO, declarar, parar)
    iniciar_consumidor(FILA_PROJECAO, declarar, aplicar, parar)
