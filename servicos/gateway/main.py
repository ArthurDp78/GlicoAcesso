from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from servicos import correlacao
from servicos.gateway import rotas
from servicos.http import cliente_http


PASTA_PORTAL = Path(__file__).resolve().parent / "portal"
LOGO = Path(__file__).resolve().parents[2] / "identidade-visual" / "logo-sem-fundo.png"


@asynccontextmanager
async def ciclo(app: FastAPI):
    # Maior que o prazo dos BFFs, que podem encadear duas chamadas em um comando.
    async with cliente_http(app, timeout=20.0):
        yield


app = FastAPI(title="GlicoAcesso — API Gateway", lifespan=ciclo)
correlacao.instalar(app)
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


rotas.instalar(app)
