"""Dependências das rotas: profissional autenticado e acesso delegado aos serviços."""
from typing import Annotated

from fastapi import Depends, Request

from servicos.bff import Servicos
from servicos.comandos import Chave
from servicos.identidade_demo import TOKEN_BFF_UNIDADE, Ator, profissional_autenticado


API = "/api/unidade/v1"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


def caminho_unidade(servicos, sufixo: str = "") -> str:
    # A unidade vem do vínculo autenticado, nunca do cliente.
    return f"/internal/v1/unidades/{servicos.ator.unidadeId}{sufixo}"


def consulta(request: Request, profissional: Profissional) -> Servicos:
    return Servicos(request, TOKEN_BFF_UNIDADE, profissional)


def comando(request: Request, profissional: Profissional, chave: Chave) -> Servicos:
    return Servicos(request, TOKEN_BFF_UNIDADE, profissional, chave)


Consulta = Annotated[Servicos, Depends(consulta)]
Comando = Annotated[Servicos, Depends(comando)]
