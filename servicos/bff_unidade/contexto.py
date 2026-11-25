"""Dependências das rotas: profissional autenticado e acesso delegado aos serviços."""
from typing import Annotated

from fastapi import Depends, Request

from servicos.bff import Servicos
from servicos.comandos import Chave
from servicos.identidade_demo import TOKEN_BFF_UNIDADE, Ator, profissional_autenticado


API = "/api/unidade/v1"
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


def consulta(request: Request, profissional: Profissional) -> Servicos:
    return Servicos(request, TOKEN_BFF_UNIDADE, profissional)


def comando(request: Request, profissional: Profissional, chave: Chave) -> Servicos:
    return Servicos(request, TOKEN_BFF_UNIDADE, profissional, chave)


Consulta = Annotated[Servicos, Depends(consulta)]
Comando = Annotated[Servicos, Depends(comando)]
