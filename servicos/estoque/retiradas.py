from uuid import uuid4

from servicos.banco import conectar
from servicos.contratos_retirada import EventoRetirada
from servicos.estoque.eventos import BANCO, registrar_evento
from servicos.mensageria import FILAS_RETIRADA, registrar_inbox


FILA = FILAS_RETIRADA["estoque"]


def aplicar_retirada(corpo: bytes) -> None:
    evento = EventoRetirada.model_validate_json(corpo)
    entrega = evento.payload
    with conectar(BANCO) as conexao:
        if not registrar_inbox(conexao, FILA, evento.eventId):
            return

        alocacao = conexao.execute("""
            SELECT unidade_id, item_id, quantidade, liberada_em, consumida_em, retirada_id
            FROM alocacoes WHERE reserva_id = %s FOR UPDATE
        """, (entrega.reservaId,)).fetchone()
        if (alocacao is None or alocacao["liberada_em"] is not None
                or (alocacao["unidade_id"], alocacao["item_id"], alocacao["quantidade"])
                != (entrega.unidadeId, entrega.itemId, entrega.quantidade)):
            raise ValueError(f"Alocação incompatível com a retirada {entrega.retiradaId}.")
        if alocacao["consumida_em"] is not None:
            if alocacao["retirada_id"] != entrega.retiradaId:
                raise ValueError(f"Alocação da reserva {entrega.reservaId} já consumida por outra retirada.")
            return

        saldo = conexao.execute("""
            UPDATE saldos SET estoque_fisico_atual = estoque_fisico_atual - %(quantidade)s,
                quantidade_alocada = quantidade_alocada - %(quantidade)s,
                estoque_version = estoque_version + 1, updated_at = clock_timestamp()
            WHERE unidade_id = %(unidadeId)s AND item_id = %(itemId)s
              AND quantidade_alocada >= %(quantidade)s
            RETURNING unidade_id, item_id, estoque_fisico_atual, quantidade_alocada,
                      permite_reserva, estoque_version, updated_at
        """, entrega.model_dump()).fetchone()
        if saldo is None:
            raise ValueError(f"Saldo incompatível com a alocação da reserva {entrega.reservaId}.")

        conexao.execute("""
            UPDATE alocacoes SET consumida_em = %s, retirada_id = %s, updated_at = clock_timestamp()
            WHERE reserva_id = %s
        """, (evento.occurredAt, entrega.retiradaId, entrega.reservaId))
        movimento_id = uuid4()
        conexao.execute("""
            INSERT INTO movimentacoes (movimentacao_id, unidade_id, item_id, variacao_fisica, estoque_version,
                                       ocorrida_em, ator_id, motivo)
            VALUES (%s, %s, %s, %s, %s, %s, 'retiradas', 'Entrega no balcão')
        """, (movimento_id, entrega.unidadeId, entrega.itemId, -entrega.quantidade, saldo["estoque_version"],
              evento.occurredAt))
        registrar_evento(
            conexao, "estoque.retirada-baixada.v1", "MovimentacaoEstoque", movimento_id, evento.correlationId,
            saldo, {"retiradaId": str(entrega.retiradaId), "reservaId": str(entrega.reservaId),
                    "quantidadeBaixada": entrega.quantidade}, causacao=evento.eventId,
        )
