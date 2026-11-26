"""Catálogo, permissão de reserva, entradas e ajustes físicos."""
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation

from servicos.banco import conectar
from servicos.comandos import INTEIRO_MAXIMO, Chave, Correlacao, cadastro_conflitante, responder, resumir
from servicos.estoque.esquemas import AjusteFisico, EntradaFisica, ItemInput, Movimentacao, PermissaoInput
from servicos.estoque.saldos import CAMPOS_SALDO, registrar_evento, travar_saldo, variar_saldo
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import Ator, ProfissionalDelegado, administracao_autenticada, exigir_unidade


rotas = APIRouter()
BANCO = "ESTOQUE_DATABASE_URL"
Profissional = ProfissionalDelegado
Administracao = Annotated[str, Depends(administracao_autenticada)]


def salvar_item(conexao, dados: ItemInput, item_id: UUID | None):
    if item_id is None:
        return conexao.execute("""
            INSERT INTO itens (nome, tipo, descricao, item_id) VALUES (%s, %s, %s, %s)
            RETURNING item_id, nome, tipo, descricao
        """, (dados.nome, dados.tipo, dados.descricao, uuid4())).fetchone()
    # Uma duplicidade anterior à regra é mantida enquanto a identidade do item não mudar.
    return conexao.execute("""
        UPDATE itens SET nome = %s, tipo = %s, descricao = %s, updated_at = now(),
            duplicidade_legada = duplicidade_legada AND identidade = identidade_item(%s, %s)
        WHERE item_id = %s RETURNING item_id, nome, tipo, descricao
    """, (dados.nome, dados.tipo, dados.descricao, dados.nome, dados.tipo, item_id)).fetchone()


def gravar_item(principal: str, chave: str, dados: ItemInput, item_id: UUID | None = None):
    """Cadastra (sem item_id) ou atualiza um item do catálogo."""
    operacao = "cadastrar-item" if item_id is None else "atualizar-item"
    resumo = resumir(item_id, dados.model_dump_json())
    with conectar(BANCO) as conexao:
        if (anterior := resultado_anterior(conexao, operacao, principal, chave, resumo)) is not None:
            return anterior
        try:
            with conexao.transaction():
                linha = salvar_item(conexao, dados, item_id)
        except UniqueViolation as erro:
            resultado = cadastro_conflitante(erro, "item_identidade_unica", "Já existe item com este nome e tipo.")
            return gravar_resultado(conexao, operacao, principal, chave, resumo, resultado)
        if linha is None:
            raise HTTPException(404, "Item não encontrado.")
        corpo = {"itemId": str(linha["item_id"]), "nome": linha["nome"], "tipo": linha["tipo"]}
        if linha["descricao"] is not None:
            corpo["descricao"] = linha["descricao"]
        return gravar_resultado(conexao, operacao, principal, chave, resumo, (201 if item_id is None else 200, corpo))


def configurar_permissao(profissional: Ator, unidade_id: UUID, item_id: UUID, dados: PermissaoInput, chave: str, correlacao):
    exigir_unidade(profissional, unidade_id)
    resumo = resumir(unidade_id, item_id, dados.model_dump_json())
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, "configurar-permissao", profissional.id, chave, resumo)
        if anterior is None:
            anterior = resultado_anterior(conexao, "configurar-reserva", profissional.id, chave, resumo)
            if anterior is not None and anterior[0] == 200:
                # A resposta da main não incluía os identificadores que o contrato atual exige.
                return 200, {"unidadeId": str(unidade_id), "itemId": str(item_id), **anterior[1]}
        if anterior is not None:
            return anterior
        if conexao.execute("SELECT 1 FROM itens WHERE item_id = %s", (item_id,)).fetchone() is None:
            raise HTTPException(404, "Item não encontrado.")
        criado = conexao.execute("""
            INSERT INTO saldos (unidade_id, item_id, estoque_fisico_atual, permite_reserva)
            VALUES (%s, %s, 0, %s) ON CONFLICT DO NOTHING RETURNING unidade_id
        """, (unidade_id, item_id, dados.permiteReserva)).fetchone()
        saldo = travar_saldo(conexao, unidade_id, item_id)
        # Sem mudança de estado não há novo fato a publicar.
        if criado is not None or saldo["permite_reserva"] != dados.permiteReserva:
            saldo = conexao.execute(f"""
                UPDATE saldos SET permite_reserva = %s, estoque_version = estoque_version + 1, updated_at = clock_timestamp()
                WHERE unidade_id = %s AND item_id = %s RETURNING {CAMPOS_SALDO}
            """, (dados.permiteReserva, unidade_id, item_id)).fetchone()
            registrar_evento(conexao, "estoque.permissao-reserva-alterada.v1", "SaldoEstoque",
                             f"{unidade_id}:{item_id}", correlacao, saldo, {})
        resultado = 200, {"unidadeId": str(unidade_id), "itemId": str(item_id), "permiteReserva": dados.permiteReserva}
        return gravar_resultado(conexao, "configurar-permissao", profissional.id, chave, resumo, resultado)


