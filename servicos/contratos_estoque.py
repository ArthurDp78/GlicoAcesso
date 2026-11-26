from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator


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


class ConfigurarReserva(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permiteReserva: StrictBool


class AjusteEstoque(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variacaoFisica: Annotated[int, Field(strict=True, ge=-LIMITE_ESTOQUE, le=LIMITE_ESTOQUE)]
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\x00]+$")]

    @field_validator("variacaoFisica")
    @classmethod
    def exigir_variacao(cls, valor: int) -> int:
        if valor == 0:
            raise ValueError("A variação deve ser diferente de zero.")
        return valor
