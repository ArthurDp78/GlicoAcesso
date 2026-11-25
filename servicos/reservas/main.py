import os
import threading
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from servicos.banco import BancoIndisponivel, conectar
from servicos.comandos import RASTREADO
from servicos.contratos_reserva import PedidoReserva, ReservaInterna
from servicos.erros import entrada_invalida_400
from servicos.http import cliente_http, consultar, falha_de_configuracao
from servicos.idempotencia import reobter_resultado
from servicos.identidade_demo import (
    Ator, AtorAutenticado, ator_delegado, cidadao_autenticado, orquestrador_autenticado, profissional_autenticado,
    retiradas_autenticado,
)
from servicos.reservas import cancelamento, segundo_plano


@asynccontextmanager
async def ciclo(app: FastAPI):
    parar = threading.Event()
    segundo_plano.iniciar(parar)  # Expiração por prazo e consumo da retirada concluída.
    async with cliente_http(app):
        yield
    parar.set()


app = FastAPI(title="GlicoAcesso — Reservas", lifespan=ciclo)
app.include_router(cancelamento.rotas)
COMANDOS_INTERNOS = "/internal/v1/reservas/{reservaId}"
entrada_invalida_400(
    app, "/api/unidade/v1/reservas/{reservaId}/decisao", "/api/unidade/v1/reservas/{reservaId}/cancelar",
    "/api/cidadao/v1/reservas/{reservaId}/cancelar",
    *(f"{COMANDOS_INTERNOS}/{comando}" for comando in
      ("aceite", "confirmar", "falhar-confirmacao", "iniciar-cancelamento", "finalizar-cancelamento")),
)
BANCO = "RESERVAS_DATABASE_URL"
OPERACAO = "criar-reserva"
Cidadao = Annotated[str, Depends(cidadao_autenticado)]
Profissional = Annotated[Ator, Depends(profissional_autenticado)]
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
CAMPOS = """
    reserva_id AS "reservaId", cidadao_id AS "cidadaoId",
    unidade_id AS "unidadeId", item_id AS "itemId", quantidade, status,
    criada_em AS "criadaEm", decisao_ate AS "decisaoAte"
"""


class UnidadeParaReserva(BaseModel):
    unidadeId: UUID
    ativa: bool
    prazoAnaliseHoras: Annotated[int, Field(gt=0)]


class Permissao(BaseModel):
    unidadeId: UUID
    itemId: UUID
    permiteReserva: bool


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco de Reservas indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "reservas", "status": "ok"}


def reobter(conexao, cidadao: str, chave: str, resumo: str) -> ReservaInterna | None:
    entrada = conexao.execute("""
        SELECT request_hash, resposta FROM idempotencia_comandos
        WHERE operacao = %s AND principal_id = %s AND chave = %s
    """, (OPERACAO, cidadao, chave)).fetchone()
    if entrada is None:
        return None
    if entrada["request_hash"] != resumo:
        raise HTTPException(409, "Chave idempotente reutilizada com conteúdo diferente.")
    return ReservaInterna.model_validate(entrada["resposta"])


def reobter_antes_da_validacao(cidadao: str, chave: str, resumo: str) -> ReservaInterna | None:
    with conectar(BANCO) as conexao:
        return reobter(conexao, cidadao, chave, resumo)


async def verificar_dependencia(cliente, url: str, token: str, modelo):
    try:
        resposta = await consultar(cliente, url, headers={"Authorization": f"Bearer {token}"})
    except HTTPException as erro:
        raise HTTPException(503, "Não foi possível validar a unidade ou a permissão de reserva.") from erro
    if resposta.status_code == 404 and not falha_de_configuracao(resposta):
        return None
    if resposta.status_code != 200:
        raise HTTPException(503, "Não foi possível validar a unidade ou a permissão de reserva.")
    try:
        return modelo.model_validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(503, "A validação retornou dados incompatíveis.") from erro


