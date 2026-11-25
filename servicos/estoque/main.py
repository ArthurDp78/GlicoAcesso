import threading
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from servicos.banco import BancoIndisponivel, conectar
from servicos.erros import entrada_invalida_400
from servicos.estoque import administracao
from servicos.estoque.eventos import iniciar
from servicos.estoque.saldos import registrar_evento
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import Ator, orquestrador_autenticado, profissional_autenticado, servico_reservas_autenticado


@asynccontextmanager
async def ciclo(_app: FastAPI):
    parar = threading.Event()
    iniciar(parar)  # Publicador da Outbox, projeção e baixa de retiradas, em segundo plano.
    yield
    parar.set()


app = FastAPI(title="GlicoAcesso — Estoque", lifespan=ciclo)
app.include_router(administracao.rotas)
entrada_invalida_400(app, "/internal/v1/alocacoes", "/internal/v1/alocacoes/{reservaId}")


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


@app.get(
    "/api/unidade/v1/estoque/itens", response_model=list[Item], response_model_exclude_none=True,
    dependencies=[Depends(profissional_autenticado)],
)
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

class PermissaoReserva(BaseModel):
    unidadeId: UUID
    itemId: UUID
    permiteReserva: bool


@app.get(
    "/internal/v1/unidades/{unidadeId}/itens/{itemId}/permissao-reserva",
    response_model=PermissaoReserva, dependencies=[Depends(servico_reservas_autenticado)],
)
def consultar_permissao(unidadeId: UUID, itemId: UUID):
    with conectar("ESTOQUE_DATABASE_URL") as conexao:
        dado = conexao.execute("""
            SELECT unidade_id AS "unidadeId", item_id AS "itemId", permite_reserva AS "permiteReserva"
            FROM saldos WHERE unidade_id = %s AND item_id = %s
        """, (unidadeId, itemId)).fetchone()
    if dado is None:
        raise HTTPException(404, "Combinação de unidade e item não encontrada.")
    return dado


# --- Comandos da SAGA (somente o Orquestrador) ---

BANCO = "ESTOQUE_DATABASE_URL"
PRINCIPAL = "orquestrador"
Orquestrador = Annotated[str, Depends(orquestrador_autenticado)]
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


class PedidoAlocacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sagaId: UUID
    reservaId: UUID
    unidadeId: UUID
    itemId: UUID
    quantidade: Annotated[int, Field(strict=True, ge=1, le=2147483647)]


