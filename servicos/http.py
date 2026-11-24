from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException


@asynccontextmanager
async def cliente_http(app: FastAPI):
    async with httpx.AsyncClient(timeout=4.0, trust_env=False) as cliente:
        app.state.http = cliente
        yield


async def consultar(cliente: httpx.AsyncClient, url: str, *, params=None) -> httpx.Response:
    try:
        return await cliente.get(url, params=params)
    except httpx.TimeoutException as erro:
        raise HTTPException(504, "O serviço de consulta demorou a responder.") from erro
    except httpx.RequestError as erro:
        raise HTTPException(502, "O serviço de consulta está indisponível.") from erro
