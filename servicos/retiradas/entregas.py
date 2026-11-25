"""Registro da entrega presencial: serializa com a revogação na linha da autorização."""
import os
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from servicos.banco import conectar
from servicos.comandos import Chave, Correlacao, responder, resumir
from servicos.contratos_reserva import EstadoReserva
from servicos.http import consultar, falha_de_configuracao
from servicos.idempotencia import gravar_resultado, reobter_resultado, resultado_anterior
from servicos.identidade_demo import Ator, exigir_unidade, profissional_autenticado
from servicos.mensageria import RETIRADA_CONCLUIDA, gravar_outbox


rotas = APIRouter()
BANCO = "RETIRADAS_DATABASE_URL"
OPERACAO = "registrar-retirada"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


class PedidoRetirada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autorizacaoId: UUID


class RetiradaRegistrada(BaseModel):
    retiradaId: UUID
    autorizacaoId: UUID
    realizadaEm: AwareDatetime


class EstadoCanonico(BaseModel):
    reservaId: UUID
    status: EstadoReserva


class Autorizacao(BaseModel):
    autorizacaoId: UUID
    reservaId: UUID
    sagaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: int
    status: Literal["ATIVA", "CANCELADA", "UTILIZADA"]


def conflito(codigo: str, mensagem: str) -> tuple[int, dict]:
    return 409, {"codigo": codigo, "mensagem": mensagem}


def buscar_autorizacao(autorizacao_id: UUID):
    with conectar(BANCO) as conexao:
        return conexao.execute("SELECT reserva_id, unidade_id FROM autorizacoes WHERE autorizacao_id = %s",
                               (autorizacao_id,)).fetchone()


async def estado_da_reserva(request: Request, reserva_id: UUID, correlacao: UUID) -> str | None:
    """Estado canônico em Reservas; None se a reserva não existir e 503 se o resultado for inconclusivo."""
    token = os.environ.get("GLICO_RETIRADAS_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Credencial interna de Retiradas não configurada.")
    reservas = os.environ.get("RESERVAS_URL", "http://127.0.0.1:8004").rstrip("/")
    try:
        resposta = await consultar(
            request.app.state.http, f"{reservas}/internal/v1/reservas/{reserva_id}/estado",
            headers={"Authorization": f"Bearer {token}", "X-Correlation-Id": str(correlacao)},
        )
        if falha_de_configuracao(resposta):
            raise HTTPException(503)
        if resposta.status_code == 404:
            return None
        if resposta.status_code != 200:
            raise HTTPException(503)
        estado = EstadoCanonico.model_validate_json(resposta.content)
        if estado.reservaId != reserva_id:
            raise HTTPException(503)
        return estado.status
    except (HTTPException, ValidationError) as erro:
        raise HTTPException(503, "Não foi possível confirmar o estado da reserva; nenhuma entrega foi registrada.") from erro


def registrar(profissional: Ator, autorizacao_id: UUID, chave: str, resumo: str, correlacao: UUID):
    """Revalida a autorização travada e grava entrega, evento e resultado na mesma transação."""
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, OPERACAO, profissional.id, chave, resumo)) is not None:
            return anterior
        autorizacao = conexao.execute("""
            SELECT reserva_id, unidade_id, item_id, quantidade, cancelada_em
            FROM autorizacoes WHERE autorizacao_id = %s FOR UPDATE
        """, (autorizacao_id,)).fetchone()
        usada = conexao.execute("SELECT 1 FROM retiradas WHERE autorizacao_id = %s", (autorizacao_id,)).fetchone()
        if usada is not None:
            resultado = conflito("AUTORIZACAO_UTILIZADA", "A entrega desta autorização já foi registrada.")
        elif autorizacao["cancelada_em"] is not None:
            resultado = conflito("AUTORIZACAO_CANCELADA", "A autorização foi cancelada.")
        else:
            entrega = conexao.execute("""
                INSERT INTO retiradas (retirada_id, autorizacao_id, realizada_em, ator_id, correlation_id)
                VALUES (%s, %s, clock_timestamp(), %s, %s) RETURNING retirada_id, realizada_em
            """, (uuid4(), autorizacao_id, profissional.id, correlacao)).fetchone()
            gravar_outbox(conexao, RETIRADA_CONCLUIDA, "Retirada", entrega["retirada_id"], correlacao,
                          entrega["realizada_em"], {
                              "retiradaId": str(entrega["retirada_id"]), "reservaId": str(autorizacao["reserva_id"]),
                              "unidadeId": str(autorizacao["unidade_id"]), "itemId": str(autorizacao["item_id"]),
                              "quantidade": autorizacao["quantidade"]})
            resultado = 201, RetiradaRegistrada(
                retiradaId=entrega["retirada_id"], autorizacaoId=autorizacao_id, realizadaEm=entrega["realizada_em"],
            ).model_dump(mode="json")
        return gravar_resultado(conexao, OPERACAO, profissional.id, chave, resumo, resultado)


@rotas.post("/api/unidade/v1/retiradas", status_code=201, response_model=RetiradaRegistrada)
async def registrar_retirada(request: Request, pedido: PedidoRetirada, profissional: Profissional, chave: Chave,
                             correlacao: Correlacao = None):
    correlacao = correlacao or uuid4()
    resumo = resumir(pedido.autorizacaoId)
    anterior = await run_in_threadpool(reobter_resultado, BANCO, OPERACAO, profissional.id, chave, resumo)
    if anterior is not None:
        return responder(anterior)
    autorizacao = await run_in_threadpool(buscar_autorizacao, pedido.autorizacaoId)
    # As recusas desta etapa não são gravadas: uma nova tentativa refaz a consulta canônica.
    if autorizacao is None:
        return responder(conflito("AUTORIZACAO_INEXISTENTE", "A autorização não existe."))
    exigir_unidade(profissional, autorizacao["unidade_id"])
    estado = await estado_da_reserva(request, autorizacao["reserva_id"], correlacao)
    if estado != "CONFIRMADA":
        return responder(conflito("ESTADO_INCOMPATIVEL", f"A reserva está {estado or 'inexistente'}."))
    return responder(await run_in_threadpool(registrar, profissional, pedido.autorizacaoId, chave, resumo, correlacao))


@rotas.get("/internal/v1/autorizacoes/{reservaId}", response_model=Autorizacao)
def consultar_autorizacao(reservaId: UUID, profissional: Profissional):
    with conectar(BANCO) as conexao:
        linha = conexao.execute("""
            SELECT a.autorizacao_id AS "autorizacaoId", a.reserva_id AS "reservaId", a.saga_id AS "sagaId",
                   a.unidade_id AS "unidadeId", a.item_id AS "itemId", a.quantidade,
                   CASE WHEN r.retirada_id IS NOT NULL THEN 'UTILIZADA'
                        WHEN a.cancelada_em IS NOT NULL THEN 'CANCELADA' ELSE 'ATIVA' END AS status
            FROM autorizacoes a LEFT JOIN retiradas r USING (autorizacao_id) WHERE a.reserva_id = %s
        """, (reservaId,)).fetchone()
    if linha is None:
        raise HTTPException(404, "Não existe autorização para a reserva.")
    exigir_unidade(profissional, linha["unidadeId"])
    return linha