def movimentar(operacao: str, evento: str, profissional: Ator, unidade_id: UUID, item_id: UUID, variacao: int,
               motivo: str, chave: str, correlacao, resumo_legado: str):
    """Saldo, movimentação, evento e resultado idempotente na mesma transação."""
    exigir_unidade(profissional, unidade_id)
    resumo = resumir(unidade_id, item_id, variacao, motivo)
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(
            conexao, operacao, profissional.id, chave, resumo,
            resumo_legado=resumo_legado if operacao == "registrar-entrada" else None,
        )
        if anterior is None and operacao == "registrar-ajuste":
            anterior = resultado_anterior(conexao, "ajustar-estoque", profissional.id, chave, resumo_legado)
        if anterior is not None:
            return anterior
        if operacao == "registrar-entrada":
            conexao.execute("""
                INSERT INTO saldos (unidade_id, item_id, estoque_fisico_atual, permite_reserva)
                SELECT %s, item_id, 0, false FROM itens WHERE item_id = %s
                ON CONFLICT DO NOTHING
            """, (unidade_id, item_id))
        saldo = travar_saldo(conexao, unidade_id, item_id)
        if saldo is None:
            raise HTTPException(404, "Item ou saldo da unidade não encontrado.")
        resultante = saldo["estoque_fisico_atual"] + variacao
        if resultante > INTEIRO_MAXIMO:
            raise HTTPException(422, "A quantidade resultante excede o limite do saldo.")
        if resultante < saldo["quantidade_alocada"]:
            resultado = 409, {"codigo": "AJUSTE_INCOMPATIVEL",
                              "mensagem": "O ajuste reduziria o estoque físico abaixo da quantidade alocada."}
            return gravar_resultado(conexao, operacao, profissional.id, chave, resumo, resultado)
        saldo = variar_saldo(conexao, unidade_id, item_id, fisico=variacao)
        movimentacao_id = uuid4()
        conexao.execute("""
            INSERT INTO movimentacoes (movimentacao_id, unidade_id, item_id, variacao_fisica, ocorrida_em, ator_id, motivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (movimentacao_id, unidade_id, item_id, variacao, saldo["updated_at"], profissional.id, motivo))
        registrar_evento(conexao, evento, "MovimentacaoEstoque", movimentacao_id, correlacao, saldo, {
            "movimentacaoId": str(movimentacao_id), "variacaoFisica": variacao})
        corpo = Movimentacao(movimentacaoId=movimentacao_id, unidadeId=unidade_id, itemId=item_id, variacaoFisica=variacao,
                             ocorridaEm=saldo["updated_at"], estoqueVersion=saldo["estoque_version"])
        return gravar_resultado(conexao, operacao, profissional.id, chave, resumo, (201, corpo.model_dump(mode="json")))


@rotas.post("/internal/v1/itens", status_code=201)
def cadastrar_item(dados: ItemInput, principal: Administracao, chave: Chave):
    return responder(gravar_item(principal, chave, dados))


@rotas.put("/internal/v1/itens/{itemId}")
def atualizar_item(itemId: UUID, dados: ItemInput, principal: Administracao, chave: Chave):
    return responder(gravar_item(principal, chave, dados, itemId))


@rotas.put("/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/permissao")
def alterar_permissao(unidadeId: UUID, itemId: UUID, dados: PermissaoInput, profissional: Profissional, chave: Chave,
                      correlacao: Correlacao = None):
    return responder(configurar_permissao(profissional, unidadeId, itemId, dados, chave, correlacao))


@rotas.post("/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/entradas", status_code=201, response_model=Movimentacao)
def registrar_entrada(unidadeId: UUID, itemId: UUID, dados: EntradaFisica, profissional: Profissional, chave: Chave,
                      correlacao: Correlacao = None):
    legado = resumir(unidadeId, itemId, dados.model_dump_json())
    return responder(movimentar("registrar-entrada", "estoque.entrada-registrada.v1", profissional, unidadeId, itemId,
                                dados.quantidade, dados.motivo, chave, correlacao, legado))


@rotas.post("/api/unidade/v1/estoque/{unidadeId}/itens/{itemId}/ajustes", status_code=201, response_model=Movimentacao)
def registrar_ajuste(unidadeId: UUID, itemId: UUID, dados: AjusteFisico, profissional: Profissional, chave: Chave,
                     correlacao: Correlacao = None):
    legado = resumir(unidadeId, itemId, dados.model_dump_json())
    return responder(movimentar("registrar-ajuste", "estoque.ajustado.v1", profissional, unidadeId, itemId,
                                dados.variacaoFisica, dados.motivo, chave, correlacao, legado))