def token_interno() -> str:
    token = os.environ.get("GLICO_RESERVAS_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Credencial interna de Reservas não configurada.")
    return token


async def unidade_ativa(request: Request, unidade_id: UUID) -> UnidadeParaReserva | None:
    unidades = os.environ.get("UNIDADES_URL", "http://127.0.0.1:8002").rstrip("/")
    unidade = await verificar_dependencia(
        request.app.state.http, f"{unidades}/internal/v1/unidades/{unidade_id}", token_interno(), UnidadeParaReserva
    )
    if unidade is None or unidade.unidadeId != unidade_id or not unidade.ativa:
        return None
    return unidade


async def verificar_vinculo(request: Request, profissional: Ator) -> UUID:
    if await unidade_ativa(request, profissional.unidadeId) is None:
        raise HTTPException(403, "Profissional sem unidade ativa vinculada.")
    return profissional.unidadeId


async def verificar_pedido(request: Request, pedido: PedidoReserva) -> int:
    token = token_interno()
    estoque = os.environ.get("ESTOQUE_URL", "http://127.0.0.1:8003").rstrip("/")
    cliente = request.app.state.http
    unidade = await unidade_ativa(request, pedido.unidadeId)
    if unidade is None:
        raise HTTPException(422, "Unidade inexistente ou inativa.")
    permissao = await verificar_dependencia(
        cliente, f"{estoque}/internal/v1/unidades/{pedido.unidadeId}/itens/{pedido.itemId}/permissao-reserva",
        token, Permissao,
    )
    if (permissao is None or permissao.unidadeId != pedido.unidadeId
            or permissao.itemId != pedido.itemId or not permissao.permiteReserva):
        raise HTTPException(422, "A unidade não permite a reserva deste item.")
    return unidade.prazoAnaliseHoras


def persistir(cidadao: str, chave: str, resumo: str, pedido: PedidoReserva, prazo: int):
    with conectar(BANCO) as conexao:
        # O bloqueio dura só a transação local. Nenhuma chamada HTTP ocorre aqui.
        controle = f"{OPERACAO}:{cidadao}:{chave}"
        conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (controle,))
        anterior = reobter(conexao, cidadao, chave, resumo)
        if anterior is not None:
            return anterior
        dados = conexao.execute(f"""
            INSERT INTO reservas (reserva_id, cidadao_id, unidade_id, item_id, quantidade,
                status, prazo_analise_horas, criada_em, decisao_ate, atualizada_em, idempotency_key)
            VALUES (%s, %s, %s, %s, %s, 'SOLICITADA', %s,
                now(), now() + make_interval(hours => %s), now(), %s)
            RETURNING {CAMPOS}
        """, (uuid4(), cidadao, pedido.unidadeId, pedido.itemId, pedido.quantidade, prazo, prazo, chave)).fetchone()
        reserva = ReservaInterna.model_validate(dados)
        conexao.execute("""
            INSERT INTO historico_reserva
                (historico_id, reserva_id, status_posterior, ocorrido_em, ator_id)
            VALUES (%s, %s, 'SOLICITADA', %s, %s)
        """, (uuid4(), reserva.reservaId, reserva.criadaEm, cidadao))
        conexao.execute("""
            INSERT INTO idempotencia_comandos
                (operacao, principal_id, chave, request_hash, http_status, resposta)
            VALUES (%s, %s, %s, %s, 201, %s)
        """, (OPERACAO, cidadao, chave, resumo, Jsonb(reserva.model_dump(mode="json"))))
        return reserva


