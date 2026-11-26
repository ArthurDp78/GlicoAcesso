"""Modelos das respostas compostas apresentadas no painel da unidade."""
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, TypeAdapter


class EstoquePainelItem(BaseModel):
    itemId: UUID
    unidadeId: UUID
    itemNome: str
    estoqueFisicoAtual: int
    quantidadeAlocada: int
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: str  # Instante da projeção, não da consulta.


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


class ItemCatalogo(BaseModel):
    itemId: UUID
    nome: str
    tipo: Literal["MEDICAMENTO", "INSUMO"]
    descricao: str | None = None


class CatalogoUnidade(BaseModel):
    unidadeId: UUID
    itens: list[ItemCatalogo]


ESTOQUE_PAINEL = TypeAdapter(list[EstoquePainelItem])
UNIDADE = TypeAdapter(UnidadeOperacional)
ITENS_CATALOGO = TypeAdapter(list[ItemCatalogo])
