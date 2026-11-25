from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from servicos.comandos import Justificativa



class CancelamentoUnidade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    justificativa: Justificativa


class PedidoReserva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unidadeId: UUID
    itemId: UUID
    quantidade: Annotated[int, Field(strict=True, ge=1, le=2147483647)]


EstadoReserva = Literal[
    "SOLICITADA", "EM_CONFIRMACAO", "CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO",
    "CANCELADA", "REJEITADA", "EXPIRADA", "FALHA_CONFIRMACAO", "RETIRADA",
]


class DadosReserva(PedidoReserva):
    reservaId: UUID
    status: EstadoReserva
    criadaEm: AwareDatetime
    decisaoAte: AwareDatetime


class ReservaInterna(DadosReserva):
    cidadaoId: str


class LinkReserva(BaseModel):
    href: str
    method: Literal["GET", "POST"]
    body: dict | None = None


class ReservaPublica(DadosReserva):
    itemNome: str | None = None
    unidadeNome: str | None = None
    enderecoLocal: str | None = None
    orientacoesRetirada: str | None = None
    links: dict[str, LinkReserva] = Field(serialization_alias="_links")


CANCELAVEIS = ("SOLICITADA", "EM_CONFIRMACAO", "CONFIRMADA")  # Estados em que a ação é oferecida (documento 07).
