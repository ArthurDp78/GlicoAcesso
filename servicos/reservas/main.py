import os
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from servicos.banco import BancoIndisponivel, conectar
from servicos.contratos_reserva import PedidoReserva, ReservaInterna
from servicos.http import cliente_http, consultar
from servicos.identidade_demo import cidadao_autenticado


app = FastAPI(title="GlicoAcesso — Reservas", lifespan=cliente_http)
BANCO = "RESERVAS_DATABASE_URL"
OPERACAO = "criar-reserva"
Cidadao = Annotated[str, Depends(cidadao_autenticado)]
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
    resposta = await consultar(cliente, url, headers={"Authorization": f"Bearer {token}"})
    if resposta.status_code == 404:
        return None
    if resposta.status_code != 200:
        raise HTTPException(503, "Não foi possível validar a unidade ou a permissão de reserva.")
    try:
        return modelo.model_validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "A validação retornou dados incompatíveis.") from erro


async def verificar_pedido(request: Request, pedido: PedidoReserva) -> int:
    token = os.environ.get("GLICO_RESERVAS_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Credencial interna de Reservas não configurada.")
    unidades = os.environ.get("UNIDADES_URL", "http://127.0.0.1:8002").rstrip("/")
    estoque = os.environ.get("ESTOQUE_URL", "http://127.0.0.1:8003").rstrip("/")
    cliente = request.app.state.http
    unidade = await verificar_dependencia(
        cliente, f"{unidades}/internal/v1/unidades/{pedido.unidadeId}", token, UnidadeParaReserva
    )
    if unidade is None or unidade.unidadeId != pedido.unidadeId or not unidade.ativa:
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


@app.get("/internal/v1/reservas/{reservaId}", response_model=ReservaInterna)
def consultar_reserva(reservaId: UUID, cidadao: Cidadao, response: Response):
    response.headers["Cache-Control"] = "no-store"
    with conectar(BANCO) as conexao:
        registro = conexao.execute(
            f"SELECT {CAMPOS} FROM reservas WHERE reserva_id = %s AND cidadao_id = %s",
            (reservaId, cidadao),
        ).fetchone()
    if registro is None:
        raise HTTPException(404, "Reserva não encontrada.")
    return registro
