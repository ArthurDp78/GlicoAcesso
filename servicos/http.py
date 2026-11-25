from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException

from servicos.identidade_demo import CHAMADOR_NAO_AUTORIZADO


@asynccontextmanager
async def cliente_http(app: FastAPI, timeout: float = 4.0):
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as cliente:
        app.state.http = cliente
        yield


async def requisitar(cliente: httpx.AsyncClient, metodo: str, url: str, **opcoes) -> httpx.Response:
    try:
        return await cliente.request(metodo, url, **opcoes)
    except httpx.TimeoutException as erro:
        raise HTTPException(504, "O serviço de consulta demorou a responder.") from erro
    except httpx.RequestError as erro:
        raise HTTPException(502, "O serviço de consulta está indisponível.") from erro

async def consultar(cliente: httpx.AsyncClient, url: str, *, params=None, headers=None) -> httpx.Response:
    return await requisitar(cliente, "GET", url, params=params, headers=headers)


def falha_de_configuracao(resposta: httpx.Response) -> bool:
    """Credencial de serviço recusada ou rota inexistente: não é recusa de negócio nem prova ausência de efeito."""
    if resposta.status_code == 401:
        return True
    try:
        detalhe = resposta.json()["detail"] if resposta.status_code in (403, 404) else None
    except (ValueError, KeyError, TypeError):
        return False
    return detalhe == "Not Found" or (isinstance(detalhe, dict) and detalhe.get("codigo") == CHAMADOR_NAO_AUTORIZADO)
