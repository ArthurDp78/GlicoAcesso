"""Persistência do saldo canônico e registro do evento com o estado resultante."""
from uuid import UUID

from servicos.mensageria import gravar_outbox


CAMPOS_SALDO = """
    unidade_id, item_id, estoque_fisico_atual, quantidade_alocada, permite_reserva, estoque_version, updated_at
"""


def registrar_evento(conexao, tipo: str, agregado_tipo: str, agregado_id, correlacao: UUID | None, saldo, extra: dict,
                     causacao: UUID | None = None):
    """Grava o fato na Outbox, na transação que alterou o saldo, com o estado resultante completo."""
    gravar_outbox(conexao, tipo, agregado_tipo, agregado_id, correlacao, saldo["updated_at"], {
        "unidadeId": str(saldo["unidade_id"]), "itemId": str(saldo["item_id"]),
        "estoqueVersion": saldo["estoque_version"], "estoqueFisicoAtual": saldo["estoque_fisico_atual"],
        "quantidadeAlocada": saldo["quantidade_alocada"], "permiteReserva": saldo["permite_reserva"], **extra,
    }, causacao)


def travar_saldo(conexao, unidade_id: UUID, item_id: UUID):
    return conexao.execute(f"""
        SELECT {CAMPOS_SALDO} FROM saldos WHERE unidade_id = %s AND item_id = %s FOR UPDATE
    """, (unidade_id, item_id)).fetchone()


def variar_saldo(conexao, unidade_id: UUID, item_id: UUID, fisico: int = 0, alocado: int = 0):
    """Aplica variações ao saldo e incrementa a versão; as constraints protegem as invariantes.

    O instante é o da alteração, com a linha travada: acompanha a ordem de estoque_version.
    """
    return conexao.execute(f"""
        UPDATE saldos SET estoque_fisico_atual = estoque_fisico_atual + %s,
            quantidade_alocada = quantidade_alocada + %s,
            estoque_version = estoque_version + 1, updated_at = clock_timestamp()
        WHERE unidade_id = %s AND item_id = %s
        RETURNING {CAMPOS_SALDO}
    """, (fisico, alocado, unidade_id, item_id)).fetchone()
