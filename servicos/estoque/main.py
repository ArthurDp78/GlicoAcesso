from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel

from servicos.banco import BancoIndisponivel, conectar


app = FastAPI(title="GlicoAcesso — Estoque")


class Item(BaseModel):
    itemId: UUID
    nome: str
    tipo: Literal["MEDICAMENTO", "INSUMO"]
    descricao: str | None = None


class DisponibilidadeItem(BaseModel):
    itemId: UUID
    unidadeId: UUID
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: AwareDatetime


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco de Estoque indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "estoque", "status": "ok"}


@app.get("/api/cidadao/v1/estoque/itens", response_model=list[Item], response_model_exclude_none=True)
def listar_itens():
    with conectar("ESTOQUE_DATABASE_URL") as conexao:
        return conexao.execute("""
            SELECT item_id AS "itemId", nome, tipo, descricao
            FROM itens
            ORDER BY nome, item_id
        """).fetchall()


@app.get(
    "/api/cidadao/v1/estoque/disponibilidade",
    response_model=DisponibilidadeItem,
    responses={404: {"description": "Combinação de unidade e item sem projeção."}},
)
def consultar_disponibilidade(
    unidade_id: Annotated[UUID, Query(alias="unidadeId")],
    item_id: Annotated[UUID, Query(alias="itemId")],
):
    with conectar("ESTOQUE_DATABASE_URL") as conexao:
        disponibilidade = conexao.execute("""
            SELECT unidade_id AS "unidadeId", item_id AS "itemId",
                   quantidade_disponivel AS "quantidadeDisponivel",
                   permite_reserva AS "permiteReserva", atualizado_em AS "atualizadoEm"
            FROM disponibilidade
            WHERE unidade_id = %s AND item_id = %s
        """, (unidade_id, item_id)).fetchone()
    if disponibilidade is None:
        raise HTTPException(status_code=404, detail="Disponibilidade não encontrada.")
    return disponibilidade
