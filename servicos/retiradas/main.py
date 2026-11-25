import os
import threading
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from servicos.banco import BancoIndisponivel, conectar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.contratos_retirada import Autorizacao, EstadoCanonico, PedidoRetirada, RetiradaRegistrada
from servicos.http import cliente_http, consultar, correlacao, correlacionar
from servicos.identidade_demo import Ator, orquestrador_autenticado, profissional_autenticado


from servicos.mensageria import declarar_retiradas, iniciar_publicador


BANCO = "RETIRADAS_DATABASE_URL"


@asynccontextmanager
async def ciclo(app: FastAPI):
    parar = threading.Event()
    async with cliente_http(app):
        iniciar_publicador(BANCO, declarar_retiradas, parar)
        try:
            yield
        finally:
            parar.set()


app = FastAPI(title="GlicoAcesso — Retiradas", lifespan=ciclo)
app.middleware("http")(correlacionar)
PRINCIPAL = "orquestrador"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]
REGISTRAR = "registrar-retirada"
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
                ON CONFLICT (reserva_id) DO NOTHING
                RETURNING {CAMPOS}
            """, (uuid4(), pedido.reservaId, pedido.sagaId, pedido.unidadeId, pedido.itemId,
                  pedido.quantidade, chave, correlacao)).fetchone()
            if linha is None:
                resultado = conflito("AUTORIZACAO_INCOMPATIVEL", "A reserva já tem autorização.")
            else:
                resultado = 201, json_autorizacao(linha)
        return gravar_resultado(conexao, "preparar-autorizacao", PRINCIPAL, chave, resumo, resultado)


def cancelar(reserva_id: UUID, saga_id: UUID, chave: str):
    resumo = sha256(f"{reserva_id}:{saga_id}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, "cancelar-autorizacao", PRINCIPAL, chave, resumo)) is not None:
            return anterior
        autorizacao = conexao.execute(
            "SELECT autorizacao_id FROM autorizacoes WHERE reserva_id = %s FOR UPDATE", (reserva_id,),
        ).fetchone()
        if autorizacao is None:
            resultado = 404, {"codigo": "AUTORIZACAO_NAO_ENCONTRADA", "mensagem": "Não há autorização para a reserva."}
        elif (entrega := entrega_da_autorizacao(conexao, autorizacao["autorizacao_id"])) is not None:
            resultado = entrega_ja_registrada(entrega)
        else:
            linha = conexao.execute(f"""
                UPDATE autorizacoes SET cancelada_em = COALESCE(cancelada_em, now()), updated_at = now()
                WHERE reserva_id = %s RETURNING {CAMPOS}
            """, (reserva_id,)).fetchone()
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


def conflito(codigo: str, mensagem: str):
    return 409, {"codigo": codigo, "mensagem": mensagem}


def entrega_da_autorizacao(conexao, autorizacao_id: UUID):
    return conexao.execute(
        'SELECT retirada_id AS "retiradaId" FROM entregas WHERE autorizacao_id = %s', (autorizacao_id,),
    ).fetchone()


def entrega_ja_registrada(entrega):
    return 409, {
        "codigo": "ENTREGA_JA_REGISTRADA",
        "mensagem": "A entrega já foi registrada.",
        "retiradaId": str(entrega["retiradaId"]),
    }


@app.get("/internal/v1/autorizacoes/{reservaId}", response_model=Autorizacao)
def consultar_autorizacao(reservaId: UUID, profissional: Profissional):
    with conectar(BANCO) as conexao:
        linha = conexao.execute("""
            SELECT a.autorizacao_id AS "autorizacaoId", a.reserva_id AS "reservaId", a.saga_id AS "sagaId",
                   a.unidade_id AS "unidadeId", a.item_id AS "itemId", a.quantidade,
                   CASE WHEN e.retirada_id IS NOT NULL THEN 'UTILIZADA'
                        WHEN a.cancelada_em IS NOT NULL THEN 'CANCELADA' ELSE 'ATIVA' END AS status
            FROM autorizacoes a LEFT JOIN entregas e USING (autorizacao_id)
            WHERE a.reserva_id = %s
        """, (reservaId,)).fetchone()
    if linha is None:
        raise HTTPException(404, "Autorização não encontrada.")
    if linha["unidadeId"] != profissional.unidadeId:
        raise HTTPException(403, "Autorização de outra unidade.")
    return responder((200, Autorizacao.model_validate(linha).model_dump(mode="json")))


def verificar_autorizacao(conexao, autorizacao_id, profissional, *, travar=False):
    comando = f"SELECT {CAMPOS} FROM autorizacoes WHERE autorizacao_id = %s"
    if travar:
        comando += " FOR UPDATE"
    autorizacao = conexao.execute(comando, (autorizacao_id,)).fetchone()
    if autorizacao is None:
        return None, conflito("AUTORIZACAO_NAO_ENCONTRADA", "Autorização não encontrada.")
    if autorizacao["unidadeId"] != profissional.unidadeId:
        raise HTTPException(403, "Autorização de outra unidade.")
    if autorizacao["status"] == "CANCELADA":
        return None, conflito("AUTORIZACAO_CANCELADA", "A autorização foi revogada.")
    # Com o bloqueio, a consulta separada enxerga a entrega de uma transação que acabou de concluir.
    entrega = entrega_da_autorizacao(conexao, autorizacao_id)
    if entrega is not None:
        return None, entrega_ja_registrada(entrega)
    return autorizacao, None


def preparar_registro(autorizacao_id, profissional, chave, resumo):
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, REGISTRAR, profissional.id, chave, resumo)
        if anterior is not None:
            return None, anterior
        return verificar_autorizacao(conexao, autorizacao_id, profissional)


async def verificar_estado(request, reserva_id):
    origem = os.getenv("RESERVAS_URL", "http://127.0.0.1:8004").rstrip("/")
    token = os.getenv("GLICO_RETIRADAS_SERVICE_TOKEN", "")
    indisponivel = 503, {"codigo": "ESTADO_INDISPONIVEL", "mensagem": "Não foi possível verificar a reserva."}
    if len(token) < 32:
        return indisponivel
    try:
        resposta = await consultar(
            request.app.state.http, f"{origem}/internal/v1/reservas/{reserva_id}/estado",
            headers={"Authorization": "Bearer " + token},
        )
        if resposta.status_code == 404:
            return conflito("RESERVA_NAO_ENCONTRADA", "A reserva da autorização não foi encontrada.")
        if resposta.status_code != 200:
            return indisponivel
        estado = EstadoCanonico.model_validate_json(resposta.content)
    except (HTTPException, ValidationError):
        return indisponivel
    if estado.reservaId != reserva_id:
        return indisponivel
    if estado.status != "CONFIRMADA":
        return conflito("RESERVA_NAO_CONFIRMADA", "A reserva precisa estar confirmada.")
    return None


def persistir_entrega(autorizacao_id, profissional, chave, resumo, estado_invalido):
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, REGISTRAR, profissional.id, chave, resumo)
        if anterior is not None:
            return anterior
        autorizacao, conflito_local = verificar_autorizacao(conexao, autorizacao_id, profissional, travar=True)
        if conflito_local or estado_invalido:
            return conflito_local or estado_invalido

        retirada_id = uuid4()
        entrega = conexao.execute("""
            INSERT INTO entregas (retirada_id, autorizacao_id, profissional_id)
            VALUES (%s, %s, %s) RETURNING realizada_em
        """, (retirada_id, autorizacao_id, profissional.id)).fetchone()
        realizada_em = entrega["realizada_em"]
        evento = {campo: str(autorizacao[campo]) for campo in ("reservaId", "unidadeId", "itemId")}
        evento.update(retiradaId=str(retirada_id), quantidade=autorizacao["quantidade"])
        conexao.execute("""
            INSERT INTO outbox (event_id, event_type, event_version, aggregate_type, aggregate_id,
                                correlation_id, occurred_at, payload)
            VALUES (%s, 'retirada.concluida.v1', 1, 'Retirada', %s, %s, %s, %s)
        """, (uuid4(), str(retirada_id), correlacao.get() or uuid4(), realizada_em, Jsonb(evento)))
        resposta = RetiradaRegistrada(retiradaId=retirada_id, autorizacaoId=autorizacao_id, realizadaEm=realizada_em)
        return gravar_resultado(conexao, REGISTRAR, profissional.id, chave, resumo, (201, resposta.model_dump(mode="json")))


@app.post("/api/unidade/v1/retiradas", status_code=201, response_model=RetiradaRegistrada)
async def registrar_retirada(request: Request, pedido: PedidoRetirada, profissional: Profissional, chave: Chave):
    if not chave.strip() or "\x00" in chave:
        raise HTTPException(422, "Chave idempotente inválida.")
    resumo = sha256(f"{profissional.unidadeId}:{pedido.autorizacaoId}".encode()).hexdigest()
    autorizacao, anterior = await run_in_threadpool(
        preparar_registro, pedido.autorizacaoId, profissional, chave, resumo,
    )
    if anterior is not None:
        return responder(anterior)
    estado_invalido = await verificar_estado(request, autorizacao["reservaId"])
    resultado = await run_in_threadpool(
        persistir_entrega, pedido.autorizacaoId, profissional, chave, resumo, estado_invalido,
    )
    return responder(resultado)
