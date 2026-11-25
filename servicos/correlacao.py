"""Correlação na entrada (Gateway e BFFs): preserva um X-Correlation-Id válido ou gera um novo."""
import logging
import re
from uuid import uuid4

from fastapi import FastAPI, Request


CABECALHO = "X-Correlation-Id"
UUID_CANONICO = re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
log = logging.getLogger("uvicorn.error")


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlacionar(request: Request, seguir):
        recebido = request.headers.get(CABECALHO, "")
        request.state.correlacao = recebido if UUID_CANONICO.fullmatch(recebido) else str(uuid4())
        resposta = await seguir(request)
        resposta.headers[CABECALHO] = request.state.correlacao
        if request.url.path != "/health":
            log.info("%s %s -> %s correlationId=%s", request.method, request.url.path, resposta.status_code,
                     request.state.correlacao)
        return resposta
