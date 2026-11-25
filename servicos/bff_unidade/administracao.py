"""Cadastro da unidade e estoque: encaminha ao serviço dono da regra."""
from uuid import UUID

from fastapi import APIRouter, Response

from servicos.bff_unidade.contexto import API, Comando, Consulta, caminho_unidade
from servicos.bff_unidade.representacoes import (
    ESTOQUE_PAINEL, ITENS_CATALOGO, UNIDADE, CatalogoUnidade, EstoquePainelItem, UnidadeOperacional,
)
from servicos.estoque.esquemas import AjusteFisico, EntradaFisica, PermissaoInput
from servicos.unidades.esquemas import HorariosUnidade, PrazoAnalise, StatusUnidade, UnidadeInput


rotas = APIRouter(prefix=API)


@rotas.get("/unidade", response_model=UnidadeOperacional)
async def consultar_unidade(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await servicos.obter("unidades", caminho_unidade(servicos), UNIDADE)


@rotas.put("/unidade")
async def atualizar_unidade(corpo: UnidadeInput, servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos), corpo)


@rotas.put("/unidade/horarios")
async def atualizar_horarios(corpo: HorariosUnidade, servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos, "/horarios"), corpo)


@rotas.put("/unidade/prazo-analise")
async def atualizar_prazo(corpo: PrazoAnalise, servicos: Comando):
    return await servicos.comandar("unidades", "PUT", caminho_unidade(servicos, "/prazo-analise"), corpo)


@rotas.patch("/unidade/status")
async def alterar_status(corpo: StatusUnidade, servicos: Comando):
    return await servicos.comandar("unidades", "PATCH", caminho_unidade(servicos, "/status"), corpo)


@rotas.get("/painel/estoque", response_model=list[EstoquePainelItem])
async def painel_estoque(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await servicos.obter("estoque", f"{API}/estoque/{servicos.ator.unidadeId}/itens", ESTOQUE_PAINEL)


@rotas.get("/painel/estoque/catalogo", response_model=CatalogoUnidade, response_model_exclude_none=True)
async def catalogo_estoque(servicos: Consulta, response: Response):
    response.headers["Cache-Control"] = "no-store"
    itens = await servicos.obter("estoque", f"{API}/estoque/itens", ITENS_CATALOGO)
    return CatalogoUnidade(unidadeId=servicos.ator.unidadeId, itens=itens)


@rotas.put("/painel/estoque/{unidadeId}/itens/{itemId}/permissao")
async def configurar_permissao(unidadeId: UUID, itemId: UUID, corpo: PermissaoInput, servicos: Comando):
    return await servicos.comandar("estoque", "PUT", f"{API}/estoque/{unidadeId}/itens/{itemId}/permissao", corpo)


@rotas.post("/painel/estoque/{unidadeId}/itens/{itemId}/entradas", status_code=201)
async def registrar_entrada(unidadeId: UUID, itemId: UUID, corpo: EntradaFisica, servicos: Comando):
    return await servicos.comandar("estoque", "POST", f"{API}/estoque/{unidadeId}/itens/{itemId}/entradas", corpo)


@rotas.post("/painel/estoque/{unidadeId}/itens/{itemId}/ajustes", status_code=201)
async def registrar_ajuste(unidadeId: UUID, itemId: UUID, corpo: AjusteFisico, servicos: Comando):
    return await servicos.comandar("estoque", "POST", f"{API}/estoque/{unidadeId}/itens/{itemId}/ajustes", corpo)
