import os
from dataclasses import dataclass
from hmac import compare_digest
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, Header, HTTPException
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
TOKEN_CIDADAO, TOKEN_PROFISSIONAL = "GLICO_CIDADAO_TOKEN", "GLICO_PROFISSIONAL_TOKEN"
TOKEN_BFF_CIDADAO, TOKEN_BFF_UNIDADE = "GLICO_BFF_CIDADAO_TOKEN", "GLICO_BFF_UNIDADE_TOKEN"
TOKEN_RESERVAS, TOKEN_ORQUESTRADOR = "GLICO_RESERVAS_SERVICE_TOKEN", "GLICO_ORQUESTRADOR_SERVICE_TOKEN"
TOKEN_RETIRADAS, TOKEN_ADMIN = "GLICO_RETIRADAS_SERVICE_TOKEN", "GLICO_ADMIN_SERVICE_TOKEN"
VARIAVEIS_DE_TOKEN = (
    TOKEN_CIDADAO, TOKEN_PROFISSIONAL, TOKEN_BFF_CIDADAO, TOKEN_BFF_UNIDADE,
    TOKEN_RESERVAS, TOKEN_ORQUESTRADOR, TOKEN_RETIRADAS, TOKEN_ADMIN,
)
TAMANHO_MINIMO = 32
# Cada BFF só pode agir em nome dos atores do seu público.
PAPEL_DO_BFF = {TOKEN_BFF_CIDADAO: "CIDADAO", TOKEN_BFF_UNIDADE: "PROFISSIONAL"}


class CredenciaisInvalidas(RuntimeError):
    """A configuração de credenciais impede a inicialização do serviço."""


def exigir_credenciais(*obrigatorias: str) -> None:
    """Na inicialização: exige as credenciais do serviço e recusa tokens fracos ou repetidos entre identidades."""
    valores = {nome: os.environ.get(nome, "") for nome in VARIAVEIS_DE_TOKEN}
    if ausentes := [nome for nome in obrigatorias if not valores[nome]]:
        raise CredenciaisInvalidas(f"Credenciais ausentes: {', '.join(ausentes)}.")
    definidas = {nome: valor for nome, valor in valores.items() if valor}
    if fracas := [nome for nome, valor in definidas.items() if len(valor) < TAMANHO_MINIMO or valor != valor.strip()]:
        raise CredenciaisInvalidas(f"Credenciais com menos de {TAMANHO_MINIMO} caracteres ou com espaços: {', '.join(fracas)}.")
    vistos: dict[str, str] = {}
    for nome, valor in definidas.items():
        if valor in vistos:
            raise CredenciaisInvalidas(f"{nome} e {vistos[valor]} usam o mesmo token.")
        vistos[valor] = nome


def corresponde(recebido: bytes, variavel: str) -> bool:
    esperado = os.environ.get(variavel, "")
    return len(esperado) >= TAMANHO_MINIMO and compare_digest(recebido, esperado.encode())


def recusar_chamador(recebido: bytes):
    if any([corresponde(recebido, variavel) for variavel in VARIAVEIS_DE_TOKEN]):
        # Identidade conhecida, mas sem permissão para esta operação.
        raise HTTPException(403, {"codigo": CHAMADOR_NAO_AUTORIZADO, "mensagem": "Operação restrita a outro chamador."})
    raise HTTPException(401, "Credencial inválida.", headers=NAO_AUTENTICADO)


def validar_token(credencial: HTTPAuthorizationCredentials | None, variavel: str) -> None:
    recebido = exigir_credencial(credencial)
    if len(os.environ.get(variavel, "")) < TAMANHO_MINIMO:
        raise HTTPException(503, "Credenciais de demonstração não configuradas.")
    if not corresponde(recebido, variavel):
        recusar_chamador(recebido)


def unidade_do_profissional() -> UUID:
    try:
        return UUID(os.environ.get("GLICO_PROFISSIONAL_UNIDADE_ID", ""))
    except ValueError:
        raise HTTPException(503, "Vínculo do profissional de demonstração não configurado.") from None


def ator_autenticado(credencial: Credencial) -> Ator:
    """Valida o token do usuário. Só os BFFs o recebem; os serviços recebem a identidade delegada."""
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


