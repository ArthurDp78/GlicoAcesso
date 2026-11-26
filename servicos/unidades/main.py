from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from servicos.banco import BancoIndisponivel, conectar
from servicos.identidade_demo import (
    TOKEN_ADMIN, TOKEN_BFF_CIDADAO, TOKEN_BFF_UNIDADE, TOKEN_RESERVAS, Ator, exigir_credenciais, exigir_unidade,
    leitor_de_unidade, servico_reservas_autenticado,
)
from servicos.unidades import administracao, repositorio
from servicos.unidades.esquemas import PrazoVigente, UnidadeCadastro, UnidadeResumo


@asynccontextmanager
async def ciclo(_app: FastAPI):
    exigir_credenciais(TOKEN_RESERVAS, TOKEN_BFF_CIDADAO, TOKEN_BFF_UNIDADE, TOKEN_ADMIN)
    yield


app = FastAPI(title="GlicoAcesso — Unidades", lifespan=ciclo)
app.include_router(administracao.rotas)
BANCO = "UNIDADES_DATABASE_URL"


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco de Unidades indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "unidades", "status": "ok"}


@app.get("/api/cidadao/v1/unidades", response_model=list[UnidadeResumo])
def listar_unidades():
    with conectar(BANCO) as conexao:
        return repositorio.listar_ativas(conexao)


@app.get("/internal/v1/unidades/{unidadeId}", response_model=UnidadeCadastro | UnidadeResumo)
def consultar_unidade(unidadeId: UUID, leitor: Annotated[Ator | str, Depends(leitor_de_unidade)]):
    if isinstance(leitor, Ator):
        exigir_unidade(leitor, unidadeId)
    with conectar(BANCO) as conexao:
        dados = repositorio.buscar_cadastro(conexao, unidadeId)
    if dados is None:
        raise HTTPException(404, "Unidade não encontrada.")
    # O BFF Cidadão recebe só os campos públicos, inclusive de unidades inativas.
    return UnidadeResumo.model_validate(dados) if leitor == "BFF_CIDADAO" else UnidadeCadastro.model_validate(dados)


@app.get(
    "/internal/v1/unidades/{unidadeId}/prazo-analise",
    response_model=PrazoVigente,
    dependencies=[Depends(servico_reservas_autenticado)],
)
def consultar_prazo_analise_unidade(unidadeId: UUID):
    with conectar(BANCO) as conexao:
        prazo = repositorio.buscar_prazo_de_ativa(conexao, unidadeId)
    if prazo is None:
        raise HTTPException(404, "Unidade não encontrada ou inativa.")
    return prazo
