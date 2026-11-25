import os
import threading
from hashlib import sha256
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from servicos.banco import BancoIndisponivel, conectar
from servicos.contratos_reserva import JustificativaCancelamento
from servicos.contratos_retirada import EstadoCanonico
from servicos.delegacao_unidade import ator_cancelamento_delegado, profissional_delegado
from servicos.http import cliente_http, consultar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from pydantic import ValidationError
from servicos.identidade_demo import Ator, cabecalhos_ator
from servicos.mensageria import declarar_retiradas, iniciar_consumidor
from servicos.orquestrador.eventos import FILA, observar_retirada
from servicos.orquestrador.executor import laco, nova_etapa


@asynccontextmanager
async def ciclo(_app: FastAPI):
    parar = threading.Event()
    threading.Thread(target=laco, args=(parar,), name="executor-saga", daemon=True).start()
    iniciar_consumidor(FILA, declarar_retiradas, observar_retirada, parar)
    async with cliente_http(_app):
        try:
            yield
        finally:
            parar.set()


app = FastAPI(title="GlicoAcesso — Orquestrador da SAGA", lifespan=ciclo)
BANCO = "ORQUESTRADOR_DATABASE_URL"
OPERACAO = "solicitar-confirmacao"
PRIMEIRA_ETAPA = "ACEITAR_RESERVA"
Profissional = Annotated[Ator, Depends(profissional_delegado)]
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco do Orquestrador indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "orquestrador", "status": "ok"}


def erro(status: int, codigo: str, mensagem: str) -> JSONResponse:
    return JSONResponse({"codigo": codigo, "mensagem": mensagem}, status_code=status, headers={"Cache-Control": "no-store"})


def aceito(dados: dict) -> JSONResponse:
    return JSONResponse(dados, status_code=202, headers={
        "Location": f"/internal/v1/sagas/{dados['sagaId']}", "Cache-Control": "no-store",
    })


@app.post("/internal/v1/reservas/{reservaId}/confirmacoes", status_code=202)
def solicitar_confirmacao(
    reservaId: UUID, profissional: Profissional, chave: Chave,
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    if not chave.strip():
        raise HTTPException(422, "Chave idempotente vazia.")
    with conectar(BANCO) as conexao:
        controle = f"{OPERACAO}:{profissional.id}:{chave}"
        conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (controle,))
        anterior = conexao.execute("""
            SELECT request_hash, resposta FROM idempotencia_comandos
            WHERE operacao = %s AND principal_id = %s AND chave = %s
        """, (OPERACAO, profissional.id, chave)).fetchone()
        if anterior is not None:
            if anterior["request_hash"] != str(reservaId):
                return erro(409, "CHAVE_IDEMPOTENTE_CONFLITANTE", "Chave reutilizada com outra reserva.")
            return aceito(anterior["resposta"])
        saga_id = uuid4()
        try:
            with conexao.transaction():
                conexao.execute("""
                    INSERT INTO saga_execucoes (saga_id, reserva_id, correlation_id, tipo, estado,
                        ator_id, ator_unidade_id, etapa_atual, criada_em, atualizada_em)
                    VALUES (%s, %s, %s, 'CONFIRMACAO', 'EM_EXECUCAO', %s, %s, %s, now(), now())
                """, (saga_id, reservaId, correlacao or uuid4(), profissional.id, profissional.unidadeId, PRIMEIRA_ETAPA))
        except UniqueViolation:
            return erro(409, "EXECUCAO_CONCORRENTE", "Já existe uma execução ativa para esta reserva.")
        # Primeira intenção durável: o comando existe antes de qualquer chamada a Reservas.
        nova_etapa(conexao, saga_id, PRIMEIRA_ETAPA, "reservas", "POST", f"/internal/v1/reservas/{reservaId}/aceite",
                   {"sagaId": str(saga_id)}, {"X-Ator-Papel": profissional.papel, "X-Ator-Id": profissional.id,
                                              "X-Ator-Unidade-Id": str(profissional.unidadeId)})
        dados = {"sagaId": str(saga_id), "reservaId": str(reservaId)}
        conexao.execute("""
            INSERT INTO idempotencia_comandos (operacao, principal_id, chave, request_hash, http_status, resposta)
            VALUES (%s, %s, %s, %s, 202, %s)
        """, (OPERACAO, profissional.id, chave, str(reservaId), Jsonb(dados)))
    return aceito(dados)


