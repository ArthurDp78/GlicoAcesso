from contextlib import asynccontextmanager

import httpx
from contextvars import ContextVar
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request


correlacao = ContextVar[UUID | None]("correlacao", default=None)
CABECALHO_CORRELACAO = "X-Correlation-Id"


async def correlacionar(request: Request, continuar):
    try:
        identificador = UUID(request.headers.get(CABECALHO_CORRELACAO, ""))
    except ValueError:
        identificador = uuid4()
    token = correlacao.set(identificador)
    try:
        resposta = await continuar(request)
        resposta.headers[CABECALHO_CORRELACAO] = str(identificador)
        return resposta
    finally:
        correlacao.reset(token)

from servicos.identidade_demo import CHAMADOR_NAO_AUTORIZADO


@asynccontextmanager
async def cliente_http(app: FastAPI, timeout: float = 4.0):
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as cliente:
        app.state.http = cliente
        yield


async def requisitar(cliente: httpx.AsyncClient, metodo: str, url: str, **opcoes) -> httpx.Response:
    try:
        headers = httpx.Headers(opcoes.pop("headers", None))
        if (identificador := correlacao.get()) is not None:
            headers[CABECALHO_CORRELACAO] = str(identificador)
        return await cliente.request(metodo, url, headers=headers, **opcoes)
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
