from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from servicos.banco import BancoIndisponivel, conectar
from servicos.identidade_demo import Ator, profissional_autenticado


app = FastAPI(title="GlicoAcesso — Orquestrador da SAGA")
BANCO = "ORQUESTRADOR_DATABASE_URL"
OPERACAO = "solicitar-confirmacao"
PRIMEIRA_ETAPA = "ACEITAR_RESERVA"
# shortcut: o BFF repassa o Bearer do profissional e o Orquestrador o valida; trocar por token delegado assinado
# (credencial do BFF + ator) quando houver provedor de identidade.
Profissional = Annotated[Ator, Depends(profissional_autenticado)]
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
        # Primeira intenção durável: a etapa existe antes de qualquer chamada a Reservas (2.7).
        conexao.execute("""
            INSERT INTO saga_etapas (saga_id, etapa_id, operacao, destino, idempotency_key, estado_tecnico,
                dados_comando, proximo_retry_em, criada_em, atualizada_em)
            VALUES (%s, %s, 'aceitarReserva', 'reservas', %s, 'PENDENTE', %s, now(), now(), now())
        """, (saga_id, PRIMEIRA_ETAPA, f"{saga_id}:{PRIMEIRA_ETAPA}", Jsonb({"sagaId": str(saga_id)})))
        dados = {"sagaId": str(saga_id), "reservaId": str(reservaId)}
        conexao.execute("""
            INSERT INTO idempotencia_comandos (operacao, principal_id, chave, request_hash, http_status, resposta)
            VALUES (%s, %s, %s, %s, 202, %s)
        """, (OPERACAO, profissional.id, chave, str(reservaId), Jsonb(dados)))
    return aceito(dados)


@app.get("/internal/v1/sagas/{sagaId}")
def consultar_pedido(sagaId: UUID, profissional: Profissional):
    with conectar(BANCO) as conexao:
        execucao = conexao.execute("""
            SELECT saga_id AS "sagaId", reserva_id AS "reservaId", tipo, estado AS "estadoExecucao",
                motivo_encerramento AS "motivoEncerramento", ator_id
            FROM saga_execucoes WHERE saga_id = %s
        """, (sagaId,)).fetchone()
    if execucao is None:
        raise HTTPException(404, "Pedido não encontrado.")
    if execucao.pop("ator_id") != profissional.id:
        raise HTTPException(403, "Pedido de outro ator.")
    return {chave: valor for chave, valor in execucao.items() if valor is not None}
