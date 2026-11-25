from uuid import UUID

import httpx
from fastapi import HTTPException
from langchain_core.tools import StructuredTool
from pydantic import TypeAdapter, ValidationError

from servicos.contratos_orientacao import ConsultaDisponibilidade, UnidadeConsultada
from servicos.http import consultar


UNIDADES = TypeAdapter(tuple[UnidadeConsultada, ...])


def criar_ferramenta_disponibilidade(cliente: httpx.AsyncClient, origem_bff: str) -> StructuredTool:
    url = origem_bff.rstrip("/") + "/api/cidadao/v1/explorar"

    async def consultar_disponibilidade(itemId: UUID) -> ConsultaDisponibilidade:
        """Consulta disponibilidade e permissão de reserva para um item do catálogo do GlicoAcesso."""
        try:
            resposta = await consultar(cliente, url, params={"itemId": str(itemId)})
            if resposta.status_code != 200:
                return ConsultaDisponibilidade(status="indisponivel")
            unidades = UNIDADES.validate_json(resposta.content)
        except (HTTPException, ValidationError):
            return ConsultaDisponibilidade(status="indisponivel")
        return ConsultaDisponibilidade(status="consultada", unidades=unidades)

    return StructuredTool.from_function(coroutine=consultar_disponibilidade)