@app.post("/api/cidadao/v1/reservas", status_code=201, response_model=ReservaInterna)
async def criar(request: Request, response: Response, pedido: PedidoReserva, cidadao: Cidadao, chave: Chave):
    response.headers["Cache-Control"] = "no-store"
    if not chave.strip():
        raise HTTPException(422, "Chave idempotente vazia.")
    resumo = sha256(pedido.model_dump_json().encode()).hexdigest()
    anterior = await run_in_threadpool(reobter_antes_da_validacao, cidadao, chave, resumo)
    if anterior is not None:
        return anterior
    prazo = await verificar_pedido(request, pedido)
    return await run_in_threadpool(persistir, cidadao, chave, resumo, pedido, prazo)


def buscar_reserva(reserva_id: UUID):
    with conectar(BANCO) as conexao:
        return conexao.execute(f"SELECT {CAMPOS} FROM reservas WHERE reserva_id = %s", (reserva_id,)).fetchone()


@app.get("/internal/v1/reservas/{reservaId}", response_model=ReservaInterna)
async def consultar_reserva(request: Request, reservaId: UUID, ator: AtorAutenticado, response: Response):
    response.headers["Cache-Control"] = "no-store"
    unidade = await verificar_vinculo(request, ator) if ator.papel == "PROFISSIONAL" else None
    registro = await run_in_threadpool(buscar_reserva, reservaId)
    if ator.papel == "CIDADAO":
        # Reserva alheia e inexistente são indistinguíveis para o cidadão.
        if registro is None or registro["cidadaoId"] != ator.id:
            raise HTTPException(404, "Reserva não encontrada.")
        return registro
    if registro is None:
        raise HTTPException(404, "Reserva não encontrada.")
    if registro["unidadeId"] != unidade:
        raise HTTPException(403, "Reserva de outra unidade.")
    return registro


@app.get("/internal/v1/reservas/{reservaId}/estado", dependencies=[Depends(retiradas_autenticado), *RASTREADO])
def consultar_estado(reservaId: UUID):
    registro = buscar_reserva(reservaId)
    if registro is None:
        raise HTTPException(404, "Reserva não encontrada.")
    return responder((200, {"reservaId": str(reservaId), "status": registro["status"]}))


def listar_pendentes_da_unidade(unidade_id: UUID):
    with conectar(BANCO) as conexao:
        return conexao.execute(f"""
            SELECT {CAMPOS} FROM reservas
            WHERE unidade_id = %s AND status = 'SOLICITADA'
            ORDER BY decisao_ate, reserva_id
        """, (unidade_id,)).fetchall()


@app.get("/api/unidade/v1/reservas", response_model=list[ReservaInterna])
async def listar_pendentes(request: Request, profissional: Profissional, response: Response):
    response.headers["Cache-Control"] = "no-store"
    unidade = await verificar_vinculo(request, profissional)
    return await run_in_threadpool(listar_pendentes_da_unidade, unidade)


class Decisao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisao: Literal["ACEITAR", "REJEITAR"]


OPERACAO_DECISAO = "decisao-unidade"


def conflito(codigo: str, mensagem: str) -> tuple[int, dict]:
    return 409, {"codigo": codigo, "mensagem": mensagem}


