import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from google.genai.errors import APIError
from langchain_core.exceptions import ModelAPIError, ModelRateLimitError
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError

BACKOFF = (0.25, 0.5)


def atraso_tentativa(
    erro: (
        TimeoutError | httpx.TransportError | APIError | ModelAPIError | ModelRateLimitError
        | ChatGoogleGenerativeAIError
    ),
    atraso: float,
) -> float | None:
    if isinstance(erro, (ModelAPIError, ModelRateLimitError, ChatGoogleGenerativeAIError)):
        causa = erro.__cause__
        if isinstance(causa, APIError):
            erro = causa
        elif isinstance(erro, ChatGoogleGenerativeAIError) and not isinstance(
            erro, (ModelAPIError, ModelRateLimitError),
        ):
            return None

    if isinstance(erro, APIError):
        status = erro.code
        if status not in (408, 429) and not 500 <= status <= 599:
            return None
        if "quota" in (erro.message or "").lower():
            return None
        headers = erro.response.headers if erro.response is not None else {}
        if valor := headers.get("Retry-After"):
            try:
                try:
                    segundos = float(valor)
                except ValueError:
                    instante = parsedate_to_datetime(valor)
                    segundos = (instante - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return atraso
            return max(atraso, segundos)
    elif isinstance(erro, ModelRateLimitError):
        if "quota" in str(erro).lower():
            return None
        return atraso
    elif isinstance(erro, (ModelAPIError, httpx.TransportError)):
        return atraso
    return atraso


async def chamar_provedor[T](chamar: Callable[[], Awaitable[T]], *, timeout: float) -> T:
    for tentativa in range(len(BACKOFF) + 1):
        try:
            async with asyncio.timeout(timeout):
                return await chamar()
        except (
            TimeoutError, httpx.TransportError, APIError, ModelAPIError, ModelRateLimitError,
            ChatGoogleGenerativeAIError,
        ) as erro:
            if tentativa == len(BACKOFF):
                raise
            atraso = atraso_tentativa(erro, BACKOFF[tentativa])
            if atraso is None or atraso >= timeout:
                raise
            await asyncio.sleep(atraso)
    raise AssertionError("Nenhuma tentativa de chamada registrada.")
