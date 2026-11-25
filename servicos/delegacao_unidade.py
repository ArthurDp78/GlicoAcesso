"""Credencial interna de curta duração emitida pelo BFF Unidade para o Orquestrador."""
import base64
import json
import os
from binascii import Error
from hmac import compare_digest, digest
from time import time
from uuid import UUID

from fastapi import HTTPException

from servicos.identidade_demo import Ator, Credencial, NAO_AUTENTICADO, exigir_credencial


VALIDADE_SEGUNDOS = 60
CONTEXTO = b"glicoacesso:bff-unidade:orquestrador:v1:"


def chave_bff() -> bytes:
    chave = os.environ.get("GLICO_BFF_UNIDADE_SIGNING_KEY", "")
    if len(chave) < 32:
        raise HTTPException(503, "Credencial interna do BFF Unidade não configurada.")
    return chave.encode()


def emitir_credencial(ator: Ator) -> str:
    if ator.papel != "PROFISSIONAL" or ator.unidadeId is None:
        raise HTTPException(403, "A delegação exige um profissional vinculado à unidade.")
    dados = json.dumps([ator.papel, ator.id, str(ator.unidadeId), int(time()) + VALIDADE_SEGUNDOS]).encode()
    mensagem = base64.urlsafe_b64encode(dados)
    assinatura = digest(chave_bff(), CONTEXTO + mensagem, "sha256").hex().encode()
    return (mensagem + b"." + assinatura).decode("ascii")


def profissional_delegado(credencial: Credencial) -> Ator:
    token = exigir_credencial(credencial)
    chave = chave_bff()
    mensagem, _, assinatura = token.partition(b".")
    invalida = HTTPException(401, "Credencial interna inválida ou expirada.", headers=NAO_AUTENTICADO)
    esperada = digest(chave, CONTEXTO + mensagem, "sha256").hex().encode()
    if not compare_digest(assinatura, esperada):
        raise invalida
    try:
        papel, ator_id, unidade, expira = json.loads(base64.b64decode(mensagem, altchars=b"-_", validate=True))
        if not isinstance(ator_id, str) or not ator_id or not isinstance(unidade, str):
            raise ValueError
        unidade_id = UUID(unidade)
    except (Error, ValueError, TypeError):
        raise invalida from None
    if type(expira) is not int or expira <= time():
        raise invalida
    if papel != "PROFISSIONAL":
        raise HTTPException(403, "Operação exclusiva de profissional delegado.")
    return Ator("PROFISSIONAL", ator_id, unidade_id)
