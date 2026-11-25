"""Comandos administrativos de Unidades: efeito e resultado idempotente na mesma transação."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from servicos.banco import conectar
from servicos.comandos import Chave, cadastro_conflitante, responder, resumir
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import Ator, ProfissionalDelegado, administracao_autenticada, exigir_unidade
from servicos.unidades import repositorio
from servicos.unidades.esquemas import HorariosUnidade, PrazoAnalise, StatusUnidade, UnidadeCadastro, UnidadeInput


rotas = APIRouter()
BANCO = "UNIDADES_DATABASE_URL"
Profissional = ProfissionalDelegado
Administracao = Annotated[str, Depends(administracao_autenticada)]
OPERACOES_MAIN = {
    "atualizar-unidade": "atualizar-cadastro",
    "substituir-horarios": "atualizar-horarios",
    "alterar-status": "atualizar-situacao",
    "configurar-prazo": "atualizar-prazo",
}


def cadastrar(principal: str, chave: str, dados: UnidadeInput):
    resumo = resumir(dados.model_dump_json())
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, "cadastrar-unidade", principal, chave, resumo)
        if anterior is None:
            anterior = resultado_anterior(conexao, "cadastrar-unidade", "gestor-rede-demo", chave, resumo)
        if anterior is not None:
            return anterior
        try:
            with conexao.transaction():
                unidade_id = repositorio.inserir(conexao, dados)
            resultado = 201, repositorio.cadastro_json(conexao, unidade_id)
        except UniqueViolation as erro:
            resultado = cadastro_conflitante(erro, "unidade_identidade_unica", "Já existe unidade com este nome e endereço.")
        return gravar_resultado(conexao, "cadastrar-unidade", principal, chave, resumo, resultado)


def alterar(operacao: str, profissional: Ator, unidade_id: UUID, chave: str, dados, aplicar):
    exigir_unidade(profissional, unidade_id)
    resumo = resumir(unidade_id, dados.model_dump_json())
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, operacao, profissional.id, chave, resumo)
        if anterior is None:
            anterior = resultado_anterior(conexao, OPERACOES_MAIN[operacao], profissional.id, chave, resumo)
        if anterior is not None:
            return anterior
        if not repositorio.travar(conexao, unidade_id):
            raise HTTPException(404, "Unidade não encontrada.")
        try:
            with conexao.transaction():
                aplicar(conexao)
            resultado = 200, repositorio.cadastro_json(conexao, unidade_id)
        except UniqueViolation as erro:
            resultado = cadastro_conflitante(erro, "unidade_identidade_unica", "Já existe unidade com este nome e endereço.")
        return gravar_resultado(conexao, operacao, profissional.id, chave, resumo, resultado)


@rotas.post("/internal/v1/unidades", status_code=201, response_model=UnidadeCadastro)
def cadastrar_unidade(dados: UnidadeInput, principal: Administracao, chave: Chave):
    return responder(cadastrar(principal, chave, dados))


@rotas.put("/internal/v1/unidades/{unidadeId}", response_model=UnidadeCadastro)
def atualizar_unidade(unidadeId: UUID, dados: UnidadeInput, profissional: Profissional, chave: Chave):
    return responder(alterar("atualizar-unidade", profissional, unidadeId, chave, dados,
                             lambda conexao: repositorio.atualizar(conexao, unidadeId, dados)))


@rotas.put("/internal/v1/unidades/{unidadeId}/horarios", response_model=UnidadeCadastro)
def substituir_horarios(unidadeId: UUID, dados: HorariosUnidade, profissional: Profissional, chave: Chave):
    return responder(alterar("substituir-horarios", profissional, unidadeId, chave, dados,
                             lambda conexao: repositorio.substituir_horarios(conexao, unidadeId, dados.horarios)))


@rotas.patch("/internal/v1/unidades/{unidadeId}/status", response_model=UnidadeCadastro)
def alterar_status(unidadeId: UUID, dados: StatusUnidade, profissional: Profissional, chave: Chave):
    return responder(alterar("alterar-status", profissional, unidadeId, chave, dados,
                             lambda conexao: repositorio.definir_status(conexao, unidadeId, dados.ativa)))


@rotas.put("/internal/v1/unidades/{unidadeId}/prazo-analise", response_model=UnidadeCadastro)
def configurar_prazo(unidadeId: UUID, dados: PrazoAnalise, profissional: Profissional, chave: Chave):
    return responder(alterar("configurar-prazo", profissional, unidadeId, chave, dados,
                             lambda conexao: repositorio.definir_prazo(conexao, unidadeId, dados.prazoAnaliseHoras)))