def registrar_decisao(profissional: str, unidade: UUID, reserva_id: UUID, decisao: str, chave: str):
    resumo = sha256(f"{reserva_id}:{decisao}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        controle = f"{OPERACAO_DECISAO}:{profissional}:{chave}"
        conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (controle,))
        anterior = conexao.execute("""
            SELECT request_hash, http_status, resposta FROM idempotencia_comandos
            WHERE operacao = %s AND principal_id = %s AND chave = %s
        """, (OPERACAO_DECISAO, profissional, chave)).fetchone()
        if anterior is not None:
            if anterior["request_hash"] != resumo:
                return conflito("CHAVE_IDEMPOTENTE_CONFLITANTE", "Chave reutilizada com outra reserva ou decisão.")
            return anterior["http_status"], anterior["resposta"]
        reserva = conexao.execute("""
            SELECT unidade_id, status, decisao_ate > now() AS no_prazo
            FROM reservas WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if reserva is None:
            raise HTTPException(404, "Reserva não encontrada.")
        if reserva["unidade_id"] != unidade:
            raise HTTPException(403, "Reserva de outra unidade.")
        if reserva["status"] != "SOLICITADA":
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {reserva['status']}.")
        elif not reserva["no_prazo"]:
            resultado = conflito("ESTADO_INCOMPATIVEL", "O prazo de decisão terminou.")
        elif decisao == "ACEITAR":
            # O aceite só muda o estado pelo comando do Orquestrador; aqui fixa-se o destino da chave.
            resultado = conflito("ACEITE_ENCAMINHAR", "Encaminhe o aceite ao Orquestrador com a mesma chave.")
        else:
            conexao.execute("""
                UPDATE reservas SET status = 'REJEITADA', decisao = 'REJEITAR', decisao_ator_id = %s,
                    decidida_em = now(), atualizada_em = now()
                WHERE reserva_id = %s
            """, (profissional, reserva_id))
            conexao.execute("""
                INSERT INTO historico_reserva
                    (historico_id, reserva_id, status_anterior, status_posterior, ocorrido_em, ator_id)
                VALUES (%s, %s, 'SOLICITADA', 'REJEITADA', now(), %s)
            """, (uuid4(), reserva_id, profissional))
            resultado = 200, {"reservaId": str(reserva_id), "status": "REJEITADA"}
        conexao.execute("""
            INSERT INTO idempotencia_comandos
                (operacao, principal_id, chave, request_hash, http_status, resposta)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (OPERACAO_DECISAO, profissional, chave, resumo, resultado[0], Jsonb(resultado[1])))
        return resultado


@app.post("/api/unidade/v1/reservas/{reservaId}/decisao", dependencies=RASTREADO)
async def decidir(request: Request, reservaId: UUID, corpo: Decisao, profissional: Profissional, chave: Chave):
    if not chave.strip():
        raise HTTPException(400, "Chave idempotente vazia.")
    # O replay vem antes da consulta remota: um retry recupera o destino original mesmo se a unidade mudou.
    anterior = await run_in_threadpool(
        reobter_resultado, BANCO, OPERACAO_DECISAO, profissional.id, chave,
        sha256(f"{reservaId}:{corpo.decisao}".encode()).hexdigest(),
    )
    if anterior is not None:
        return responder(anterior)
    unidade = await verificar_vinculo(request, profissional)
    status, dados = await run_in_threadpool(
        registrar_decisao, profissional.id, unidade, reservaId, corpo.decisao, chave
    )
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})


