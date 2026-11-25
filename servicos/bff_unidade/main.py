import os
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from servicos.cancelamento_bff import cancelar_pelo_bff
from servicos.contratos_reserva import ESTADOS_CANCELAVEIS, JustificativaCancelamento, ReservaInterna
from servicos.contratos_retirada import Autorizacao, AutorizacaoPainel, PedidoRetirada, RetiradaRegistrada
from servicos.contratos_unidade import HorariosUnidade, PrazoUnidade, SituacaoUnidade, UnidadeInput
from servicos.contratos_estoque import AjusteEstoque, ConfigurarReserva, EntradaEstoque, Item, MovimentacaoEstoque
from servicos.delegacao_unidade import emitir_credencial
from servicos.http import cliente_http, consultar, correlacionar, requisitar
from servicos.identidade_demo import Ator, profissional_autenticado


app = FastAPI(title="GlicoAcesso — BFF Unidade", lifespan=cliente_http)
app.middleware("http")(correlacionar)
API = "/api/unidade/v1"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


class Link(BaseModel):
    href: str
    method: Literal["GET", "POST"]
    body: dict | None = None


class ReservaPainel(ReservaInterna):
    itemNome: str | None = None
    dadosAutorizacao: AutorizacaoPainel | None = None
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


def para_painel(reserva: ReservaInterna, nomes: dict[UUID, str], autorizacao: Autorizacao | None = None) -> ReservaPainel:
    href = f"{API}/painel/reservas/{reserva.reservaId}"
    links = {"self": Link(href=href, method="GET")}
    if reserva.status == "SOLICITADA":
        decisao = f"{API}/reservas/{reserva.reservaId}/decisao"
        links["aceitar"] = Link(href=decisao, method="POST", body={"decisao": "ACEITAR"})
        links["rejeitar"] = Link(href=decisao, method="POST", body={"decisao": "REJEITAR"})
    if reserva.status in ESTADOS_CANCELAVEIS and (autorizacao is None or autorizacao.status != "UTILIZADA"):
        links["cancelar"] = Link(href=f"{API}/reservas/{reserva.reservaId}/cancelar", method="POST",
                                 body={"justificativa": ""})
    if reserva.status == "CONFIRMADA" and autorizacao and autorizacao.status == "ATIVA":
        links["autorizacao-retirada"] = Link(
            href=f"{API}/retiradas", method="POST", body={"autorizacaoId": str(autorizacao.autorizacaoId)},
        )
    return ReservaPainel(
        **reserva.model_dump(), itemNome=nomes.get(reserva.itemId), dadosAutorizacao=autorizacao, links=links,
    )


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
    autorizacao = None
    if reserva.status in ("CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO", "RETIRADA", "CANCELADA"):
        leitura = await consultar(
            request.app.state.http, f"{origem_retiradas()}/internal/v1/autorizacoes/{reservaId}",
            headers=credencial(request),
        )
        if leitura.status_code == 200:
            try:
                autorizacao = Autorizacao.model_validate_json(leitura.content)
            except ValidationError as erro:
                raise HTTPException(502, "Retiradas retornou dados incompatíveis.") from erro
            if (autorizacao.reservaId, autorizacao.unidadeId, autorizacao.itemId, autorizacao.quantidade) != (
                reserva.reservaId, reserva.unidadeId, reserva.itemId, reserva.quantidade,
            ):
                raise HTTPException(502, "A autorização diverge da reserva.")
        elif leitura.status_code != 404:
            return repassar_erro(leitura)
    return para_painel(reserva, await nomes_dos_itens(request), autorizacao)


