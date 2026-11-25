from servicos.banco import conectar
from servicos.contratos_retirada import EventoRetirada
from servicos.mensageria import FILAS_RETIRADA, registrar_inbox


FILA = FILAS_RETIRADA["orquestrador"]


def observar_retirada(corpo: bytes) -> None:
    evento = EventoRetirada.model_validate_json(corpo)
    entrega = evento.payload
    with conectar("ORQUESTRADOR_DATABASE_URL") as conexao:
        if not registrar_inbox(conexao, FILA, evento.eventId):
            return
        campos = (entrega.retiradaId, entrega.unidadeId, entrega.itemId, entrega.quantidade)
        resultado = conexao.execute("""
            INSERT INTO entregas_observadas (reserva_id, retirada_id, unidade_id, item_id, quantidade,
                                             ocorrida_em, correlation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (reserva_id) DO NOTHING RETURNING retirada_id
        """, (entrega.reservaId, *campos, evento.occurredAt, evento.correlationId)).fetchone()
        if resultado is None:
            anterior = conexao.execute("""
                SELECT retirada_id, unidade_id, item_id, quantidade FROM entregas_observadas WHERE reserva_id = %s
            """, (entrega.reservaId,)).fetchone()
            if (anterior["retirada_id"], anterior["unidade_id"], anterior["item_id"], anterior["quantidade"]) != campos:
                raise ValueError(f"Evidência de entrega conflitante para a reserva {entrega.reservaId}.")