class ComandoSaga(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID


Orquestrador = Annotated[str, Depends(orquestrador_autenticado)]


def registrar_transicao(operacao: str, reserva_id: UUID, saga_id: UUID, chave: str,
                        origem: str, destino: str, ator: Ator | None = None):
    """Transição pedida pelo Orquestrador: efeito, histórico e resultado idempotente na mesma transação."""
    principal = "orquestrador"
    resumo = sha256(f"{reserva_id}:{saga_id}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        controle = f"{operacao}:{principal}:{chave}"
        conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (controle,))
        anterior = conexao.execute("""
            SELECT request_hash, http_status, resposta FROM idempotencia_comandos
            WHERE operacao = %s AND principal_id = %s AND chave = %s
        """, (operacao, principal, chave)).fetchone()
        if anterior is not None:
            if anterior["request_hash"] != resumo:
                return conflito("CHAVE_IDEMPOTENTE_CONFLITANTE", "Chave reutilizada com outro comando.")
            return anterior["http_status"], anterior["resposta"]
        reserva = conexao.execute(f"""
            SELECT {CAMPOS}, decisao_ate > now() AS "noPrazo"
            FROM reservas WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if reserva is None:
            raise HTTPException(404, "Reserva não encontrada.")
        if ator is not None and reserva["unidadeId"] != ator.unidadeId:
            raise HTTPException(403, "Reserva de outra unidade.")
        if reserva["status"] != origem:
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {reserva['status']}.")
        elif ator is not None and not reserva["noPrazo"]:
            resultado = conflito("ESTADO_INCOMPATIVEL", "O prazo de decisão terminou.")
        else:
            conexao.execute("""
                UPDATE reservas SET status = %s, atualizada_em = now(),
                    decisao = COALESCE(%s, decisao), decisao_ator_id = COALESCE(%s, decisao_ator_id),
                    decidida_em = CASE WHEN %s::text IS NULL THEN decidida_em ELSE now() END
                WHERE reserva_id = %s
            """, (destino, ator and "ACEITAR", ator and ator.id, ator and ator.id, reserva_id))
            conexao.execute("""
                INSERT INTO historico_reserva
                    (historico_id, reserva_id, status_anterior, status_posterior, ocorrido_em, ator_id, saga_id)
                VALUES (%s, %s, %s, %s, now(), %s, %s)
            """, (uuid4(), reserva_id, origem, destino, ator.id if ator else principal, saga_id))
            corpo = {"reservaId": str(reserva_id), "status": destino}
            if ator is not None:
                corpo |= {"unidadeId": str(reserva["unidadeId"]), "itemId": str(reserva["itemId"]),
                          "quantidade": reserva["quantidade"]}
            resultado = 200, corpo
        conexao.execute("""
            INSERT INTO idempotencia_comandos
                (operacao, principal_id, chave, request_hash, http_status, resposta)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (operacao, principal, chave, resumo, resultado[0], Jsonb(resultado[1])))
        return resultado


def responder(resultado: tuple[int, dict]) -> JSONResponse:
    return JSONResponse(resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})


@app.post("/internal/v1/reservas/{reservaId}/aceite", dependencies=RASTREADO)
async def aceitar(
    request: Request, reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave,
    papel: Annotated[str | None, Header(alias="X-Ator-Papel")] = None,
    ator_id: Annotated[str | None, Header(alias="X-Ator-Id")] = None,
    unidade: Annotated[str | None, Header(alias="X-Ator-Unidade-Id")] = None,
):
    ator = ator_delegado(papel, ator_id, unidade)
    # Um aceite já gravado é recuperado sem reavaliar a unidade; senão a SAGA o trataria como recusado.
    anterior = await run_in_threadpool(
        reobter_resultado, BANCO, "aceitar-reserva", "orquestrador", chave,
        sha256(f"{reservaId}:{comando.sagaId}".encode()).hexdigest(),
    )
    if anterior is not None:
        return responder(anterior)
    await verificar_vinculo(request, ator)
    return responder(await run_in_threadpool(
        registrar_transicao, "aceitar-reserva", reservaId, comando.sagaId, chave, "SOLICITADA", "EM_CONFIRMACAO", ator
    ))


@app.post("/internal/v1/reservas/{reservaId}/confirmar", dependencies=RASTREADO)
async def confirmar(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(await run_in_threadpool(
        registrar_transicao, "confirmar-reserva", reservaId, comando.sagaId, chave, "EM_CONFIRMACAO", "CONFIRMADA"
    ))


@app.post("/internal/v1/reservas/{reservaId}/falhar-confirmacao", dependencies=RASTREADO)
async def falhar_confirmacao(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(await run_in_threadpool(
        registrar_transicao, "falhar-confirmacao", reservaId, comando.sagaId, chave, "EM_CONFIRMACAO", "FALHA_CONFIRMACAO"
    ))


@app.post("/internal/v1/reservas/{reservaId}/finalizar-cancelamento", dependencies=RASTREADO)
async def finalizar_cancelamento(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(await run_in_threadpool(
        registrar_transicao, "finalizar-cancelamento", reservaId, comando.sagaId, chave,
        "CANCELAMENTO_EM_ANDAMENTO", "CANCELADA"
    ))