@app.post(API + "/reservas/{reservaId}/decisao")
async def decidir(
    request: Request, reservaId: UUID, corpo: DecisaoProfissional,
    profissional: Annotated[Ator, Depends(profissional_autenticado)],
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
        headers={"Authorization": "Bearer " + emitir_credencial(profissional), "Idempotency-Key": chave},
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
ITENS = TypeAdapter(list[Item])


class CatalogoPainel(BaseModel):
    unidadeId: UUID
    itens: list[Item]


@app.get(API + "/painel/estoque/catalogo", response_model=CatalogoPainel, response_model_exclude_none=True)
async def catalogo_estoque(request: Request, response: Response, profissional: Profissional):
    resposta = await consultar(
        request.app.state.http,
        origem("ESTOQUE_URL", "http://127.0.0.1:8003") + "/api/unidade/v1/estoque/itens",
        headers=credencial(request),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    try:
        itens = ITENS.validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "Estoque retornou um catálogo incompatível.") from erro
    response.headers["Cache-Control"] = "no-store"
    return {"unidadeId": profissional.unidadeId, "itens": itens}


@app.post(API + "/painel/estoque/{unidadeId}/itens/{itemId}/entradas", status_code=201, response_model=MovimentacaoEstoque)
async def registrar_entrada(
    request: Request, unidadeId: UUID, itemId: UUID, entrada: EntradaEstoque,
    profissional: Profissional, chave: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    if profissional.unidadeId != unidadeId:
        raise HTTPException(403, "Ator sem acesso à unidade.")
    destino = origem("ESTOQUE_URL", "http://127.0.0.1:8003")
    resposta = await requisitar(
        request.app.state.http, "POST", f"{destino}/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/entradas",
        headers={**credencial(request), "Idempotency-Key": chave}, json=entrada.model_dump(mode="json"),
    )
    if resposta.status_code != 201:
        return repassar_erro(resposta)
    try:
        movimento = MovimentacaoEstoque.model_validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "Estoque retornou uma movimentação incompatível.") from erro
    return JSONResponse(movimento.model_dump(mode="json"), status_code=201, headers={"Cache-Control": "no-store"})


@app.get(API + "/painel/estoque", response_model=list[EstoquePainelItem])
async def painel_estoque(
    request: Request, response: Response, profissional: Annotated[Ator, Depends(profissional_autenticado)],
):
    # O token é validado aqui para descobrir a unidade do profissional; Estoque confere o vínculo de novo.
    resposta = await consultar(
        request.app.state.http,
        origem("ESTOQUE_URL", "http://127.0.0.1:8003") + f"/api/unidade/v1/estoque/{profissional.unidadeId}/itens",
        headers=credencial(request),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    try:
        itens = ESTOQUE_PAINEL.validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "Estoque retornou dados incompatíveis.") from erro
    response.headers["Cache-Control"] = "no-store"
    return itens


Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


async def encaminhar_comando(request, profissional, unidade_id, caminho, pedido, chave, destino, status):
    if profissional.unidadeId != unidade_id:
        raise HTTPException(403, "Ator sem acesso à unidade.")
    resposta = await requisitar(
        request.app.state.http, request.method, destino + caminho,
        headers={**credencial(request), "Idempotency-Key": chave}, json=pedido.model_dump(mode="json"),
    )
    if resposta.status_code != status:
        return repassar_erro(resposta)
    return JSONResponse(resposta.json(), status_code=status, headers={"Cache-Control": "no-store"})


@app.put(API + "/painel/estoque/{unidadeId}/itens/{itemId}/permissao", response_model=ConfigurarReserva)
async def configurar_reserva(request: Request, unidadeId: UUID, itemId: UUID, pedido: ConfigurarReserva,
                             profissional: Profissional, chave: Chave):
    return await encaminhar_comando(
        request, profissional, unidadeId, f"/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/permissao",
        pedido, chave, origem("ESTOQUE_URL", "http://127.0.0.1:8003"), 200,
    )


@app.post(API + "/painel/estoque/{unidadeId}/itens/{itemId}/ajustes", status_code=201,
          response_model=MovimentacaoEstoque)
async def ajustar_estoque(request: Request, unidadeId: UUID, itemId: UUID, pedido: AjusteEstoque,
                          profissional: Profissional, chave: Chave):
    return await encaminhar_comando(
        request, profissional, unidadeId, f"/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/ajustes",
        pedido, chave, origem("ESTOQUE_URL", "http://127.0.0.1:8003"), 201,
    )


def origem_unidades() -> str:
    return origem("UNIDADES_URL", "http://127.0.0.1:8002")


@app.get(API + "/unidade")
async def consultar_unidade(request: Request, profissional: Profissional):
    resposta = await consultar(
        request.app.state.http, f"{origem_unidades()}/internal/v1/unidades/{profissional.unidadeId}",
        headers=credencial(request),
    )
    if resposta.status_code != 200:
        return repassar_erro(resposta)
    return JSONResponse(resposta.json(), headers={"Cache-Control": "no-store"})


async def enviar_manutencao(request, profissional, pedido, chave, sufixo=""):
    unidade_id = profissional.unidadeId
    return await encaminhar_comando(
        request, profissional, unidade_id, f"/internal/v1/unidades/{unidade_id}{sufixo}",
        pedido, chave, origem_unidades(), 200,
    )


@app.put(API + "/unidade")
async def atualizar_unidade(request: Request, profissional: Profissional, pedido: UnidadeInput, chave: Chave):
    return await enviar_manutencao(request, profissional, pedido, chave)


@app.put(API + "/unidade/horarios")
async def atualizar_horarios(request: Request, profissional: Profissional, pedido: HorariosUnidade, chave: Chave):
    return await enviar_manutencao(request, profissional, pedido, chave, "/horarios")


@app.patch(API + "/unidade/status")
async def atualizar_situacao(request: Request, profissional: Profissional, pedido: SituacaoUnidade, chave: Chave):
    return await enviar_manutencao(request, profissional, pedido, chave, "/status")


@app.put(API + "/unidade/prazo-analise")
async def atualizar_prazo(request: Request, profissional: Profissional, pedido: PrazoUnidade, chave: Chave):
    return await enviar_manutencao(request, profissional, pedido, chave, "/prazo-analise")


def origem_retiradas() -> str:
    return origem("RETIRADAS_URL", "http://127.0.0.1:8007")


@app.post(API + "/retiradas", status_code=201, response_model=RetiradaRegistrada)
async def registrar_retirada(request: Request, profissional: Profissional, pedido: PedidoRetirada, chave: Chave):
    return await encaminhar_comando(
        request, profissional, profissional.unidadeId, f"{API}/retiradas", pedido, chave, origem_retiradas(), 201,
    )


@app.post(API + "/reservas/{reservaId}/cancelar")
async def cancelar_reserva(request: Request, reservaId: UUID, profissional: Profissional,
                          corpo: JustificativaCancelamento, chave: Chave):
    return await cancelar_pelo_bff(
        request, origem("RESERVAS_URL", "http://127.0.0.1:8004"),
        origem("ORQUESTRADOR_URL", "http://127.0.0.1:8006"),
        f"{API}/reservas/{reservaId}/cancelar", f"{API}/painel/reservas/{reservaId}",
        reservaId, chave, lambda: emitir_credencial(profissional), corpo.model_dump(),
    )
