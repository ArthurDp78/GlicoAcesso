from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StrictBool, StringConstraints

ROTA_ORIENTACAO = "/api/cidadao/v1/orientacoes"
ROTA_INTERNA_ORIENTACAO = "/internal/v1/orientacoes"
TOKEN_ORIENTACAO = "GLICO_ORIENTACAO_SERVICE_TOKEN"


class PedidoOrientacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itemId: UUID
    pergunta: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class UnidadeConsultada(BaseModel):
    unidadeId: UUID
    nomeUnidade: str
    disponivel: StrictBool
    permiteReserva: StrictBool
    atualizadoEm: AwareDatetime


class ConsultaDisponibilidade(BaseModel):
    status: Literal["consultada", "indisponivel", "nao_consultada"] = "nao_consultada"
    unidades: tuple[UnidadeConsultada, ...] = ()


class FonteOrientacao(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    titulo: str
    secao: str


class RespostaOrientacao(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    modo: Literal["rag", "orientacao_basica", "fora_do_escopo"]
    resposta: str
    fontes: tuple[FonteOrientacao, ...]
    consulta: ConsultaDisponibilidade
