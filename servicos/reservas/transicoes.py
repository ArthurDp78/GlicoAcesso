"""Gravação de uma transição de estado com sua auditoria, na transação do chamador."""
from uuid import UUID, uuid4


def transicionar(conexao, reserva_id: UUID, origem: str, destino: str, *, ator_id: str | None = None,
                 justificativa: str | None = None, motivo: str | None = None, saga_id: UUID | None = None,
                 event_id: UUID | None = None, retirada_id: UUID | None = None) -> None:
    alterada = conexao.execute("""
        UPDATE reservas SET status = %s, atualizada_em = now() WHERE reserva_id = %s AND status = %s
        RETURNING reserva_id
    """, (destino, reserva_id, origem)).fetchone()
    if alterada is None:
        raise RuntimeError(f"Transição de {origem} para {destino} perdeu a corrida.")
    conexao.execute("""
        INSERT INTO historico_reserva (historico_id, reserva_id, status_anterior, status_posterior, ocorrido_em,
            ator_id, justificativa, motivo, saga_id, event_id, retirada_id)
        VALUES (%s, %s, %s, %s, now(), %s, %s, %s, %s, %s, %s)
    """, (uuid4(), reserva_id, origem, destino, ator_id, justificativa, motivo, saga_id, event_id, retirada_id))
