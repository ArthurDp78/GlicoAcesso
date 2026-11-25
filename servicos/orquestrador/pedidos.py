"""Recepção e consulta de pedidos de cancelamento distribuído."""
import os
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict

from servicos.banco import conectar
from servicos.comandos import RASTREADO, Chave, Correlacao, Justificativa, NaoNulo, resumir
from servicos.http import falha_de_configuracao
from servicos.idempotencia import gravar_resultado, reobter_resultado, resultado_anterior
from servicos.identidade_demo import Ator, AtorDelegado, cabecalhos_do_ator
from servicos.orquestrador.cancelamento import iniciar_execucao
from servicos.orquestrador.registro import BANCO


rotas = APIRouter()
OPERACAO = "solicitar-cancelamento"


class PedidoCancelamento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    justificativa: Annotated[Justificativa | None, NaoNulo] = None


def erro(status: int, codigo: str, mensagem: str) -> JSONResponse:
    return JSONResponse({"codigo": codigo, "mensagem": mensagem}, status_code=status, headers={"Cache-Control": "no-store"})


def aceito(dados: dict) -> JSONResponse:
    return JSONResponse(dados, status_code=202, headers={
        "Location": f"/internal/v1/sagas/{dados['sagaId']}", "Cache-Control": "no-store",
    })


def responder(resultado: tuple[int, dict]) -> JSONResponse:
    return aceito(resultado[1]) if resultado[0] == 202 else JSONResponse(
        resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})


def consultar_permissao(reserva_id: UUID, ator: Ator, correlacao: UUID) -> str:
    """Estado canônico da reserva, se o ator puder cancelá-la."""
    url = os.environ.get("RESERVAS_URL", "http://127.0.0.1:8004").rstrip("/")
    try:
        # Prazo menor que o do BFF, para que a indisponibilidade chegue a ele como 503.
        resposta = httpx.get(
            f"{url}/internal/v1/reservas/{reserva_id}/permissao-cancelamento", timeout=3.0, trust_env=False, headers={
                "Authorization": "Bearer " + os.environ.get("GLICO_ORQUESTRADOR_SERVICE_TOKEN", ""),
                "X-Correlation-Id": str(correlacao), **cabecalhos_do_ator(ator.papel, ator.id, ator.unidadeId)})
        if falha_de_configuracao(resposta):
            raise HTTPException(503, "Não foi possível verificar a permissão em Reservas.")
        if resposta.status_code == 403:
            raise HTTPException(403, "Ator sem acesso à reserva.")
        if resposta.status_code == 404:
            raise HTTPException(404, "Reserva não encontrada.")
        resposta.raise_for_status()
        return str(resposta.json()["status"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as falha:
        raise HTTPException(503, "Não foi possível verificar a permissão em Reservas.") from falha


def registrar(reserva_id: UUID, ator: Ator, justificativa: str | None, chave: str, resumo: str, correlacao: UUID):
    """Grava pedido, intenção e resultado idempotente na mesma transação."""
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, OPERACAO, ator.id, chave, resumo)) is not None:
            return anterior
        saga_id = uuid4()
        ativa = conexao.execute("""
            SELECT saga_id, tipo FROM saga_execucoes WHERE reserva_id = %s AND encerrada_em IS NULL
        """, (reserva_id,)).fetchone()
        concorrente = 409, {"codigo": "EXECUCAO_CONCORRENTE", "mensagem": "Já existe um cancelamento para esta reserva."}
        if ativa is not None and ativa["tipo"] == "CANCELAMENTO":
            return concorrente
        aberto = conexao.execute("""
            SELECT 1 FROM saga_pedidos_cancelamento WHERE reserva_id = %s AND fase IN ('PENDENTE', 'EM_TRANSICAO')
        """, (reserva_id,)).fetchone()
        if aberto is not None:
            return concorrente
        try:
            with conexao.transaction():
                if ativa is None:
                    iniciar_execucao(conexao, saga_id, reserva_id, correlacao, ator.papel, ator.id, ator.unidadeId, justificativa)
                else:
                    conexao.execute("""
                        INSERT INTO saga_pedidos_cancelamento (saga_id_solicitado, reserva_id, correlation_id,
                            saga_confirmacao_id, ator_papel, ator_id, ator_unidade_id, justificativa)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (saga_id, reserva_id, correlacao, ativa["saga_id"], ator.papel, ator.id, ator.unidadeId, justificativa))
        except UniqueViolation:
            return concorrente
        resultado = 202, {"sagaId": str(saga_id), "reservaId": str(reserva_id)}
        return gravar_resultado(conexao, OPERACAO, ator.id, chave, resumo, resultado)


@rotas.post("/internal/v1/reservas/{reservaId}/cancelamentos", status_code=202)
def solicitar_cancelamento(reservaId: UUID, ator: AtorDelegado, chave: Chave,
                           pedido: PedidoCancelamento | None = None, correlacao: Correlacao = None):
    justificativa = pedido.justificativa if pedido else None
    if ator.papel == "PROFISSIONAL" and justificativa is None:
        return erro(400, "ENTRADA_INVALIDA", "A justificativa é obrigatória para o profissional.")
    if ator.papel == "CIDADAO" and justificativa is not None:
        return erro(400, "ENTRADA_INVALIDA", "O cancelamento pelo cidadão não recebe justificativa.")
    resumo = resumir(reservaId, justificativa or "")
    anterior = reobter_resultado(BANCO, OPERACAO, ator.id, chave, resumo)
    if anterior is not None:
        return responder(anterior)
    correlacao = correlacao or uuid4()
    estado = consultar_permissao(reservaId, ator, correlacao)
    if estado not in ("EM_CONFIRMACAO", "CONFIRMADA"):
        return erro(409, "ESTADO_INCOMPATIVEL", f"A reserva está {estado}.")
    return responder(registrar(reservaId, ator, justificativa, chave, resumo, correlacao))


@rotas.get("/internal/v1/sagas/{sagaId}", dependencies=RASTREADO)
def consultar_pedido(sagaId: UUID, ator: AtorDelegado):
    with conectar(BANCO) as conexao:
        # Um pedido ainda não ativado ou recusado não tem execução própria nem estado técnico.
        pedido = conexao.execute("""
            SELECT saga_id AS "sagaId", reserva_id AS "reservaId", tipo, estado AS "estadoExecucao",
                motivo_encerramento AS "motivoEncerramento", ator_papel, ator_id
            FROM saga_execucoes WHERE saga_id = %(saga)s
            UNION ALL
            SELECT saga_id_solicitado, reserva_id, 'CANCELAMENTO', NULL, motivo_encerramento, ator_papel, ator_id
            FROM saga_pedidos_cancelamento WHERE saga_id_solicitado = %(saga)s AND fase <> 'ATIVADO'
        """, {"saga": sagaId}).fetchone()
    if pedido is None:
        raise HTTPException(404, "Pedido não encontrado.")
    if (pedido.pop("ator_papel"), pedido.pop("ator_id")) != (ator.papel, ator.id):
        raise HTTPException(403, "Pedido de outro ator.")
    return {chave: valor for chave, valor in pedido.items() if valor is not None}
