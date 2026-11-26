"""Credenciais internas de curta duração dos BFFs para o Orquestrador."""
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


def chave_bff(papel: str = "PROFISSIONAL") -> bytes:
    variavel = "GLICO_BFF_CIDADAO_SIGNING_KEY" if papel == "CIDADAO" else "GLICO_BFF_UNIDADE_SIGNING_KEY"
    chave = os.environ.get(variavel, "")
    if len(chave) < 32:
        raise HTTPException(503, "Credencial interna do BFF não configurada.")
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


PREFIXO_CIDADAO = b"cidadao."
CONTEXTO_CIDADAO = b"glicoacesso:bff-cidadao:orquestrador:v1:"


def emitir_credencial_cidadao(cidadao_id: str) -> str:
    dados = json.dumps([cidadao_id, int(time()) + VALIDADE_SEGUNDOS]).encode()
    mensagem = base64.urlsafe_b64encode(dados)
    assinatura = digest(chave_bff("CIDADAO"), CONTEXTO_CIDADAO + mensagem, "sha256").hex().encode()
    return (PREFIXO_CIDADAO + mensagem + b"." + assinatura).decode("ascii")


def ator_cancelamento_delegado(credencial: Credencial) -> Ator:
    token = exigir_credencial(credencial)
    if not token.startswith(PREFIXO_CIDADAO):
        return profissional_delegado(credencial)
    mensagem, _, assinatura = token[len(PREFIXO_CIDADAO):].partition(b".")
    invalida = HTTPException(401, "Credencial interna inválida ou expirada.", headers=NAO_AUTENTICADO)
    esperada = digest(chave_bff("CIDADAO"), CONTEXTO_CIDADAO + mensagem, "sha256").hex().encode()
    if not compare_digest(assinatura, esperada):
        raise invalida
    try:
        ator_id, expira = json.loads(base64.b64decode(mensagem, altchars=b"-_", validate=True))
        if not isinstance(ator_id, str) or not ator_id or type(expira) is not int or expira <= time():
            raise ValueError
    except (Error, ValueError, TypeError):
        raise invalida from None
    return Ator("CIDADAO", ator_id)
