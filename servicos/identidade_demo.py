import os
from dataclasses import dataclass
from hmac import compare_digest
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)
Credencial = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
NAO_AUTENTICADO = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class Ator:
    papel: Literal["CIDADAO", "PROFISSIONAL"]
    id: str
    unidadeId: UUID | None = None


def exigir_credencial(credencial: HTTPAuthorizationCredentials | None) -> bytes:
    if credencial is None:
        raise HTTPException(401, "Credencial Bearer obrigatória.", headers=NAO_AUTENTICADO)
    return credencial.credentials.encode()


def validar_token(credencial: HTTPAuthorizationCredentials | None, variavel: str) -> None:
    recebido = exigir_credencial(credencial)
    esperado = os.environ.get(variavel, "")
    if len(esperado) < 32:
        raise HTTPException(503, "Credenciais de demonstração não configuradas.")
    if not compare_digest(recebido, esperado.encode()):
        raise HTTPException(401, "Credencial inválida.", headers=NAO_AUTENTICADO)


def unidade_do_profissional() -> UUID:
    try:
        return UUID(os.environ.get("GLICO_PROFISSIONAL_UNIDADE_ID", ""))
    except ValueError:
        raise HTTPException(503, "Vínculo do profissional de demonstração não configurado.") from None


def ator_autenticado(credencial: Credencial) -> Ator:
    # shortcut: um token fixo por papel; trocar por um provedor de identidade (JWT) se houver mais atores.
    recebido = exigir_credencial(credencial)
    tokens = {
        papel: os.environ.get(variavel, "")
        for papel, variavel in (("CIDADAO", "GLICO_CIDADAO_TOKEN"), ("PROFISSIONAL", "GLICO_PROFISSIONAL_TOKEN"))
    }
    tokens = {papel: valor for papel, valor in tokens.items() if len(valor) >= 32}
    if not tokens or len(set(tokens.values())) < len(tokens):
        raise HTTPException(503, "Credenciais de demonstração ausentes ou repetidas entre papéis.")
    papeis = [papel for papel, valor in tokens.items() if compare_digest(recebido, valor.encode())]
    if not papeis:
        raise HTTPException(401, "Credencial inválida.", headers=NAO_AUTENTICADO)
    if papeis[0] == "CIDADAO":
        return Ator("CIDADAO", "cidadao-demo")
    return Ator("PROFISSIONAL", "profissional-demo", unidade_do_profissional())


AtorAutenticado = Annotated[Ator, Depends(ator_autenticado)]


def cidadao_autenticado(ator: AtorAutenticado) -> str:
    if ator.papel != "CIDADAO":
        raise HTTPException(403, "Operação exclusiva do cidadão.")
    return ator.id


def profissional_autenticado(ator: AtorAutenticado) -> Ator:
    if ator.papel != "PROFISSIONAL":
        raise HTTPException(403, "Operação exclusiva de profissional da unidade.")
    return ator


def servico_reservas_autenticado(credencial: Credencial) -> None:
    validar_token(credencial, "GLICO_RESERVAS_SERVICE_TOKEN")
