"""Mecanismos comuns aos BFFs: chamada delegada, propagação de respostas e encaminhamento à SAGA."""
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, TypeAdapter, ValidationError

from servicos import correlacao
from servicos.http import cliente_http, falha_de_configuracao, requisitar
from servicos.identidade_demo import Ator, delegar, exigir_credenciais


ORIGENS = {
    "unidades": ("UNIDADES_URL", "http://127.0.0.1:8002"),
    "estoque": ("ESTOQUE_URL", "http://127.0.0.1:8003"),
    "reservas": ("RESERVAS_URL", "http://127.0.0.1:8004"),
    "orquestrador": ("ORQUESTRADOR_URL", "http://127.0.0.1:8006"),
    "retiradas": ("RETIRADAS_URL", "http://127.0.0.1:8007"),
}
# Respostas conclusivas do serviço, repassadas com status e corpo originais.
REPASSADOS = (200, 201, 400, 403, 404, 409, 422)
INDISPONIVEL = "Serviço temporariamente indisponível. Repita a operação; em comandos, use a mesma chave e conteúdo."
SEM_CACHE = {"Cache-Control": "no-store"}
log = logging.getLogger("uvicorn.error")


class RespostaRecusada(Exception):
    """Um serviço respondeu algo diferente do esperado: a resposta é propagada ao cliente."""

    def __init__(self, resposta: httpx.Response):
        self.resposta = resposta


def repassar(resposta: httpx.Response) -> Response:
    # Uma credencial recusada é a do BFF, não a do usuário; 5xx e respostas inesperadas não são conclusivos.
    if resposta.status_code not in REPASSADOS or falha_de_configuracao(resposta):
        log.warning("%s %s respondeu %s", resposta.request.method, resposta.request.url.path, resposta.status_code)
        return JSONResponse({"detail": INDISPONIVEL}, status_code=503, headers=SEM_CACHE)
    return Response(resposta.content, status_code=resposta.status_code, media_type="application/json", headers=SEM_CACHE)


def criar_app(titulo: str, *credenciais: str) -> FastAPI:
    @asynccontextmanager
    async def ciclo(app: FastAPI):
        exigir_credenciais(*credenciais)
        async with cliente_http(app, timeout=8.0):
            yield

    app = FastAPI(title=titulo, lifespan=ciclo)
    correlacao.instalar(app)

    @app.exception_handler(RespostaRecusada)
    async def propagar(_request, erro: RespostaRecusada):
        return repassar(erro.resposta)

    return app


class Servicos:
    """Acesso aos serviços em nome do ator da requisição, com a credencial própria do BFF."""

    def __init__(self, request: Request, credencial: str, ator: Ator | None = None, chave: str | None = None):
        self.request, self.credencial, self.ator, self.chave = request, credencial, ator, chave

    async def chamar(self, servico: str, metodo: str, caminho: str, *, corpo: bytes | None = None, params=None,
                     publico: bool = False) -> httpx.Response:
        variavel, padrao = ORIGENS[servico]
        cabecalhos = {correlacao.CABECALHO: self.request.state.correlacao}
        if not publico:
            cabecalhos |= delegar(self.credencial, self.ator)
        if self.chave is not None:
            cabecalhos["Idempotency-Key"] = self.chave
        if corpo is not None:
            cabecalhos["Content-Type"] = "application/json"
        try:
            return await requisitar(self.request.app.state.http, metodo, os.environ.get(variavel, padrao).rstrip("/") + caminho,
                                    headers=cabecalhos, content=corpo, params=params)
        except HTTPException as erro:
            raise HTTPException(503, INDISPONIVEL) from erro

    async def obter(self, servico: str, caminho: str, modelo: TypeAdapter, **opcoes):
        """Consulta principal: uma recusa é propagada e dados incompatíveis são indisponibilidade."""
        resposta = await self.chamar(servico, "GET", caminho, **opcoes)
        if resposta.status_code != 200:
            raise RespostaRecusada(resposta)
        try:
            return modelo.validate_json(resposta.content)
        except ValidationError as erro:
            raise HTTPException(503, INDISPONIVEL) from erro

    async def complementar(self, servico: str, caminho: str, modelo: TypeAdapter, *, exigir_integracao=False, **opcoes):
        """Busca um complemento; callers podem exigir dependência quando ela decide ações disponíveis."""
        try:
            return await self.obter(servico, caminho, modelo, **opcoes)
        except RespostaRecusada as erro:
            if erro.resposta.status_code == 404 and not falha_de_configuracao(erro.resposta):
                return None  # Recurso opcional ausente, conforme contrato.
            if erro.resposta.status_code >= 500:
                log.warning("Complemento de %s indisponível: HTTP %s", servico, erro.resposta.status_code)
                if exigir_integracao:
                    raise HTTPException(503, INDISPONIVEL) from erro
                return None
            log.warning("Complemento de %s respondeu fora do contrato: HTTP %s", servico, erro.resposta.status_code)
            raise HTTPException(503, INDISPONIVEL) from erro
        except HTTPException as erro:
            log.warning("Complemento de %s indisponível: HTTP %s", servico, erro.status_code)
            if exigir_integracao:
                raise HTTPException(503, INDISPONIVEL) from erro
            return None

    async def comandar(self, servico: str, metodo: str, caminho: str, corpo: BaseModel) -> Response:
        """Encaminha o DTO validado pelo contrato da borda ao serviço dono da regra."""
        conteudo = corpo.model_dump_json().encode()
        return repassar(await self.chamar(servico, metodo, caminho, corpo=conteudo))


def codigo_do_conflito(resposta: httpx.Response) -> str | None:
    try:
        return resposta.json().get("codigo") if resposta.status_code == 409 else None
    except (ValueError, AttributeError):
        return None


async def encaminhar(servicos: Servicos, reserva_id, caminho_local: str, codigo: str, pedido_saga: str, acompanhamento: str,
                     corpo: bytes | None = None, corpo_saga: bytes | None = None) -> Response:
    """Operação local em Reservas; só o encaminhamento conclusivo autoriza chamar o Orquestrador, com a mesma chave."""
    local = await servicos.chamar("reservas", "POST", caminho_local, corpo=corpo)
    if codigo_do_conflito(local) != codigo:
        return repassar(local)
    pedido = await servicos.chamar("orquestrador", "POST", f"/internal/v1/reservas/{reserva_id}/{pedido_saga}", corpo=corpo_saga)
    if pedido.status_code != 202:
        return repassar(pedido)
    return JSONResponse({"reservaId": str(reserva_id)}, status_code=202, headers={"Location": acompanhamento, **SEM_CACHE})
