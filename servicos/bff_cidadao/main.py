import asyncio
import os
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, TypeAdapter, ValidationError

from servicos.http import cliente_http, consultar


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
