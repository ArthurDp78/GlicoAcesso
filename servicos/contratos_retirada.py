from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from servicos.contratos_reserva import EstadoReserva


class EstadoCanonico(BaseModel):
    reservaId: UUID
    status: EstadoReserva


class AutorizacaoPainel(BaseModel):
    autorizacaoId: UUID
    status: Literal["ATIVA", "CANCELADA", "UTILIZADA"]


class Autorizacao(AutorizacaoPainel):
    reservaId: UUID
    sagaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: int


class PedidoRetirada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    autorizacaoId: UUID


class RetiradaRegistrada(PedidoRetirada):
    retiradaId: UUID
    realizadaEm: AwareDatetime


class EntregaConcluida(BaseModel):
    retiradaId: UUID
    reservaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: Annotated[int, Field(strict=True, gt=0, le=2_147_483_647)]


class EventoRetirada(BaseModel):
    eventId: UUID
    eventType: Literal["retirada.concluida.v1"]
    eventVersion: Literal[1]
    correlationId: UUID
    occurredAt: AwareDatetime
    payload: EntregaConcluida
