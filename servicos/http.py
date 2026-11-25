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


@asynccontextmanager
async def cliente_http(app: FastAPI):
    async with httpx.AsyncClient(timeout=4.0, trust_env=False) as cliente:
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
