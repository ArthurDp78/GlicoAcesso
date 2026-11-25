import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from servicos.contratos_reserva import ReservaInterna
from servicos.http import cliente_http, consultar, falha_de_configuracao, requisitar
from servicos.identidade_demo import (
    TOKEN_BFF_UNIDADE, TOKEN_PROFISSIONAL, Ator, delegar, exigir_credenciais, profissional_autenticado,
)


@asynccontextmanager
async def ciclo(app: FastAPI):
    exigir_credenciais(TOKEN_PROFISSIONAL, TOKEN_BFF_UNIDADE)
    async with cliente_http(app):
        yield


app = FastAPI(title="GlicoAcesso — BFF Unidade", lifespan=ciclo)
API = "/api/unidade/v1"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


class Link(BaseModel):
    href: str
    method: Literal["GET", "POST"]
    body: dict | None = None


class ReservaPainel(ReservaInterna):
    itemNome: str | None = None
    links: dict[str, Link] = Field(serialization_alias="_links")


class DecisaoProfissional(BaseModel):
    decisao: Literal["ACEITAR", "REJEITAR"]


RESERVAS = TypeAdapter(list[ReservaInterna])


def origem(variavel: str, padrao: str) -> str:
    return os.environ.get(variavel, padrao).rstrip("/")


def repassar_erro(resposta) -> Response:
    if falha_de_configuracao(resposta):
        # A credencial recusada é a do BFF, não a do usuário.
        raise HTTPException(503, "Serviço temporariamente indisponível.")
    if resposta.status_code not in (401, 403, 404, 409, 422, 502, 503, 504):
        raise HTTPException(502, "Não foi possível concluir a operação.")
    headers = {"Cache-Control": "no-store"}
    if "www-authenticate" in resposta.headers:
        headers["WWW-Authenticate"] = resposta.headers["www-authenticate"]
    return Response(resposta.content, status_code=resposta.status_code, media_type="application/json", headers=headers)


async def nomes_dos_itens(request: Request) -> dict[UUID, str]:
    # O nome é complementar: sem o catálogo, o painel continua útil.
    try:
        resposta = await consultar(request.app.state.http, origem("ESTOQUE_URL", "http://127.0.0.1:8003") + "/api/cidadao/v1/estoque/itens")
        return {UUID(item["itemId"]): item["nome"] for item in resposta.json()} if resposta.status_code == 200 else {}
    except (HTTPException, ValueError, KeyError, TypeError):
        return {}


def para_painel(reserva: ReservaInterna, nomes: dict[UUID, str]) -> ReservaPainel:
    href = f"{API}/painel/reservas/{reserva.reservaId}"
    links = {"self": Link(href=href, method="GET")}
    if reserva.status == "SOLICITADA":
        decisao = f"{API}/reservas/{reserva.reservaId}/decisao"
        links["aceitar"] = Link(href=decisao, method="POST", body={"decisao": "ACEITAR"})
        links["rejeitar"] = Link(href=decisao, method="POST", body={"decisao": "REJEITAR"})
    return ReservaPainel(**reserva.model_dump(), itemNome=nomes.get(reserva.itemId), links=links)


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "bff-unidade", "status": "ok"}


@app.get(API + "/painel/reservas", response_model=list[ReservaPainel], response_model_exclude_none=True)
async def listar_pendentes(request: Request, response: Response, profissional: Profissional):
    resposta = await consultar(
        request.app.state.http, origem("RESERVAS_URL", "http://127.0.0.1:8004") + "/api/unidade/v1/reservas",
        headers=delegar(TOKEN_BFF_UNIDADE, profissional),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    try:
        reservas = RESERVAS.validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "Reservas retornou dados incompatíveis.") from erro
    response.headers["Cache-Control"] = "no-store"
    nomes = await nomes_dos_itens(request)
    return [para_painel(reserva, nomes) for reserva in reservas]


@app.get(API + "/painel/reservas/{reservaId}", response_model=ReservaPainel, response_model_exclude_none=True)
async def consultar_reserva(request: Request, response: Response, reservaId: UUID, profissional: Profissional):
    resposta = await consultar(
        request.app.state.http, origem("RESERVAS_URL", "http://127.0.0.1:8004") + f"/internal/v1/reservas/{reservaId}",
        headers=delegar(TOKEN_BFF_UNIDADE, profissional),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    try:
        reserva = ReservaInterna.model_validate_json(resposta.content, extra="ignore")
    except ValidationError as erro:
        raise HTTPException(502, "Reservas retornou dados incompatíveis.") from erro
    response.headers["Cache-Control"] = "no-store"
    return para_painel(reserva, await nomes_dos_itens(request))


@app.post(API + "/reservas/{reservaId}/decisao")
async def decidir(
    request: Request, reservaId: UUID, corpo: DecisaoProfissional, profissional: Profissional,
    chave: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
):
    cabecalhos = {**delegar(TOKEN_BFF_UNIDADE, profissional), "Idempotency-Key": chave}
    cliente = request.app.state.http
    resposta = await requisitar(
        cliente, "POST", origem("RESERVAS_URL", "http://127.0.0.1:8004") + f"/api/unidade/v1/reservas/{reservaId}/decisao",
        headers=cabecalhos, json=corpo.model_dump(),
    )
    if resposta.status_code == 200:
        return JSONResponse(resposta.json(), headers={"Cache-Control": "no-store"})
    try:
        encaminhar = resposta.status_code == 409 and resposta.json().get("codigo") == "ACEITE_ENCAMINHAR"
    except ValueError:
        encaminhar = False
    if not encaminhar:
        return repassar_erro(resposta)
    # Só o encaminhamento conclusivo de Reservas autoriza chamar o Orquestrador, com a mesma chave.
    pedido = await requisitar(
        cliente, "POST", origem("ORQUESTRADOR_URL", "http://127.0.0.1:8006") + f"/internal/v1/reservas/{reservaId}/confirmacoes",
        headers=cabecalhos,
    )
    if pedido.status_code != 202:
        return repassar_erro(pedido)
    return JSONResponse({"reservaId": str(reservaId)}, status_code=202, headers={
        "Location": f"{API}/painel/reservas/{reservaId}", "Cache-Control": "no-store",
    })


class EstoquePainelItem(BaseModel):
    itemId: UUID
    unidadeId: UUID
    itemNome: str
    estoqueFisicoAtual: int
    quantidadeAlocada: int
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: str  # Repassado como veio da projeção: é o instante do estado, não da consulta.


ESTOQUE_PAINEL = TypeAdapter(list[EstoquePainelItem])


@app.get(API + "/painel/estoque", response_model=list[EstoquePainelItem])
async def painel_estoque(
    request: Request, response: Response, profissional: Profissional,
):
    # O token é validado aqui para descobrir a unidade do profissional; Estoque confere o vínculo de novo.
    resposta = await consultar(
        request.app.state.http,
        origem("ESTOQUE_URL", "http://127.0.0.1:8003") + f"/api/unidade/v1/estoque/{profissional.unidadeId}/itens",
        headers=delegar(TOKEN_BFF_UNIDADE, profissional),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    try:
        itens = ESTOQUE_PAINEL.validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "Estoque retornou dados incompatíveis.") from erro
    response.headers["Cache-Control"] = "no-store"
    return itens