@app.get("/internal/v1/sagas/{sagaId}")
def consultar_pedido(sagaId: UUID, ator: Annotated[Ator, Depends(ator_cancelamento_delegado)]):
    with conectar(BANCO) as conexao:
        execucao = conexao.execute("""
            SELECT saga_id AS "sagaId", reserva_id AS "reservaId", tipo, estado AS "estadoExecucao",
                motivo_encerramento AS "motivoEncerramento", ator_id
            FROM saga_execucoes WHERE saga_id = %s
        """, (sagaId,)).fetchone()
    if execucao is None:
        raise HTTPException(404, "Pedido não encontrado.")
    if execucao.pop("ator_id") != ator.id:
        raise HTTPException(403, "Pedido de outro ator.")
    return {chave: valor for chave, valor in execucao.items() if valor is not None}


CANCELAR = "solicitar-cancelamento"
AtorCancelamento = Annotated[Ator, Depends(ator_cancelamento_delegado)]


def ver_pedido_cancelamento(principal, chave, resumo):
    with conectar(BANCO) as conexao:
        return resultado_anterior(conexao, CANCELAR, principal, chave, resumo)


def agendar_cancelamento(reserva_id, ator, principal, chave, resumo, justificativa, correlacao, falha):
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, CANCELAR, principal, chave, resumo)
        if anterior is not None:
            return anterior
        if falha is not None:
            return falha

        saga_id = uuid4()
        try:
            with conexao.transaction():
                conexao.execute("""
                    INSERT INTO saga_execucoes (saga_id, reserva_id, correlation_id, tipo, estado,
                        ator_id, ator_unidade_id, criada_em, atualizada_em)
                    VALUES (%s, %s, %s, 'CANCELAMENTO', 'AGUARDANDO_CONFIRMACAO', %s, %s, now(), now())
                """, (saga_id, reserva_id, correlacao or uuid4(), ator.id, ator.unidadeId))
        except UniqueViolation:
            return 409, {"codigo": "EXECUCAO_CONCORRENTE", "mensagem": "Já existe cancelamento para esta reserva."}
        corpo = {"sagaId": str(saga_id)}
        if justificativa is not None:
            corpo["justificativa"] = justificativa
        nova_etapa(conexao, saga_id, "INICIAR_CANCELAMENTO", "reservas", "POST",
                   f"/internal/v1/reservas/{reserva_id}/iniciar-cancelamento", corpo, cabecalhos_ator(ator))
        return gravar_resultado(conexao, CANCELAR, principal, chave, resumo, (
            202, {"sagaId": str(saga_id), "reservaId": str(reserva_id)},
        ))


async def validar_pedido_cancelamento(request, reserva_id, ator):
    origem = os.getenv("RESERVAS_URL", "http://127.0.0.1:8004").rstrip("/")
    token = os.getenv("GLICO_ORQUESTRADOR_SERVICE_TOKEN", "")
    try:
        resposta = await consultar(
            request.app.state.http, f"{origem}/internal/v1/reservas/{reserva_id}/permissao-cancelamento",
            headers={"Authorization": "Bearer " + token, **cabecalhos_ator(ator)},
        )
        if resposta.status_code in (403, 404):
            return resposta.status_code, {"codigo": "ACESSO_NEGADO", "mensagem": "Reserva indisponível para o ator."}
        if resposta.status_code == 200:
            estado = EstadoCanonico.model_validate_json(resposta.content)
            if estado.reservaId == reserva_id:
                if estado.status in ("EM_CONFIRMACAO", "CONFIRMADA"):
                    return None
                return 409, {"codigo": "ESTADO_INCOMPATIVEL", "mensagem": "A reserva não pode ser cancelada."}
    except (HTTPException, ValidationError):
        pass
    return 503, {"codigo": "RESERVAS_INDISPONIVEL", "mensagem": "Não foi possível verificar a reserva."}


@app.post("/internal/v1/reservas/{reservaId}/cancelamentos", status_code=202)
async def solicitar_cancelamento(
    request: Request, reservaId: UUID, ator: AtorCancelamento, chave: Chave,
    pedido: JustificativaCancelamento | None = None,
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    if not chave.strip() or "\x00" in chave:
        raise HTTPException(422, "Chave idempotente inválida.")
    if (ator.papel == "PROFISSIONAL") != (pedido is not None):
        raise HTTPException(422, "Justificativa incompatível com o papel.")
    justificativa = pedido.justificativa if pedido else None
    principal = f"{ator.papel}:{ator.id}"
    resumo = sha256(str((reservaId, ator.unidadeId, justificativa)).encode()).hexdigest()
    resultado = await run_in_threadpool(ver_pedido_cancelamento, principal, chave, resumo)
    if resultado is None:
        falha = await validar_pedido_cancelamento(request, reservaId, ator)
        resultado = await run_in_threadpool(
            agendar_cancelamento, reservaId, ator, principal, chave, resumo, justificativa, correlacao, falha,
        )
    status, dados = resultado
    if status == 202:
        return aceito(dados)
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})
