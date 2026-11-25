"""Cancelamento local e início do cancelamento distribuído."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from servicos.banco import conectar
from servicos.comandos import RASTREADO, Chave, Justificativa, responder, resumir
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import (
    Ator, ator_autenticado, ator_delegado, orquestrador_autenticado, profissional_autenticado,
)
from servicos.reservas.transicoes import transicionar


rotas = APIRouter()
BANCO = "RESERVAS_DATABASE_URL"
Orquestrador = Annotated[str, Depends(orquestrador_autenticado)]
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


def ator_cidadao(ator: Annotated[Ator, Depends(ator_autenticado)]) -> Ator:
    if ator.papel != "CIDADAO":
        raise HTTPException(403, "Operação exclusiva do cidadão.")
    return ator


def delegado(
    _orquestrador: Orquestrador,
    papel: Annotated[str | None, Header(alias="X-Ator-Papel")] = None,
    ator_id: Annotated[str | None, Header(alias="X-Ator-Id")] = None,
    unidade: Annotated[str | None, Header(alias="X-Ator-Unidade-Id")] = None,
) -> Ator:
    return ator_delegado(papel, ator_id, unidade, aceita_cidadao=True)


Cidadao = Annotated[Ator, Depends(ator_cidadao)]
Delegado = Annotated[Ator, Depends(delegado)]


class CancelamentoUnidade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    justificativa: Justificativa


class IniciarCancelamento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID
    justificativa: Justificativa | None = None


def conflito(codigo: str, mensagem: str) -> tuple[int, dict]:
    return 409, {"codigo": codigo, "mensagem": mensagem}


def autorizar(reserva, ator: Ator) -> None:
    # Reserva alheia e inexistente são indistinguíveis para o cidadão.
    if reserva is None or (ator.papel == "CIDADAO" and reserva["cidadao_id"] != ator.id):
        raise HTTPException(404, "Reserva não encontrada.")
    if ator.papel == "PROFISSIONAL" and reserva["unidade_id"] != ator.unidadeId:
        raise HTTPException(403, "Reserva de outra unidade.")


def buscar(conexao, reserva_id: UUID, *, travar: bool):
    return conexao.execute(
        "SELECT cidadao_id, unidade_id, status FROM reservas WHERE reserva_id = %s" + (" FOR UPDATE" if travar else ""),
        (reserva_id,),
    ).fetchone()


def cancelar_local(ator: Ator, reserva_id: UUID, justificativa: str | None, chave: str):
    """Cancela SOLICITADA ou fixa, sob a chave, o encaminhamento ao Orquestrador."""
    operacao = f"cancelar-{ator.papel.lower()}"
    resumo = resumir(reserva_id, justificativa or "")
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, operacao, ator.id, chave, resumo)) is not None:
            return anterior
        reserva = buscar(conexao, reserva_id, travar=True)
        autorizar(reserva, ator)
        status = reserva["status"]
        if status == "SOLICITADA":
            transicionar(conexao, reserva_id, status, "CANCELADA", ator_id=ator.id, justificativa=justificativa)
            resultado = 200, {"reservaId": str(reserva_id), "status": "CANCELADA"}
        elif status in ("EM_CONFIRMACAO", "CONFIRMADA"):
            resultado = conflito("CANCELAMENTO_DISTRIBUIDO", "Encaminhe o cancelamento ao Orquestrador com a mesma chave.")
        elif status == "CANCELAMENTO_EM_ANDAMENTO":
            resultado = conflito("CANCELAMENTO_EM_ANDAMENTO", "O cancelamento já está em andamento.")
        else:
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {status}.")
        return gravar_resultado(conexao, operacao, ator.id, chave, resumo, resultado)


def iniciar(ator: Ator, reserva_id: UUID, comando: IniciarCancelamento, chave: str):
    operacao, principal = "iniciar-cancelamento", "orquestrador"
    if ator.papel == "PROFISSIONAL" and comando.justificativa is None:
        raise HTTPException(400, "Justificativa obrigatória para o profissional.")
    resumo = resumir(reserva_id, comando.sagaId, ator.papel, ator.id, comando.justificativa or "")
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, operacao, principal, chave, resumo)) is not None:
            return anterior
        reserva = buscar(conexao, reserva_id, travar=True)
        autorizar(reserva, ator)
        if reserva["status"] in ("EM_CONFIRMACAO", "CONFIRMADA"):
            transicionar(conexao, reserva_id, reserva["status"], "CANCELAMENTO_EM_ANDAMENTO", ator_id=ator.id,
                         justificativa=comando.justificativa, saga_id=comando.sagaId)
            resultado = 200, {"reservaId": str(reserva_id), "status": "CANCELAMENTO_EM_ANDAMENTO"}
        else:
            resultado = conflito("ESTADO_INCOMPATIVEL", f"A reserva está {reserva['status']}.")
        return gravar_resultado(conexao, operacao, principal, chave, resumo, resultado)


@rotas.post("/api/cidadao/v1/reservas/{reservaId}/cancelar", dependencies=RASTREADO)
def cancelar_pelo_cidadao(reservaId: UUID, cidadao: Cidadao, chave: Chave):
    return responder(cancelar_local(cidadao, reservaId, None, chave))


@rotas.post("/api/unidade/v1/reservas/{reservaId}/cancelar", dependencies=RASTREADO)
def cancelar_pela_unidade(reservaId: UUID, corpo: CancelamentoUnidade, profissional: Profissional, chave: Chave):
    return responder(cancelar_local(profissional, reservaId, corpo.justificativa, chave))


@rotas.get("/internal/v1/reservas/{reservaId}/permissao-cancelamento", dependencies=RASTREADO)
def consultar_permissao(reservaId: UUID, ator: Delegado):
    with conectar(BANCO) as conexao:
        reserva = buscar(conexao, reservaId, travar=False)
    autorizar(reserva, ator)
    return responder((200, {"reservaId": str(reservaId), "status": reserva["status"]}))


@rotas.post("/internal/v1/reservas/{reservaId}/iniciar-cancelamento", dependencies=RASTREADO)
def iniciar_cancelamento(reservaId: UUID, comando: IniciarCancelamento, ator: Delegado, chave: Chave):
    return responder(iniciar(ator, reservaId, comando, chave))
