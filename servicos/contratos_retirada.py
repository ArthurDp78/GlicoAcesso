"""DTO público para registrar uma retirada presencial."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PedidoRetirada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autorizacaoId: UUID
