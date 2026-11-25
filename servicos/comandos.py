"""Tipos e respostas comuns aos comandos HTTP idempotentes."""
import logging
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import StringConstraints


INTEIRO_MAXIMO = 2147483647  # Limite do tipo integer do PostgreSQL.
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"\S")]
Correlacao = Annotated[UUID | None, Header(alias="X-Correlation-Id")]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Justificativa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5)]

log = logging.getLogger("uvicorn.error")


def _rastrear(request: Request, correlacao: Correlacao = None) -> None:
    if correlacao is not None:
        log.info("%s %s correlationId=%s", request.method, request.url.path, correlacao)


RASTREADO = [Depends(_rastrear)]  # Aceita e registra o X-Correlation-Id documentado.


def resumir(*partes) -> str:
    """Impressão digital do conteúdo canônico do comando."""
    return sha256(":".join(str(parte) for parte in partes).encode()).hexdigest()


def responder(resultado: tuple[int, dict]) -> JSONResponse:
    return JSONResponse(resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})
