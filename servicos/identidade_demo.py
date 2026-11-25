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


CHAMADOR_NAO_AUTORIZADO = "CHAMADOR_NAO_AUTORIZADO"
VARIAVEIS_DE_TOKEN = (
    "GLICO_CIDADAO_TOKEN", "GLICO_PROFISSIONAL_TOKEN", "GLICO_RESERVAS_SERVICE_TOKEN",
    "GLICO_ORQUESTRADOR_SERVICE_TOKEN", "GLICO_RETIRADAS_SERVICE_TOKEN", "GLICO_ADMIN_SERVICE_TOKEN",
)


def validar_token(credencial: HTTPAuthorizationCredentials | None, variavel: str) -> None:
    recebido = exigir_credencial(credencial)
    esperado = os.environ.get(variavel, "")
    if len(esperado) < 32:
        raise HTTPException(503, "Credenciais de demonstração não configuradas.")
    if not compare_digest(recebido, esperado.encode()):
        # Identidade conhecida, mas sem permissão para esta operação.
        conhecidos = (os.environ.get(outra, "") for outra in VARIAVEIS_DE_TOKEN)
        if any([len(token) >= 32 and compare_digest(recebido, token.encode()) for token in conhecidos]):
            raise HTTPException(403, {"codigo": CHAMADOR_NAO_AUTORIZADO, "mensagem": "Operação restrita a outro chamador."})
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


def orquestrador_autenticado(credencial: Credencial) -> str:
    validar_token(credencial, "GLICO_ORQUESTRADOR_SERVICE_TOKEN")
    return "orquestrador"


def retiradas_autenticado(credencial: Credencial) -> None:
    validar_token(credencial, "GLICO_RETIRADAS_SERVICE_TOKEN")


def administracao_autenticada(credencial: Credencial) -> str:
    # Cadastros globais (unidades e catálogo) não pertencem a uma unidade e não são expostos pelos BFFs.
    validar_token(credencial, "GLICO_ADMIN_SERVICE_TOKEN")
    return "administracao"


def reservas_ou_profissional(credencial: Credencial) -> Ator | None:
    """None = serviço Reservas; Ator = profissional, cujo vínculo a rota confere."""
    recebido = exigir_credencial(credencial)
    servico = os.environ.get("GLICO_RESERVAS_SERVICE_TOKEN", "")
    if len(servico) >= 32 and compare_digest(recebido, servico.encode()):
        return None
    return profissional_autenticado(ator_autenticado(credencial))


def exigir_unidade(profissional: Ator, unidade_id: UUID) -> None:
    if profissional.unidadeId != unidade_id:
        raise HTTPException(403, "Ator sem acesso à unidade.")


def ator_delegado(papel: str | None, ator_id: str | None, unidade: str | None, *, aceita_cidadao: bool = False) -> Ator:
    # shortcut: cabeçalhos de ator só valem junto da credencial do Orquestrador; trocar por token delegado assinado.
    if aceita_cidadao and papel == "CIDADAO" and ator_id:
        return Ator("CIDADAO", ator_id)
    if papel != "PROFISSIONAL" or not ator_id:
        raise HTTPException(403, "Ator delegado ausente ou sem papel permitido.")
    try:
        return Ator("PROFISSIONAL", ator_id, UUID(unidade or ""))
    except ValueError:
        raise HTTPException(403, "Unidade do ator delegado inválida.") from None
