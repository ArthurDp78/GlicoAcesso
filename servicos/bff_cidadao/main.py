from fastapi import FastAPI


app = FastAPI(title="GlicoAcesso — BFF Cidadão")


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    """Informa que o processo HTTP do BFF Cidadão está respondendo."""
    return {"servico": "bff-cidadao", "status": "ok"}
