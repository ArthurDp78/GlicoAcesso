import os
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from servicos.http import cliente_http, consultar, correlacionar, requisitar
from servicos.identidade_demo import cidadao_autenticado, profissional_autenticado


PASTA_PORTAL = Path(__file__).resolve().parent / "portal"
LOGO = Path(__file__).resolve().parents[2] / "identidade-visual" / "logo-sem-fundo.png"
app = FastAPI(title="GlicoAcesso — API Gateway", lifespan=cliente_http)
app.middleware("http")(correlacionar)
app.mount("/cidadao/assets", StaticFiles(directory=PASTA_PORTAL), name="portal-cidadao")
app.mount("/unidade/assets", StaticFiles(directory=PASTA_PORTAL), name="portal-unidade")


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "gateway", "status": "ok"}


@app.get("/cidadao", include_in_schema=False)
def portal_cidadao():
    return FileResponse(PASTA_PORTAL / "index.html")


@app.get("/unidade", include_in_schema=False)
def portal_unidade():
    return FileResponse(PASTA_PORTAL / "unidade.html")


@app.get("/cidadao/logo.png", include_in_schema=False)
@app.get("/unidade/logo.png", include_in_schema=False)
def logo_portal():
    return FileResponse(LOGO, media_type="image/png")


@app.get("/api/cidadao/v1/itens")
@app.get("/api/cidadao/v1/unidades")
@app.get("/api/cidadao/v1/explorar")
async def encaminhar_consulta(request: Request) -> Response:
    destino = os.environ.get("BFF_CIDADAO_URL", "http://127.0.0.1:8001").rstrip("/")
    resposta = await consultar(
        request.app.state.http, destino + request.url.path, params=request.query_params.multi_items()
    )
    return Response(
        content=resposta.content,
        status_code=resposta.status_code,
        media_type=resposta.headers.get("content-type", "application/json"),
    )

@app.post("/api/cidadao/v1/reservas", status_code=201, dependencies=[Depends(cidadao_autenticado)])
@app.get("/api/cidadao/v1/reservas/{reservaId}", dependencies=[Depends(cidadao_autenticado)])
@app.post("/api/cidadao/v1/reservas/{reservaId}/cancelar", dependencies=[Depends(cidadao_autenticado)])
async def encaminhar_reserva(request: Request, reservaId: UUID | None = None) -> Response:
    return await repassar(request, os.environ.get("BFF_CIDADAO_URL", "http://127.0.0.1:8001"))


PROFISSIONAL = [Depends(profissional_autenticado)]


@app.post("/api/unidade/v1/retiradas", status_code=201, dependencies=PROFISSIONAL)
@app.get("/api/unidade/v1/unidade", dependencies=PROFISSIONAL)
@app.put("/api/unidade/v1/unidade", dependencies=PROFISSIONAL)
@app.put("/api/unidade/v1/unidade/horarios", dependencies=PROFISSIONAL)
@app.patch("/api/unidade/v1/unidade/status", dependencies=PROFISSIONAL)
@app.put("/api/unidade/v1/unidade/prazo-analise", dependencies=PROFISSIONAL)
@app.put("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/permissao", dependencies=PROFISSIONAL)
@app.post("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/ajustes", status_code=201, dependencies=PROFISSIONAL)
@app.get("/api/unidade/v1/painel/estoque", dependencies=PROFISSIONAL)
@app.get("/api/unidade/v1/painel/estoque/catalogo", dependencies=PROFISSIONAL)
@app.post("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/entradas", status_code=201, dependencies=PROFISSIONAL)
@app.get("/api/unidade/v1/painel/reservas", dependencies=PROFISSIONAL)
@app.get("/api/unidade/v1/painel/reservas/{reservaId}", dependencies=PROFISSIONAL)
@app.post("/api/unidade/v1/reservas/{reservaId}/decisao", dependencies=PROFISSIONAL)
@app.post("/api/unidade/v1/reservas/{reservaId}/cancelar", dependencies=PROFISSIONAL)
async def encaminhar_unidade(request: Request, reservaId: UUID | None = None) -> Response:
    return await repassar(request, os.environ.get("BFF_UNIDADE_URL", "http://127.0.0.1:8005"))


async def repassar(request: Request, destino: str) -> Response:
    destino = destino.rstrip("/")
    cabecalhos = {
        nome: request.headers[nome]
        for nome in ("authorization", "idempotency-key", "content-type")
        if nome in request.headers
    }
    resposta = await requisitar(
        request.app.state.http, request.method, destino + request.url.path,
        headers=cabecalhos, content=await request.body(), params=request.query_params.multi_items(),
    )
    return Response(
        content=resposta.content,
        status_code=resposta.status_code,
        headers={
            nome: resposta.headers[nome]
            for nome in ("content-type", "cache-control", "location", "www-authenticate")
            if nome in resposta.headers
        },
    )