def alocar(pedido: PedidoAlocacao, chave: str, correlacao: UUID | None):
    resumo = sha256(pedido.model_dump_json().encode()).hexdigest()
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, "alocar-estoque", PRINCIPAL, chave, resumo)) is not None:
            return anterior
        saldo = conexao.execute("""
            SELECT estoque_fisico_atual - quantidade_alocada AS livre, permite_reserva
            FROM saldos WHERE unidade_id = %s AND item_id = %s FOR UPDATE
        """, (pedido.unidadeId, pedido.itemId)).fetchone()
        existente = conexao.execute("SELECT 1 FROM alocacoes WHERE reserva_id = %s", (pedido.reservaId,)).fetchone()
        if saldo is None:
            resultado = 404, {"codigo": "SALDO_NAO_ENCONTRADO", "mensagem": "Item ou saldo da unidade não encontrado."}
        elif existente is not None:
            resultado = 409, {"codigo": "ALOCACAO_INCOMPATIVEL", "mensagem": "A reserva já tem alocação."}
        elif not saldo["permite_reserva"]:
            resultado = 409, {"codigo": "RESERVA_NAO_PERMITIDA", "mensagem": "A unidade não permite reservar o item."}
        elif saldo["livre"] < pedido.quantidade:
            resultado = 409, {"codigo": "SALDO_INSUFICIENTE", "mensagem": f"Disponível: {saldo['livre']}."}
        else:
            alocacao_id = uuid4()
            conexao.execute("""
                INSERT INTO alocacoes (alocacao_id, reserva_id, saga_id, unidade_id, item_id, quantidade,
                    idempotency_key, correlation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (alocacao_id, pedido.reservaId, pedido.sagaId, pedido.unidadeId, pedido.itemId,
                  pedido.quantidade, chave, correlacao))
            saldo = conexao.execute("""
                UPDATE saldos SET quantidade_alocada = quantidade_alocada + %s,
                    estoque_version = estoque_version + 1, updated_at = now()
                WHERE unidade_id = %s AND item_id = %s
                RETURNING unidade_id, item_id, estoque_fisico_atual, quantidade_alocada, permite_reserva,
                    estoque_version, updated_at
            """, (pedido.quantidade, pedido.unidadeId, pedido.itemId)).fetchone()
            registrar_evento(conexao, "estoque.alocacao-criada.v1", "AlocacaoEstoque", alocacao_id, correlacao, saldo, {
                "alocacaoId": str(alocacao_id), "reservaId": str(pedido.reservaId), "quantidade": pedido.quantidade})
            resultado = 201, {"alocacaoId": str(alocacao_id), **pedido.model_dump(mode="json")}
        return gravar_resultado(conexao, "alocar-estoque", PRINCIPAL, chave, resumo, resultado)


def liberar(reserva_id: UUID, saga_id: UUID, chave: str, correlacao: UUID | None):
    resumo = sha256(f"{reserva_id}:{saga_id}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, "liberar-alocacao", PRINCIPAL, chave, resumo)) is not None:
            return anterior
        alocacao = conexao.execute("""
            SELECT alocacao_id, unidade_id, item_id, quantidade, liberada_em, consumida_em
            FROM alocacoes WHERE reserva_id = %s FOR UPDATE
        """, (reserva_id,)).fetchone()
        if alocacao is not None and alocacao["consumida_em"] is not None:
            resultado = 409, {"codigo": "ALOCACAO_CONSUMIDA", "mensagem": "A alocação já foi consumida na retirada."}
        else:
            if alocacao is not None and alocacao["liberada_em"] is None:
                conexao.execute("UPDATE alocacoes SET liberada_em = now(), updated_at = now() WHERE reserva_id = %s",
                                (reserva_id,))
                saldo = conexao.execute("""
                    UPDATE saldos SET quantidade_alocada = quantidade_alocada - %s,
                        estoque_version = estoque_version + 1, updated_at = now()
                    WHERE unidade_id = %s AND item_id = %s
                    RETURNING unidade_id, item_id, estoque_fisico_atual, quantidade_alocada, permite_reserva,
                    estoque_version, updated_at
                """, (alocacao["quantidade"], alocacao["unidade_id"], alocacao["item_id"])).fetchone()
                registrar_evento(conexao, "estoque.alocacao-liberada.v1", "AlocacaoEstoque", alocacao["alocacao_id"],
                                 correlacao, saldo, {"alocacaoId": str(alocacao["alocacao_id"]),
                                                     "reservaId": str(reserva_id), "quantidade": alocacao["quantidade"]})
            # Liberada agora, já liberada ou inexistente: nada a reverter.
            resultado = 204, {}
        return gravar_resultado(conexao, "liberar-alocacao", PRINCIPAL, chave, resumo, resultado)


def responder_comando(resultado) -> Response:
    status, corpo = resultado
    if status == 204:
        return Response(status_code=204)
    return JSONResponse(corpo, status_code=status, headers={"Cache-Control": "no-store"})


@app.post("/internal/v1/alocacoes", status_code=201)
def alocar_estoque(
    pedido: PedidoAlocacao, _orquestrador: Orquestrador, chave: Chave,
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    return responder_comando(alocar(pedido, chave, correlacao))


@app.delete("/internal/v1/alocacoes/{reservaId}", status_code=204)
def liberar_alocacao(
    reservaId: UUID, _orquestrador: Orquestrador, chave: Chave,
    saga_id: Annotated[UUID, Header(alias="X-Saga-Id")],
    correlacao: Annotated[UUID | None, Header(alias="X-Correlation-Id")] = None,
):
    return responder_comando(liberar(reservaId, saga_id, chave, correlacao))


class EstoqueUnidadeItem(BaseModel):
    itemId: UUID
    unidadeId: UUID
    itemNome: str
    estoqueFisicoAtual: int
    quantidadeAlocada: int
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: AwareDatetime


@app.get("/api/unidade/v1/estoque/{unidadeId}/itens", response_model=list[EstoqueUnidadeItem])
def listar_estoque_da_unidade(unidadeId: UUID, profissional: Annotated[Ator, Depends(profissional_autenticado)]):
    # shortcut: confere só o vínculo do token; a checagem de unidade ativa fica em Reservas.
    if unidadeId != profissional.unidadeId:
        raise HTTPException(403, "Ator sem acesso à unidade.")
    with conectar(BANCO) as conexao:
        return conexao.execute("""
            SELECT d.item_id AS "itemId", d.unidade_id AS "unidadeId", i.nome AS "itemNome",
                   d.estoque_fisico_atual AS "estoqueFisicoAtual", d.quantidade_alocada AS "quantidadeAlocada",
                   d.quantidade_disponivel AS "quantidadeDisponivel", d.permite_reserva AS "permiteReserva",
                   d.atualizado_em AS "atualizadoEm"
            FROM disponibilidade d JOIN itens i USING (item_id)
            WHERE d.unidade_id = %s
            ORDER BY i.nome, d.item_id
        """, (unidadeId,)).fetchall()
