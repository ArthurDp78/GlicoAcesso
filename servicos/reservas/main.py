import logging
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

from servicos.contratos_unidade import PRAZO_MAXIMO_HORAS
from servicos.banco import BancoIndisponivel, conectar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.contratos_reserva import JustificativaCancelamento, PedidoReserva, ReservaInterna
from servicos.contratos_retirada import EstadoCanonico
from servicos.http import cliente_http, consultar
from servicos.identidade_demo import (
    Ator, AtorAutenticado, ator_cancelamento, ator_delegado, cidadao_autenticado, orquestrador_autenticado, profissional_autenticado,
    retiradas_autenticado,
)


from servicos.mensageria import declarar_retiradas, iniciar_consumidor
from servicos.reservas.eventos import FILA, aplicar_retirada


@asynccontextmanager
async def ciclo(app: FastAPI):
    parar = threading.Event()
    async with cliente_http(app):
        iniciar_consumidor(FILA, declarar_retiradas, aplicar_retirada, parar)
        threading.Thread(target=expirar_periodicamente, args=(parar,), name="expirar-reservas", daemon=True).start()
        try:
            yield
        finally:
            parar.set()


app = FastAPI(title="GlicoAcesso — Reservas", lifespan=ciclo)
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
    resposta = await consultar(cliente, url, headers={"Authorization": f"Bearer {token}"})
    if resposta.status_code == 404:
        return None
    if resposta.status_code != 200:
        raise HTTPException(503, "Não foi possível validar a unidade ou a permissão de reserva.")
    try:
        return modelo.model_validate_json(resposta.content)
    except ValidationError as erro:
        raise HTTPException(502, "A validação retornou dados incompatíveis.") from erro


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
    if unidade.prazoAnaliseHoras > PRAZO_MAXIMO_HORAS:
        raise HTTPException(422, "A unidade precisa atualizar o prazo de análise para até 720 horas.")
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


