from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints


LIMITE_ESTOQUE = 2_147_483_647


class Item(BaseModel):
    itemId: UUID
    nome: str
    tipo: Literal["MEDICAMENTO", "INSUMO"]
    descricao: str | None = None


class EntradaEstoque(BaseModel):
    quantidade: Annotated[int, Field(strict=True, ge=1, le=LIMITE_ESTOQUE)]
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\x00]+$")] = "Entrada de estoque"


class MovimentacaoEstoque(BaseModel):
    movimentacaoId: UUID
    unidadeId: UUID
    itemId: UUID
    variacaoFisica: int
    ocorridaEm: AwareDatetime
    estoqueVersion: int
