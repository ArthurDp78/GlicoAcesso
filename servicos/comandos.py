"""Tipos e respostas comuns aos comandos HTTP idempotentes."""
import logging
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import AfterValidator, BeforeValidator, StringConstraints


PRAZO_MAXIMO_HORAS = 720  # 30 dias: limite de prazoAnaliseHoras.
INTEIRO_MAXIMO = 2147483647  # Limite do tipo integer do PostgreSQL.
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"\S")]
Correlacao = Annotated[UUID | None, Header(alias="X-Correlation-Id")]


def sem_nulo(valor: str) -> str:
    if "\x00" in valor:
        raise ValueError("o texto contém caractere nulo, que o banco não armazena")
    return valor


def recusar_nulo(valor):
    if valor is None:
        raise ValueError("omita o campo em vez de enviar null")
    return valor


NaoNulo = BeforeValidator(recusar_nulo)  # Para campos opcionais: o padrão None não passa pelo validador.
TextoLivre = Annotated[str, AfterValidator(sem_nulo)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1), AfterValidator(sem_nulo)]
Justificativa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5), AfterValidator(sem_nulo)]

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


def cadastro_conflitante(erro: UniqueViolation, restricao: str, mensagem: str) -> tuple[int, dict]:
    """Traduz a unicidade garantida pelo banco, que também decide entre cadastros concorrentes."""
    if erro.diag.constraint_name != restricao:
        raise erro
    return 409, {"codigo": "CADASTRO_CONFLITANTE", "mensagem": mensagem}
