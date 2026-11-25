import threading
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from servicos import mensageria
from servicos.banco import BancoIndisponivel, conectar
from servicos.erros import entrada_invalida_400
from servicos.identidade_demo import Ator, profissional_autenticado
from servicos.orquestrador import pedidos
from servicos.orquestrador.cancelamento import processar_retirada
from servicos.orquestrador.executor import laco
from servicos.orquestrador.pedidos import aceito, erro
from servicos.orquestrador.registro import BANCO, nova_etapa


@asynccontextmanager
async def ciclo(_app: FastAPI):
    parar = threading.Event()
    threading.Thread(target=laco, args=(parar,), name="executor-saga", daemon=True).start()
    mensageria.iniciar({
        "retirada-orquestrador": mensageria.consumidor(mensageria.FILA_RETIRADA_ORQUESTRADOR, processar_retirada),
    }, parar)
    yield
    parar.set()


app = FastAPI(title="GlicoAcesso — Orquestrador da SAGA", lifespan=ciclo)
app.include_router(pedidos.rotas)
entrada_invalida_400(app, "/internal/v1/reservas/{reservaId}/confirmacoes", "/internal/v1/reservas/{reservaId}/cancelamentos")
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


@app.post("/internal/v1/reservas/{reservaId}/confirmacoes", status_code=202)
def solicitar_confirmacao(
    reservaId: UUID, profissional: Profissional, chave: Chave,
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    if not chave.strip():
        raise HTTPException(400, "Chave idempotente vazia.")
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
