"""Cancelamento local e início do cancelamento distribuído."""
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from servicos.banco import conectar
from servicos.contratos_reserva import CancelamentoUnidade
from servicos.comandos import RASTREADO, Chave, Justificativa, NaoNulo, responder, resumir
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import Ator, CidadaoDelegado, ProfissionalDelegado, ator_do_orquestrador
from servicos.reservas.transicoes import transicionar


rotas = APIRouter()
BANCO = "RESERVAS_DATABASE_URL"
Cidadao = CidadaoDelegado
Profissional = ProfissionalDelegado
Delegado = Annotated[Ator, Depends(ator_do_orquestrador)]


class IniciarCancelamento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID
    justificativa: Annotated[Justificativa | None, NaoNulo] = None


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
        anterior = resultado_anterior(conexao, operacao, ator.id, chave, resumo)
        if anterior is None:
            # A main usava outro escopo e outro resumo. O registro original permanece intacto.
            legado = sha256(str((reserva_id, justificativa, None, ator.unidadeId)).encode()).hexdigest()
            anterior = resultado_anterior(conexao, "cancelamento-local", f"{ator.papel}:{ator.id}", chave, legado)
        if anterior is not None and anterior[1].get("codigo") == "CHAVE_IDEMPOTENTE_CONFLITANTE":
            return anterior
        reserva = buscar(conexao, reserva_id, travar=anterior is None)
        autorizar(reserva, ator)
        if anterior is not None:
            return anterior
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
        anterior = resultado_anterior(conexao, operacao, principal, chave, resumo)
        if anterior is None:
            legado = sha256(str((reserva_id, comando.justificativa, comando.sagaId, ator.unidadeId)).encode()).hexdigest()
            anterior = resultado_anterior(conexao, operacao, f"{ator.papel}:{ator.id}", chave, legado)
        if anterior is not None and anterior[1].get("codigo") == "CHAVE_IDEMPOTENTE_CONFLITANTE":
            return anterior
        reserva = buscar(conexao, reserva_id, travar=anterior is None)
        autorizar(reserva, ator)
        if anterior is not None:
            return anterior
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