def listar_pendentes_da_unidade(unidade_id: UUID):
    with conectar(BANCO) as conexao:
        return conexao.execute(f"""
            SELECT {CAMPOS} FROM reservas
            WHERE unidade_id = %s AND status = 'SOLICITADA' AND decisao_ate > clock_timestamp()
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


async def comando_profissional(request, ator, funcao, *args, **kwargs):
    async def consultar_gravado():
        return await run_in_threadpool(funcao, *args, **kwargs, somente_consulta=True)

    anterior = await consultar_gravado()
    if anterior is not None:
        return anterior
    try:
        await verificar_vinculo(request, ator)
    except HTTPException:
        # O primeiro comando pode ter confirmado durante a consulta remota.
        anterior = await consultar_gravado()
        if anterior is not None:
            return anterior
        raise
    return await run_in_threadpool(funcao, *args, **kwargs)


def registrar_decisao(profissional: str, unidade: UUID, reserva_id: UUID, decisao: str, chave: str, *, somente_consulta=False):
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
            pertence = conexao.execute(
                "SELECT 1 FROM reservas WHERE reserva_id = %s AND unidade_id = %s", (reserva_id, unidade)
            ).fetchone()
            if pertence is None:
                raise HTTPException(403, "Reserva de outra unidade.")
            return anterior["http_status"], anterior["resposta"]
        if somente_consulta:
            return None
        reserva = conexao.execute("""
            SELECT unidade_id, status, decisao_ate
            FROM reservas WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if reserva is None:
            raise HTTPException(404, "Reserva não encontrada.")
        if reserva["unidade_id"] != unidade:
            raise HTTPException(403, "Reserva de outra unidade.")
        if reserva["status"] != "SOLICITADA":
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {reserva['status']}.")
        elif not prazo_vigente(conexao, reserva["decisao_ate"]):
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


@app.post("/api/unidade/v1/reservas/{reservaId}/decisao")
async def decidir(request: Request, reservaId: UUID, corpo: Decisao, profissional: Profissional, chave: Chave):
    if not chave.strip():
        raise HTTPException(422, "Chave idempotente vazia.")
    status, dados = await comando_profissional(
        request, profissional, registrar_decisao, profissional.id, profissional.unidadeId, reservaId, corpo.decisao, chave
    )
    return JSONResponse(dados, status_code=status, headers={"Cache-Control": "no-store"})


class ComandoSaga(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID


Orquestrador = Annotated[str, Depends(orquestrador_autenticado)]


def registrar_transicao(operacao: str, reserva_id: UUID, saga_id: UUID, chave: str,
                        origem: str, destino: str, ator: Ator | None = None, *, somente_consulta=False):
    """Transição pedida pelo Orquestrador: efeito, histórico e resultado idempotente na mesma transação."""
    principal = "orquestrador"
    resumo = sha256(f"{reserva_id}:{saga_id}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        controle = f"{operacao}:{principal}:{chave}"
        conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (controle,))
        anterior = conexao.execute("""
            SELECT request_hash, http_status, resposta, ator_id, unidade_id FROM idempotencia_comandos
            WHERE operacao = %s AND principal_id = %s AND chave = %s
        """, (operacao, principal, chave)).fetchone()
        if anterior is not None:
            if anterior["request_hash"] != resumo:
                return conflito("CHAVE_IDEMPOTENTE_CONFLITANTE", "Chave reutilizada com outro comando.")
            if ator is not None:
                if anterior["ator_id"] is not None:
                    autorizado = (anterior["ator_id"], anterior["unidade_id"]) == (ator.id, ator.unidadeId)
                else:
                    # Registros antigos guardam o autor do aceite efetivado no histórico.
                    vinculo = conexao.execute("""
                        SELECT r.unidade_id, h.ator_id FROM reservas r
                        LEFT JOIN historico_reserva h ON h.reserva_id = r.reserva_id
                            AND h.saga_id = %s AND h.status_posterior = 'EM_CONFIRMACAO'
                        WHERE r.reserva_id = %s
                    """, (saga_id, reserva_id)).fetchone()
                    autorizado = vinculo and vinculo["unidade_id"] == ator.unidadeId and (
                        vinculo["ator_id"] == ator.id or anterior["http_status"] == 409)
                if not autorizado:
                    raise HTTPException(403, "Ator incompatível com o comando registrado.")
            return anterior["http_status"], anterior["resposta"]
        if somente_consulta:
            return None
        reserva = conexao.execute(f"""
            SELECT {CAMPOS}, decisao_ate
            FROM reservas WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if reserva is None:
            raise HTTPException(404, "Reserva não encontrada.")
        if ator is not None and reserva["unidadeId"] != ator.unidadeId:
            raise HTTPException(403, "Reserva de outra unidade.")
        if reserva["status"] != origem:
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {reserva['status']}.")
        elif ator is not None and not prazo_vigente(conexao, reserva["decisao_ate"]):
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
                (operacao, principal_id, chave, request_hash, http_status, resposta, ator_id, unidade_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (operacao, principal, chave, resumo, resultado[0], Jsonb(resultado[1]), ator and ator.id, ator and ator.unidadeId))
        return resultado


def responder(resultado: tuple[int, dict]) -> JSONResponse:
    return JSONResponse(resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})


@app.post("/internal/v1/reservas/{reservaId}/aceite")
async def aceitar(
    request: Request, reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave,
    papel: Annotated[str | None, Header(alias="X-Ator-Papel")] = None,
    ator_id: Annotated[str | None, Header(alias="X-Ator-Id")] = None,
    unidade: Annotated[str | None, Header(alias="X-Ator-Unidade-Id")] = None,
):
    ator = ator_delegado(papel, ator_id, unidade)
    return responder(await comando_profissional(
        request, ator, registrar_transicao, "aceitar-reserva", reservaId, comando.sagaId, chave, "SOLICITADA", "EM_CONFIRMACAO", ator
    ))


@app.post("/internal/v1/reservas/{reservaId}/confirmar")
async def confirmar(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(await run_in_threadpool(
        registrar_transicao, "confirmar-reserva", reservaId, comando.sagaId, chave, "EM_CONFIRMACAO", "CONFIRMADA"
    ))


@app.post("/internal/v1/reservas/{reservaId}/falhar-confirmacao")
async def falhar_confirmacao(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(await run_in_threadpool(
        registrar_transicao, "falhar-confirmacao", reservaId, comando.sagaId, chave, "EM_CONFIRMACAO", "FALHA_CONFIRMACAO"
    ))


@app.get("/internal/v1/reservas/{reservaId}/estado", response_model=EstadoCanonico,
         dependencies=[Depends(retiradas_autenticado)])
def consultar_estado_canonico(reservaId: UUID, response: Response):
    with conectar(BANCO) as conexao:
        estado = conexao.execute(
            'SELECT reserva_id AS "reservaId", status FROM reservas WHERE reserva_id = %s', (reservaId,),
        ).fetchone()
    if estado is None:
        raise HTTPException(404, "Reserva não encontrada.")
    response.headers["Cache-Control"] = "no-store"
    return estado


def prazo_vigente(conexao, prazo):
    return conexao.execute("SELECT %s > clock_timestamp() AS vigente", (prazo,)).fetchone()["vigente"]


def expirar_periodicamente(parar: threading.Event):
    log = logging.getLogger("uvicorn.error")
    while not parar.is_set():
        try:
            with conectar(BANCO) as conexao:
                conexao.execute("""
                    WITH vencidas AS (
                        SELECT reserva_id FROM reservas
                        WHERE status = 'SOLICITADA' AND decisao_ate <= clock_timestamp()
                        ORDER BY decisao_ate LIMIT 100 FOR UPDATE SKIP LOCKED
                    ), expiradas AS (
                        UPDATE reservas r SET status = 'EXPIRADA', atualizada_em = clock_timestamp()
                        FROM vencidas v WHERE r.reserva_id = v.reserva_id
                        RETURNING r.reserva_id, r.atualizada_em
                    )
                    INSERT INTO historico_reserva
                        (historico_id, reserva_id, status_anterior, status_posterior, ocorrido_em, ator_id)
                    SELECT gen_random_uuid(), reserva_id, 'SOLICITADA', 'EXPIRADA', atualizada_em, 'reservas'
                    FROM expiradas
                """)
        except Exception:
            log.exception("Falha ao expirar solicitações.")
        parar.wait(1)


class IniciarCancelamento(ComandoSaga):
    justificativa: str | None = None


def conferir_justificativa(ator: Ator, justificativa: str | None) -> str | None:
    if ator.papel == "CIDADAO" and justificativa is None:
        return None
    if ator.papel == "PROFISSIONAL" and justificativa is not None:
        try:
            return JustificativaCancelamento(justificativa=justificativa).justificativa
        except ValidationError:
            pass
    raise HTTPException(422, "Justificativa inválida para o papel informado.")


def autorizar_cancelamento(reserva, ator):
    if reserva is None or (ator.papel == "CIDADAO" and reserva["cidadao_id"] != ator.id):
        raise HTTPException(404, "Reserva não encontrada.")
    if ator.papel == "PROFISSIONAL" and reserva["unidade_id"] != ator.unidadeId:
        raise HTTPException(403, "Reserva de outra unidade.")


def mudar_cancelamento(conexao, reserva_id, anterior, destino, ator_id, justificativa, saga_id):
    conexao.execute("""
        UPDATE reservas SET status = %s, cancelamento_saga_id = %s, atualizada_em = clock_timestamp()
        WHERE reserva_id = %s
    """, (destino, saga_id, reserva_id))
    conexao.execute("""
        INSERT INTO historico_reserva (historico_id, reserva_id, status_anterior, status_posterior,
                                       ocorrido_em, ator_id, justificativa, saga_id)
        VALUES (%s, %s, %s, %s, clock_timestamp(), %s, %s, %s)
    """, (uuid4(), reserva_id, anterior, destino, ator_id, justificativa, saga_id))
    return 200, {"reservaId": str(reserva_id), "status": destino}


def cancelar_reserva(reserva_id, ator, chave, justificativa=None, *, saga_id=None, finalizar=False, somente_consulta=False):
    if not chave.strip() or "\x00" in chave:
        raise HTTPException(422, "Chave idempotente inválida.")
    operacao = "finalizar-cancelamento" if finalizar else "iniciar-cancelamento" if saga_id else "cancelamento-local"
    principal = f"{ator.papel}:{ator.id}" if ator else "orquestrador"
    resumo = sha256(str((reserva_id, justificativa, saga_id, ator and ator.unidadeId)).encode()).hexdigest()
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, operacao, principal, chave, resumo)
        if anterior is not None:
            return anterior
        if somente_consulta:
            return None
        reserva = conexao.execute("""
            SELECT cidadao_id, unidade_id, status, cancelamento_saga_id, decisao_ate
            FROM reservas WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if ator is not None:
            autorizar_cancelamento(reserva, ator)
        elif reserva is None:
            raise HTTPException(404, "Reserva não encontrada.")
        estado = reserva["status"]
        if finalizar and estado == "CANCELAMENTO_EM_ANDAMENTO" and reserva["cancelamento_saga_id"] == saga_id:
            resultado = mudar_cancelamento(conexao, reserva_id, estado, "CANCELADA", principal, None, saga_id)
        elif saga_id is not None and not finalizar and estado in ("EM_CONFIRMACAO", "CONFIRMADA"):
            resultado = mudar_cancelamento(
                conexao, reserva_id, estado, "CANCELAMENTO_EM_ANDAMENTO", ator.id, justificativa, saga_id,
            )
        elif saga_id is None and estado == "SOLICITADA" and prazo_vigente(conexao, reserva["decisao_ate"]):
            resultado = mudar_cancelamento(conexao, reserva_id, estado, "CANCELADA", ator.id, justificativa, None)
        elif saga_id is None and estado in ("EM_CONFIRMACAO", "CONFIRMADA"):
            resultado = conflito("CANCELAMENTO_DISTRIBUIDO", "Encaminhe o cancelamento ao Orquestrador.")
        elif saga_id is None and estado == "CANCELAMENTO_EM_ANDAMENTO":
            resultado = conflito("CANCELAMENTO_EM_ANDAMENTO", "Já existe um cancelamento em andamento.")
        else:
            resultado = 409, {"codigo": "ESTADO_INCOMPATIVEL", "mensagem": "A reserva não pode ser cancelada.",
                              "status": estado}
        return gravar_resultado(conexao, operacao, principal, chave, resumo, resultado)


@app.post("/api/cidadao/v1/reservas/{reservaId}/cancelar")
def cancelar_cidadao(reservaId: UUID, cidadao: Cidadao, chave: Chave):
    return responder(cancelar_reserva(reservaId, Ator("CIDADAO", cidadao), chave))


@app.post("/api/unidade/v1/reservas/{reservaId}/cancelar")
async def cancelar_unidade(request: Request, reservaId: UUID, corpo: JustificativaCancelamento,
                          profissional: Profissional, chave: Chave):
    return responder(await comando_profissional(
        request, profissional, cancelar_reserva, reservaId, profissional, chave, corpo.justificativa,
    ))


def delegado_cancelamento(
    _orquestrador: Orquestrador,
    papel: Annotated[str | None, Header(alias="X-Ator-Papel")] = None,
    ator_id: Annotated[str | None, Header(alias="X-Ator-Id")] = None,
    unidade: Annotated[str | None, Header(alias="X-Ator-Unidade-Id")] = None,
):
    return ator_cancelamento(papel, ator_id, unidade)


DelegadoCancelamento = Annotated[Ator, Depends(delegado_cancelamento)]


@app.get("/internal/v1/reservas/{reservaId}/permissao-cancelamento", response_model=EstadoCanonico)
async def permissao_cancelamento(request: Request, reservaId: UUID, ator: DelegadoCancelamento, response: Response):
    if ator.papel == "PROFISSIONAL":
        await verificar_vinculo(request, ator)
    reserva = await run_in_threadpool(buscar_reserva, reservaId)
    dados = None if reserva is None else {"cidadao_id": reserva["cidadaoId"], "unidade_id": reserva["unidadeId"]}
    autorizar_cancelamento(dados, ator)
    response.headers["Cache-Control"] = "no-store"
    return {"reservaId": reservaId, "status": reserva["status"]}


@app.post("/internal/v1/reservas/{reservaId}/iniciar-cancelamento")
async def iniciar_cancelamento(request: Request, reservaId: UUID, comando: IniciarCancelamento,
                              ator: DelegadoCancelamento, chave: Chave):
    justificativa = conferir_justificativa(ator, comando.justificativa)
    if ator.papel == "PROFISSIONAL":
        return responder(await comando_profissional(
            request, ator, cancelar_reserva, reservaId, ator, chave, justificativa, saga_id=comando.sagaId,
        ))
    return responder(await run_in_threadpool(
        cancelar_reserva, reservaId, ator, chave, justificativa, saga_id=comando.sagaId,
    ))


@app.post("/internal/v1/reservas/{reservaId}/finalizar-cancelamento")
def finalizar_cancelamento(reservaId: UUID, comando: ComandoSaga, _orquestrador: Orquestrador, chave: Chave):
    return responder(cancelar_reserva(reservaId, None, chave, saga_id=comando.sagaId, finalizar=True))
