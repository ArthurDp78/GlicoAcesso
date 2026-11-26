"""Painel de reservas, decisões, cancelamento e entrega."""
import asyncio
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from servicos.bff import RESPOSTA_PROCESSAMENTO, encaminhar
from servicos.bff_unidade.contexto import API, Comando, Consulta, caminho_unidade
from servicos.bff_unidade.representacoes import ESTOQUE_PAINEL, UNIDADE
from servicos.contratos_reserva import CancelamentoUnidade
from servicos.contratos_retirada import PedidoRetirada
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


def links_da_reserva(reserva: ReservaInterna, autorizacao: DadosAutorizacao | None, unidade_ativa: bool,
                     *, agora: datetime | None = None):
    consulta, acoes = f"{API}/painel/reservas/{reserva.reservaId}", f"{API}/reservas/{reserva.reservaId}"
    links = {"self": LinkReserva(href=consulta, method="GET")}
    instante = agora or datetime.now(timezone.utc)
    dentro_do_prazo = reserva.decisaoAte > instante
    if reserva.status == "SOLICITADA" and dentro_do_prazo:
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
    autorizacao_pendente = (
        servicos.complementar("retiradas", f"/internal/v1/autorizacoes/{reservaId}", AUTORIZACAO,
                              exigir_integracao=True)
        if reserva.status == "CONFIRMADA" else asyncio.sleep(0, result=None)
    )
    itens, unidade, autorizacao, estoque = await asyncio.gather(
        catalogo(servicos), cadastro(servicos), autorizacao_pendente,
        servicos.complementar("estoque", f"{API}/estoque/{reserva.unidadeId}/itens", ESTOQUE_PAINEL),
    )
    return apresentar(reserva, itens, unidade, autorizacao, estoque)


@rotas.post("/reservas/{reservaId}/decisao", responses=RESPOSTA_PROCESSAMENTO)
async def decidir(reservaId: UUID, corpo: DecisaoProfissional, servicos: Comando):
    return await encaminhar(
        servicos, reservaId, f"{API}/reservas/{reservaId}/decisao", "ACEITE_ENCAMINHAR", "confirmacoes",
        f"{API}/painel/reservas/{reservaId}", corpo=corpo.model_dump_json().encode(),
    )


@rotas.post("/reservas/{reservaId}/cancelar", responses=RESPOSTA_PROCESSAMENTO)
async def cancelar(reservaId: UUID, corpo: CancelamentoUnidade, servicos: Comando):
    payload = corpo.model_dump_json().encode()
    return await encaminhar(
        servicos, reservaId, f"{API}/reservas/{reservaId}/cancelar", "CANCELAMENTO_DISTRIBUIDO", "cancelamentos",
        f"{API}/painel/reservas/{reservaId}", corpo=payload, corpo_saga=payload,
    )


@rotas.post("/retiradas", status_code=201)
async def registrar_retirada(corpo: PedidoRetirada, servicos: Comando):
    return await servicos.comandar("retiradas", "POST", API + "/retiradas", corpo)
