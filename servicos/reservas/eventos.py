from servicos.banco import conectar
from servicos.contratos_retirada import EventoRetirada
from servicos.mensageria import FILAS_RETIRADA, registrar_inbox


FILA = FILAS_RETIRADA["reservas"]


def aplicar_retirada(corpo: bytes) -> None:
    evento = EventoRetirada.model_validate_json(corpo)
    entrega = evento.payload
    with conectar("RESERVAS_DATABASE_URL") as conexao:
        if not registrar_inbox(conexao, FILA, evento.eventId):
            return
        reserva = conexao.execute("""
            SELECT unidade_id, item_id, quantidade, status, retirada_id FROM reservas
            WHERE reserva_id = %s FOR UPDATE
        """, (entrega.reservaId,)).fetchone()
        if (reserva is None or (reserva["unidade_id"], reserva["item_id"], reserva["quantidade"])
                != (entrega.unidadeId, entrega.itemId, entrega.quantidade)):
            raise ValueError(f"Reserva incompatível com a retirada {entrega.retiradaId}.")
        if reserva["status"] == "RETIRADA" and reserva["retirada_id"] == entrega.retiradaId:
            return
        if reserva["status"] not in ("CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO"):
            raise ValueError(f"Reserva {entrega.reservaId} em estado incompatível: {reserva['status']}.")

        conexao.execute("""
            UPDATE reservas SET status = 'RETIRADA', retirada_id = %s, atualizada_em = clock_timestamp()
            WHERE reserva_id = %s
        """, (entrega.retiradaId, entrega.reservaId))
        conexao.execute("""
            INSERT INTO historico_reserva (historico_id, reserva_id, status_anterior, status_posterior,
                                           ocorrido_em, ator_id)
            VALUES (%s, %s, %s, 'RETIRADA', %s, 'retiradas')
        """, (evento.eventId, entrega.reservaId, reserva["status"], evento.occurredAt))
