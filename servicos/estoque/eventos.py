"""Eventos de Estoque: registro na Outbox e projeção CQRS de disponibilidade.

Fluxo: alteração de `saldos` + `outbox` na mesma transação -> publicador -> RabbitMQ ->
consumidor da projeção -> `disponibilidade` (com `inbox` e comparação de `estoqueVersion`).
"""
import threading
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field

from servicos import mensageria
from servicos.banco import conectar
from servicos.estoque.baixa import processar_retirada


BANCO = "ESTOQUE_DATABASE_URL"
CONSUMIDOR = "projecao-disponibilidade"


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
        if not mensageria.registrar_inbox(conexao, CONSUMIDOR, evento.eventId):
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
    mensageria.iniciar({
        "publicador-outbox": mensageria.publicador(BANCO),
        "projecao-disponibilidade": mensageria.consumidor(mensageria.FILA_PROJECAO, aplicar),
        "baixa-retirada": mensageria.consumidor(mensageria.FILA_RETIRADA_ESTOQUE, processar_retirada),
    }, parar)