def exigir_unidade(profissional: Ator, unidade_id: UUID) -> None:
    if profissional.unidadeId != unidade_id:
        raise HTTPException(403, "Ator sem acesso à unidade.")


def ator_delegado(papel: str | None, ator_id: str | None, unidade: str | None, *, aceita_cidadao: bool = False) -> Ator:
    # shortcut: cabeçalhos de ator só valem junto da credencial de um serviço autorizado; trocar por token delegado assinado.
    if aceita_cidadao and papel == "CIDADAO" and ator_id:
        return Ator("CIDADAO", ator_id)
    if papel != "PROFISSIONAL" or not ator_id:
        raise HTTPException(403, "Ator delegado ausente ou sem papel permitido.")
    try:
        return Ator("PROFISSIONAL", ator_id, UUID(unidade or ""))
    except ValueError:
        raise HTTPException(403, "Unidade do ator delegado inválida.") from None


CabecalhoPapel = Annotated[str | None, Header(alias="X-Ator-Papel")]
CabecalhoAtor = Annotated[str | None, Header(alias="X-Ator-Id", max_length=200)]
CabecalhoUnidade = Annotated[str | None, Header(alias="X-Ator-Unidade-Id")]


def cabecalhos_do_ator(papel: str, ator_id: str, unidade_id) -> dict[str, str]:
    cabecalhos = {"X-Ator-Papel": papel, "X-Ator-Id": ator_id}
    if unidade_id is not None:
        cabecalhos["X-Ator-Unidade-Id"] = str(unidade_id)
    return cabecalhos


def delegar(variavel: str, ator: Ator) -> dict[str, str]:
    """Cabeçalhos do BFF: credencial própria e identidade já autenticada. O token do usuário não é repassado."""
    return {"Authorization": "Bearer " + os.environ.get(variavel, ""), **cabecalhos_do_ator(ator.papel, ator.id, ator.unidadeId)}


def ator_do_bff(
    credencial: Credencial, papel: CabecalhoPapel = None, ator_id: CabecalhoAtor = None, unidade: CabecalhoUnidade = None,
) -> Ator:
    """Identidade delegada por um BFF. A credencial é verificada antes de os cabeçalhos serem considerados."""
    recebido = exigir_credencial(credencial)
    permitidos = [papel_bff for variavel, papel_bff in PAPEL_DO_BFF.items() if corresponde(recebido, variavel)]
    if not permitidos:
        recusar_chamador(recebido)
    if papel != permitidos[0]:
        raise HTTPException(403, "O BFF não pode agir em nome deste ator.")
    return ator_delegado(papel, ator_id, unidade, aceita_cidadao=True)


AtorDelegado = Annotated[Ator, Depends(ator_do_bff)]


def exigir_papel(papel: str):
    def verificar(ator: AtorDelegado) -> Ator:
        if ator.papel != papel:
            raise HTTPException(403, {"codigo": CHAMADOR_NAO_AUTORIZADO, "mensagem": "Operação restrita a outro público."})
        return ator
    return verificar


CidadaoDelegado = Annotated[Ator, Depends(exigir_papel("CIDADAO"))]
ProfissionalDelegado = Annotated[Ator, Depends(exigir_papel("PROFISSIONAL"))]


def ator_do_orquestrador(
    credencial: Credencial, papel: CabecalhoPapel = None, ator_id: CabecalhoAtor = None, unidade: CabecalhoUnidade = None,
) -> Ator:
    orquestrador_autenticado(credencial)
    return ator_delegado(papel, ator_id, unidade, aceita_cidadao=True)


def leitor_de_unidade(
    credencial: Credencial, papel: CabecalhoPapel = None, ator_id: CabecalhoAtor = None, unidade: CabecalhoUnidade = None,
) -> Ator | Literal["RESERVAS", "BFF_CIDADAO"]:
    """Reservas e BFF Cidadão leem com credencial própria; o profissional, por delegação do BFF Unidade."""
    recebido = exigir_credencial(credencial)
    if corresponde(recebido, TOKEN_RESERVAS):
        return "RESERVAS"
    if corresponde(recebido, TOKEN_BFF_CIDADAO):
        return "BFF_CIDADAO"
    return ator_do_bff(credencial, papel, ator_id, unidade)
