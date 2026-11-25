"""Painel de reservas, decisões, cancelamento e entrega."""
import asyncio
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from servicos.bff import encaminhar
from servicos.bff_unidade.administracao import ESTOQUE_PAINEL, UNIDADE, caminho_unidade
from servicos.bff_unidade.contexto import API, Comando, Consulta
from servicos.contratos_reserva import CANCELAVEIS, LinkReserva, ReservaInterna


rotas = APIRouter(prefix=API)


class Item(BaseModel):
    itemId: UUID
    nome: str


class DadosAutorizacao(BaseModel):
    autorizacaoId: UUID
    status: Literal["ATIVA", "CANCELADA", "UTILIZADA"]


class ReservaPainel(ReservaInterna):
    itemNome: str | None = None
    orientacoesRetirada: str | None = None
    estoqueFisicoAtual: int | None = None
    dadosAutorizacao: DadosAutorizacao | None = None
    links: dict[str, LinkReserva] = Field(serialization_alias="_links")


class DecisaoProfissional(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisao: Literal["ACEITAR", "REJEITAR"]


ITENS = TypeAdapter(list[Item])
RESERVA = TypeAdapter(ReservaInterna)
RESERVAS = TypeAdapter(list[ReservaInterna])
AUTORIZACAO = TypeAdapter(DadosAutorizacao)


def links_da_reserva(reserva: ReservaInterna, autorizacao: DadosAutorizacao | None, unidade_ativa: bool):
    consulta, acoes = f"{API}/painel/reservas/{reserva.reservaId}", f"{API}/reservas/{reserva.reservaId}"
    links = {"self": LinkReserva(href=consulta, method="GET")}
    if reserva.status == "SOLICITADA":
        if unidade_ativa:  # Uma unidade inativa não aceita solicitações; não se oferece a ação.
            links["aceitar"] = LinkReserva(href=acoes + "/decisao", method="POST", body={"decisao": "ACEITAR"})
        links["rejeitar"] = LinkReserva(href=acoes + "/decisao", method="POST", body={"decisao": "REJEITAR"})
    if reserva.status == "CONFIRMADA" and autorizacao is not None and autorizacao.status == "ATIVA":
        links["autorizacao-retirada"] = LinkReserva(
            href=API + "/retiradas", method="POST", body={"autorizacaoId": str(autorizacao.autorizacaoId)})
    if reserva.status in CANCELAVEIS:
        links["cancelar"] = LinkReserva(
            href=acoes + "/cancelar", method="POST", body={"justificativa": "Solicitação cancelada pela unidade"})
    return links


def apresentar(reserva: ReservaInterna, itens, unidade, autorizacao=None, estoque=None) -> ReservaPainel:
    return ReservaPainel(
        **reserva.model_dump(),
        itemNome=next((item.nome for item in itens or [] if item.itemId == reserva.itemId), None),
        orientacoesRetirada=unidade.orientacoesRetirada if unidade else None,
        estoqueFisicoAtual=next((linha.estoqueFisicoAtual for linha in estoque or [] if linha.itemId == reserva.itemId), None),
        dadosAutorizacao=autorizacao,
        # Sem o cadastro, a ação é oferecida e o serviço decide.
        links=links_da_reserva(reserva, autorizacao, unidade is None or unidade.ativa),
    )


def catalogo(servicos):
    return servicos.complementar("estoque", "/api/cidadao/v1/estoque/itens", ITENS, publico=True)


def cadastro(servicos):
    return servicos.complementar("unidades", caminho_unidade(servicos), UNIDADE)


@rotas.get("/painel/reservas", response_model=list[ReservaPainel], response_model_exclude_none=True)
async def listar_pendentes(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    reservas = await servicos.obter("reservas", API + "/reservas", RESERVAS)
    # Vista resumida: não consulta autorizações uma a uma.
    itens, unidade = await asyncio.gather(catalogo(servicos), cadastro(servicos))
    return [apresentar(reserva, itens, unidade) for reserva in reservas]


@rotas.get("/painel/reservas/{reservaId}", response_model=ReservaPainel, response_model_exclude_none=True)
async def consultar_reserva(reservaId: UUID, servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    # Reservas verifica o vínculo antes de qualquer dado complementar ser consultado.
    reserva = await servicos.obter("reservas", f"/internal/v1/reservas/{reservaId}", RESERVA)
    itens, unidade, autorizacao, estoque = await asyncio.gather(
        catalogo(servicos), cadastro(servicos),
        servicos.complementar("retiradas", f"/internal/v1/autorizacoes/{reservaId}", AUTORIZACAO),
        servicos.complementar("estoque", f"{API}/estoque/{reserva.unidadeId}/itens", ESTOQUE_PAINEL),
    )
    return apresentar(reserva, itens, unidade, autorizacao, estoque)


@rotas.post("/reservas/{reservaId}/decisao")
async def decidir(reservaId: UUID, corpo: DecisaoProfissional, servicos: Comando):
    return await encaminhar(
        servicos, reservaId, f"{API}/reservas/{reservaId}/decisao", "ACEITE_ENCAMINHAR", "confirmacoes",
        f"{API}/painel/reservas/{reservaId}", corpo=corpo.model_dump_json().encode(),
    )


@rotas.post("/reservas/{reservaId}/cancelar")
async def cancelar(request: Request, reservaId: UUID, servicos: Comando):
    # A justificativa é validada por Reservas e, no pedido distribuído, pelo Orquestrador.
    corpo = await request.body()
    return await encaminhar(
        servicos, reservaId, f"{API}/reservas/{reservaId}/cancelar", "CANCELAMENTO_DISTRIBUIDO", "cancelamentos",
        f"{API}/painel/reservas/{reservaId}", corpo=corpo, corpo_saga=corpo,
    )


@rotas.post("/retiradas", status_code=201)
async def registrar_retirada(servicos: Comando):
    return await servicos.comandar("retiradas", "POST", API + "/retiradas")
