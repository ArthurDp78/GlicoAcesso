from servicos.bff import criar_app
from servicos.bff_unidade import administracao, reservas
from servicos.bff_unidade.contexto import API
from servicos.erros import entrada_invalida_400
from servicos.identidade_demo import TOKEN_BFF_UNIDADE, TOKEN_PROFISSIONAL


app = criar_app("GlicoAcesso — BFF Unidade", TOKEN_PROFISSIONAL, TOKEN_BFF_UNIDADE)
app.include_router(administracao.rotas)
app.include_router(reservas.rotas)
entrada_invalida_400(app, API + "/reservas/{reservaId}/decisao", API + "/reservas/{reservaId}/cancelar")


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "bff-unidade", "status": "ok"}
