import asyncio
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, TypeAdapter, ValidationError

from servicos.contratos_reserva import DadosReserva, LinkReserva, PedidoReserva, ReservaPublica
from servicos.http import cliente_http, consultar, requisitar


app = FastAPI(title="GlicoAcesso — BFF Cidadão", lifespan=cliente_http)


class Unidade(BaseModel):
    unidadeId: UUID
    nome: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str


class Item(BaseModel):
    itemId: UUID
    nome: str
    tipo: Literal["MEDICAMENTO", "INSUMO"]


class Disponibilidade(BaseModel):
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: str


class UnidadeDisponivel(BaseModel):
    unidadeId: UUID
    nomeUnidade: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str
    disponivel: bool
    permiteReserva: bool
    atualizadoEm: str


ITENS = TypeAdapter(list[Item])
UNIDADES = TypeAdapter(list[Unidade])


def decodificar(resposta, validar):
    if resposta.status_code != 200:
        status = 503 if resposta.status_code == 503 else 502
        raise HTTPException(status, "Não foi possível consultar os dados neste momento.")
    try:
        return validar(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "O serviço retornou dados de consulta inválidos.") from erro


def origem_unidades() -> str:
    return os.environ.get("UNIDADES_URL", "http://127.0.0.1:8002").rstrip("/")


def origem_estoque() -> str:
    return os.environ.get("ESTOQUE_URL", "http://127.0.0.1:8003").rstrip("/")


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "bff-cidadao", "status": "ok"}


@app.get("/api/cidadao/v1/itens", response_model=list[Item])
async def listar_itens(request: Request):
    resposta = await consultar(request.app.state.http, origem_estoque() + "/api/cidadao/v1/estoque/itens")
    return decodificar(resposta, ITENS.validate_json)


@app.get("/api/cidadao/v1/unidades", response_model=list[Unidade])
async def listar_unidades(request: Request):
    resposta = await consultar(request.app.state.http, origem_unidades() + "/api/cidadao/v1/unidades")
    return decodificar(resposta, UNIDADES.validate_json)


@app.get("/api/cidadao/v1/explorar", response_model=list[UnidadeDisponivel])
async def explorar(request: Request, itemId: UUID):
    unidades = await listar_unidades(request)
    destino = origem_estoque() + "/api/cidadao/v1/estoque/disponibilidade"
    limite = asyncio.Semaphore(12)

    async def combinar(unidade: Unidade) -> UnidadeDisponivel | None:
        async with limite:
            resposta = await consultar(
                request.app.state.http, destino,
                params={"unidadeId": str(unidade.unidadeId), "itemId": str(itemId)},
            )
        if resposta.status_code == 404:
            return None
        dado = decodificar(resposta, Disponibilidade.model_validate_json)
        return UnidadeDisponivel(
            unidadeId=unidade.unidadeId,
            nomeUnidade=unidade.nome,
            endereco=unidade.endereco,
            horarioAtendimento=unidade.horarioAtendimento,
            orientacoesRetirada=unidade.orientacoesRetirada,
            disponivel=dado.quantidadeDisponivel > 0,
            permiteReserva=dado.permiteReserva,
            atualizadoEm=dado.atualizadoEm,
        )

    resultados = await asyncio.gather(*(combinar(unidade) for unidade in unidades))
    return [resultado for resultado in resultados if resultado is not None]

def origem_reservas() -> str:
    return os.environ.get("RESERVAS_URL", "http://127.0.0.1:8004").rstrip("/")


def cabecalhos_autenticados(request: Request) -> dict[str, str]:
    return {
        nome: request.headers[nome]
        for nome in ("authorization", "idempotency-key")
        if nome in request.headers
    }


def apresentar_reserva(resposta, status_esperado: int, saida: Response):
    if resposta.status_code != status_esperado:
        if resposta.status_code not in (401, 403, 404, 409, 422, 502, 503, 504):
            raise HTTPException(502, "Não foi possível concluir a consulta de Reservas.")
        headers = {"Cache-Control": "no-store"}
        if "www-authenticate" in resposta.headers:
            headers["WWW-Authenticate"] = resposta.headers["www-authenticate"]
        return Response(resposta.content, status_code=resposta.status_code,
                        media_type="application/json", headers=headers)
    try:
        dados = DadosReserva.model_validate_json(resposta.content, extra="ignore")
    except ValidationError as erro:
        raise HTTPException(502, "Reservas retornou dados incompatíveis.") from erro
    href = f"/api/cidadao/v1/reservas/{dados.reservaId}"
    saida.headers["Cache-Control"] = "no-store"
    if status_esperado == 201:
        saida.headers["Location"] = href
    return ReservaPublica(**dados.model_dump(), links={"self": LinkReserva(href=href, method="GET")})


@app.post("/api/cidadao/v1/reservas", status_code=201, response_model=ReservaPublica)
async def criar_reserva(
    request: Request, response: Response, pedido: PedidoReserva,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
):
    resposta = await requisitar(
        request.app.state.http, "POST", origem_reservas() + "/api/cidadao/v1/reservas",
        headers={**cabecalhos_autenticados(request), "Idempotency-Key": idempotency_key},
        json=pedido.model_dump(mode="json"),
    )
    return apresentar_reserva(resposta, 201, response)


@app.get("/api/cidadao/v1/reservas/{reservaId}", response_model=ReservaPublica)
async def consultar_reserva(request: Request, response: Response, reservaId: UUID):
    resposta = await consultar(
        request.app.state.http, origem_reservas() + f"/internal/v1/reservas/{reservaId}",
        headers=cabecalhos_autenticados(request),
    )
    return apresentar_reserva(resposta, 200, response)
