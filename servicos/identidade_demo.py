import os
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)
Credencial = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def validar_token(credencial: HTTPAuthorizationCredentials | None, variavel: str) -> None:
    if credencial is None:
        raise HTTPException(401, "Credencial Bearer obrigatória.", headers={"WWW-Authenticate": "Bearer"})
    esperado = os.environ.get(variavel, "")
    if len(esperado) < 32:
        raise HTTPException(503, "Credenciais de demonstração não configuradas.")
    if not compare_digest(credencial.credentials.encode(), esperado.encode()):
        raise HTTPException(401, "Credencial inválida.", headers={"WWW-Authenticate": "Bearer"})


def cidadao_autenticado(credencial: Credencial) -> str:
    validar_token(credencial, "GLICO_CIDADAO_TOKEN")
    return "cidadao-demo"


def servico_reservas_autenticado(credencial: Credencial) -> None:
    validar_token(credencial, "GLICO_RESERVAS_SERVICE_TOKEN")
