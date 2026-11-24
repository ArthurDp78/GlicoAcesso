import os
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from servicos.banco import BancoIndisponivel, conectar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import orquestrador_autenticado


app = FastAPI(title="GlicoAcesso — Retiradas")
BANCO = "RETIRADAS_DATABASE_URL"
PRINCIPAL = "orquestrador"
Orquestrador = Annotated[str, Depends(orquestrador_autenticado)]
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
CAMPOS = """
    autorizacao_id AS "autorizacaoId", reserva_id AS "reservaId", saga_id AS "sagaId",
    unidade_id AS "unidadeId", item_id AS "itemId", quantidade,
    CASE WHEN cancelada_em IS NULL THEN 'ATIVA' ELSE 'CANCELADA' END AS status
"""


class PedidoAutorizacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID
    reservaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: Annotated[int, Field(strict=True, ge=1, le=2147483647)]


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco de Retiradas indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "retiradas", "status": "ok"}


def responder(resultado) -> JSONResponse:
    return JSONResponse(resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})


def json_autorizacao(linha) -> dict:
    return {chave: str(valor) if isinstance(valor, UUID) else valor for chave, valor in linha.items()}


def preparar(pedido: PedidoAutorizacao, chave: str, correlacao: UUID | None):
    resumo = sha256(pedido.model_dump_json().encode()).hexdigest()
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, "preparar-autorizacao", PRINCIPAL, chave, resumo)) is not None:
            return anterior
        existente = conexao.execute("SELECT 1 FROM autorizacoes WHERE reserva_id = %s", (pedido.reservaId,)).fetchone()
        if existente is not None:
            resultado = 409, {"codigo": "AUTORIZACAO_INCOMPATIVEL", "mensagem": "A reserva já tem autorização."}
        elif os.environ.get("GLICO_FALHA_PREPARAR_AUTORIZACAO") == "1":
            # Falha de negócio provocada para demonstrar a compensação da SAGA.
            resultado = 422, {"codigo": "AUTORIZACAO_NAO_CRIADA", "mensagem": "Preparação recusada (falha simulada)."}
        else:
            linha = conexao.execute(f"""
                INSERT INTO autorizacoes (autorizacao_id, reserva_id, saga_id, unidade_id, item_id, quantidade,
                    idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {CAMPOS}
            """, (uuid4(), pedido.reservaId, pedido.sagaId, pedido.unidadeId, pedido.itemId,
                  pedido.quantidade, chave, correlacao)).fetchone()
            resultado = 201, json_autorizacao(linha)
        return gravar_resultado(conexao, "preparar-autorizacao", PRINCIPAL, chave, resumo, resultado)


def cancelar(reserva_id: UUID, saga_id: UUID, chave: str):
    resumo = sha256(f"{reserva_id}:{saga_id}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, "cancelar-autorizacao", PRINCIPAL, chave, resumo)) is not None:
            return anterior
        # shortcut: sem a tabela de entregas, ENTREGA_JA_REGISTRADA ainda não ocorre; entra com o registro da retirada.
        linha = conexao.execute(f"""
            UPDATE autorizacoes SET cancelada_em = COALESCE(cancelada_em, now()), updated_at = now()
            WHERE reserva_id = %s RETURNING {CAMPOS}
        """, (reserva_id,)).fetchone()
        if linha is None:
            resultado = 404, {"codigo": "AUTORIZACAO_NAO_ENCONTRADA", "mensagem": "Não há autorização para a reserva."}
        else:
            resultado = 200, json_autorizacao(linha)
        return gravar_resultado(conexao, "cancelar-autorizacao", PRINCIPAL, chave, resumo, resultado)


@app.post("/internal/v1/autorizacoes", status_code=201)
def preparar_autorizacao(
    pedido: PedidoAutorizacao, _orquestrador: Orquestrador, chave: Chave,
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    return responder(preparar(pedido, chave, correlacao))


@app.post("/internal/v1/autorizacoes/{reservaId}/cancelar")
def cancelar_autorizacao(
    reservaId: UUID, _orquestrador: Orquestrador, chave: Chave,
    saga_id: Annotated[UUID, Header(alias="X-Saga-Id")],
):
    return responder(cancelar(reservaId, saga_id, chave))
