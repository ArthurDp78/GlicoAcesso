from fastapi import FastAPI


app = FastAPI(title="GlicoAcesso — API Gateway")


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    """Informa que o processo HTTP do Gateway está respondendo."""
    return {"servico": "gateway", "status": "ok"}
