import asyncio
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response

from servicos.contratos_orientacao import (
    PedidoOrientacao, RespostaOrientacao, ROTA_INTERNA_ORIENTACAO, TOKEN_ORIENTACAO,
)
from servicos.http import cliente_http, correlacionar
from servicos.identidade_demo import Credencial, validar_token
from servicos.orientacao.rag import PerguntaSobreItem, criar_chain_com_disponibilidade

MAXIMO_EM_EXECUCAO = 3


@asynccontextmanager
async def ciclo(app: FastAPI):
    async with cliente_http(app):
        app.state.limite = asyncio.Semaphore(MAXIMO_EM_EXECUCAO)
        origem = os.getenv("BFF_CIDADAO_URL", "http://127.0.0.1:8001")
        app.state.chain = criar_chain_com_disponibilidade(app.state.http, origem)
        yield


app = FastAPI(title="GlicoAcesso — Orientação", lifespan=ciclo)
app.middleware("http")(correlacionar)


def autenticar_servico(credencial: Credencial) -> None:
    validar_token(credencial, TOKEN_ORIENTACAO)


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "orientacao", "status": "ok"}


@app.post(ROTA_INTERNA_ORIENTACAO, response_model=RespostaOrientacao)
async def orientar(
    pedido: PedidoOrientacao, request: Request, response: Response,
    _interno: Annotated[None, Depends(autenticar_servico)],
):
    limite = request.app.state.limite
    if limite.locked():
        raise HTTPException(429, "O serviço de orientação está ocupado.", headers={"Retry-After": "2"})
    async with limite:
        resultado = await request.app.state.chain.ainvoke(PerguntaSobreItem(pedido.pergunta, pedido.itemId))
    response.headers["Cache-Control"] = "no-store"
    return RespostaOrientacao.model_validate(resultado)
