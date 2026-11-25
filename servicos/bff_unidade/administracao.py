"""Cadastro da unidade e estoque: encaminha ao serviço dono da regra."""
from uuid import UUID

from fastapi import APIRouter, Response
from pydantic import BaseModel, TypeAdapter

from servicos.bff_unidade.contexto import API, Comando, Consulta


rotas = APIRouter(prefix=API)


class EstoquePainelItem(BaseModel):
    itemId: UUID
    unidadeId: UUID
    itemNome: str
    estoqueFisicoAtual: int
    quantidadeAlocada: int
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: str  # Repassado como veio da projeção: é o instante do estado, não da consulta.


class UnidadeOperacional(BaseModel):
    unidadeId: UUID
    nome: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str
    contatos: list[dict[str, str]]
    horarios: list[dict[str, int | str]]
    prazoAnaliseHoras: int
    ativa: bool


ESTOQUE_PAINEL = TypeAdapter(list[EstoquePainelItem])
UNIDADE = TypeAdapter(UnidadeOperacional)


def caminho_unidade(servicos, sufixo: str = "") -> str:
    # A unidade vem do vínculo autenticado, nunca do cliente.
    return f"/internal/v1/unidades/{servicos.ator.unidadeId}{sufixo}"


@rotas.get("/unidade", response_model=UnidadeOperacional)
async def consultar_unidade(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await servicos.obter("unidades", caminho_unidade(servicos), UNIDADE)


@rotas.put("/unidade")
async def atualizar_unidade(servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos))


@rotas.put("/unidade/horarios")
async def atualizar_horarios(servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos, "/horarios"))


@rotas.put("/unidade/prazo-analise")
async def atualizar_prazo(servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos, "/prazo-analise"))


@rotas.patch("/unidade/status")
async def alterar_status(servicos: Comando):
    return await servicos.comandar("unidades", "PATCH", caminho_unidade(servicos, "/status"))


@rotas.get("/painel/estoque", response_model=list[EstoquePainelItem])
async def painel_estoque(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await servicos.obter("estoque", f"{API}/estoque/{servicos.ator.unidadeId}/itens", ESTOQUE_PAINEL)


@rotas.put("/painel/estoque/{unidadeId}/itens/{itemId}/permissao")
async def configurar_permissao(unidadeId: UUID, itemId: UUID, servicos: Comando):
    return await servicos.comandar("estoque", "PUT", f"{API}/estoque/{unidadeId}/itens/{itemId}/permissao")


@rotas.post("/painel/estoque/{unidadeId}/itens/{itemId}/entradas", status_code=201)
async def registrar_entrada(unidadeId: UUID, itemId: UUID, servicos: Comando):
    return await servicos.comandar("estoque", "POST", f"{API}/estoque/{unidadeId}/itens/{itemId}/entradas")


@rotas.post("/painel/estoque/{unidadeId}/itens/{itemId}/ajustes", status_code=201)
async def registrar_ajuste(unidadeId: UUID, itemId: UUID, servicos: Comando):
    return await servicos.comandar("estoque", "POST", f"{API}/estoque/{unidadeId}/itens/{itemId}/ajustes")
