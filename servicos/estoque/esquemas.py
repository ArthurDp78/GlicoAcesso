from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field

from servicos.comandos import INTEIRO_MAXIMO, NaoNulo, Texto, TextoLivre


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ItemInput(Entrada):
    nome: Texto
    tipo: Literal["MEDICAMENTO", "INSUMO"]
    descricao: Annotated[TextoLivre | None, NaoNulo] = None


class PermissaoInput(Entrada):
    permiteReserva: Annotated[bool, Field(strict=True)]


class EntradaFisica(Entrada):
    quantidade: Annotated[int, Field(strict=True, ge=1, le=INTEIRO_MAXIMO)]
    motivo: Texto


def diferente_de_zero(valor: int) -> int:
    if valor == 0:
        raise ValueError("a variação não pode ser zero")
    return valor


class AjusteFisico(Entrada):
    variacaoFisica: Annotated[int, Field(strict=True, ge=-INTEIRO_MAXIMO, le=INTEIRO_MAXIMO), AfterValidator(diferente_de_zero)]
    motivo: Texto


class Movimentacao(BaseModel):
    movimentacaoId: UUID
    unidadeId: UUID
    itemId: UUID
    variacaoFisica: int
    ocorridaEm: AwareDatetime
    estoqueVersion: int
