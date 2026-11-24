import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from servicos.contratos_reserva import ReservaInterna
from servicos.http import cliente_http, consultar, requisitar


app = FastAPI(title="GlicoAcesso — BFF Unidade", lifespan=cliente_http)
API = "/api/unidade/v1"


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


def credencial(request: Request) -> dict[str, str]:
    return {"authorization": request.headers["authorization"]} if "authorization" in request.headers else {}


def repassar_erro(resposta) -> Response:
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
async def listar_pendentes(request: Request, response: Response):
    resposta = await consultar(
        request.app.state.http, origem("RESERVAS_URL", "http://127.0.0.1:8004") + "/api/unidade/v1/reservas",
        headers=credencial(request),
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
async def consultar_reserva(request: Request, response: Response, reservaId: UUID):
    resposta = await consultar(
        request.app.state.http, origem("RESERVAS_URL", "http://127.0.0.1:8004") + f"/internal/v1/reservas/{reservaId}",
        headers=credencial(request),
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
    request: Request, reservaId: UUID, corpo: DecisaoProfissional,
    chave: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
):
    cabecalhos = {**credencial(request), "Idempotency-Key": chave}
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
