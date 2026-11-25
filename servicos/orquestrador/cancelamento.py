"""SAGA de cancelamento: ativação de pedidos, decisão das etapas e reconciliação da retirada."""
from psycopg.errors import UniqueViolation

from servicos.banco import conectar
from servicos.identidade_demo import cabecalhos_do_ator
from servicos.mensageria import EventoRetirada, registrar_inbox
from servicos.orquestrador.registro import (
    BANCO, criar_execucao, efeitos_conhecidos, mudar_estado, nova_etapa,
)


CONSUMIDOR = "reconciliacao-retirada"
INICIAR = "INICIAR_CANCELAMENTO"
ENTREGA = "ENTREGA_JA_REGISTRADA"


def intencao_de_inicio(conexao, saga_execucao, saga_cancelamento, reserva_id, ator_papel, ator_id, ator_unidade_id,
                       justificativa, etapa_id=INICIAR):
    """Grava a intenção de pedir a Reservas a transição, na execução que estiver ativa."""
    corpo = {"sagaId": str(saga_cancelamento)}
    if justificativa is not None:
        corpo["justificativa"] = justificativa
    nova_etapa(conexao, saga_execucao, etapa_id, "reservas", "POST",
               f"/internal/v1/reservas/{reserva_id}/iniciar-cancelamento", corpo,
               cabecalhos_do_ator(ator_papel, ator_id, ator_unidade_id), chave=f"{saga_cancelamento}:{INICIAR}")


def iniciar_execucao(conexao, saga_id, reserva_id, correlacao, ator_papel, ator_id, ator_unidade_id, justificativa):
    """Cancelamento sem confirmação ativa: a própria execução mantém a intenção de início."""
    criar_execucao(conexao, saga_id, reserva_id, correlacao, "CANCELAMENTO", "CANCELANDO", ator_papel, ator_id,
                   ator_unidade_id, {"efeitos": efeitos_conhecidos(conexao, reserva_id)})
    intencao_de_inicio(conexao, saga_id, saga_id, reserva_id, ator_papel, ator_id, ator_unidade_id, justificativa)


def pedido_pendente(conexao, reserva_id):
    return conexao.execute("""
        SELECT * FROM saga_pedidos_cancelamento WHERE reserva_id = %s AND fase = 'PENDENTE'
    """, (reserva_id,)).fetchone()


def definir_fase(conexao, pedido_id, fase, motivo=None):
    conexao.execute("""
        UPDATE saga_pedidos_cancelamento SET fase = %s, motivo_encerramento = %s, atualizado_em = now()
        WHERE saga_id_solicitado = %s
    """, (fase, motivo, pedido_id))


def interpor(conexao, saga_confirmacao, pedido) -> None:
    """Pausa a confirmação: todos os comandos emitidos já têm resultado e o próximo passo ainda não existe."""
    definir_fase(conexao, pedido["saga_id_solicitado"], "EM_TRANSICAO")
    intencao_de_inicio(conexao, saga_confirmacao, pedido["saga_id_solicitado"], pedido["reserva_id"],
                       pedido["ator_papel"], pedido["ator_id"], pedido["ator_unidade_id"], pedido["justificativa"],
                       etapa_id=f"{INICIAR}:{pedido['saga_id_solicitado']}")


def resolver_interposta(conexao, etapa, status: int, corpo: dict, retomar) -> bool:
    """Resultado da transição pedida dentro de uma confirmação ativa."""
    pedido_id = etapa["etapa_id"].split(":", 1)[1]
    codigo = corpo.get("codigo")
    if status == 200:
        pedido = conexao.execute("SELECT * FROM saga_pedidos_cancelamento WHERE saga_id_solicitado = %s",
                                 (pedido_id,)).fetchone()
        efeitos = efeitos_conhecidos(conexao, etapa["reserva_id"])
        # Troca atômica da execução ativa; a sucessora recebe os efeitos a reverter.
        mudar_estado(conexao, etapa["saga_id"], "INTERROMPIDA", "CANCELAMENTO_SOLICITADO", encerrar=True)
        criar_execucao(conexao, pedido_id, pedido["reserva_id"], pedido["correlation_id"], "CANCELAMENTO", "CANCELANDO",
                       pedido["ator_papel"], pedido["ator_id"], pedido["ator_unidade_id"], {"efeitos": efeitos})
        definir_fase(conexao, pedido_id, "ATIVADO")
        reverter(conexao, pedido_id, pedido["reserva_id"], efeitos)
        return True
    if status in (403, 404) or (status == 409 and codigo == "ESTADO_INCOMPATIVEL"):
        definir_fase(conexao, pedido_id, "RECUSADO", codigo or f"HTTP_{status}")
        retomar()
        return True
    return False


# --- Etapas da execução de cancelamento ---

def cancelar_autorizacao(conexao, saga, reserva):
    nova_etapa(conexao, saga, "CANCELAR_AUTORIZACAO", "retiradas", "POST",
               f"/internal/v1/autorizacoes/{reserva}/cancelar", None, {"X-Saga-Id": str(saga)})


def liberar_alocacao(conexao, saga, reserva):
    nova_etapa(conexao, saga, "LIBERAR_ALOCACAO", "estoque", "DELETE",
               f"/internal/v1/alocacoes/{reserva}", None, {"X-Saga-Id": str(saga)})


def finalizar(conexao, saga, reserva):
    nova_etapa(conexao, saga, "FINALIZAR_CANCELAMENTO", "reservas", "POST",
               f"/internal/v1/reservas/{reserva}/finalizar-cancelamento", {"sagaId": str(saga)})


def reverter(conexao, saga, reserva, efeitos: dict | None) -> None:
    """Primeira reversão aplicável. Sem registro dos efeitos, assume que a autorização pode existir."""
    if efeitos is None or efeitos["autorizacao"]:
        cancelar_autorizacao(conexao, saga, reserva)
    elif efeitos["alocacao"]:
        liberar_alocacao(conexao, saga, reserva)
    else:
        finalizar(conexao, saga, reserva)


def registrar_entrega(conexao, saga, retirada_id, event_id=None) -> None:
    """A entrega venceu: encerra sem liberar, preservando a alocação para a baixa física."""
    mudar_estado(conexao, saga, "INTERROMPIDA", ENTREGA, encerrar=True)
    conexao.execute("""
        UPDATE saga_execucoes SET retirada_id = COALESCE(retirada_id, %s), event_id = COALESCE(event_id, %s)
        WHERE saga_id = %s
    """, (retirada_id, event_id, saga))


def avancar_cancelamento(conexao, etapa, status: int, corpo: dict) -> bool:
    saga, reserva, codigo = etapa["saga_id"], etapa["reserva_id"], corpo.get("codigo")
    legado = (etapa.get("dados_execucao") or {}).get("cancelamento_main", False)
    match etapa["etapa_id"], status, codigo:
        case "INICIAR_CANCELAMENTO", 200, _ if legado:
            cancelar_autorizacao(conexao, saga, reserva)
        case "INICIAR_CANCELAMENTO", 200, _:
            reverter(conexao, saga, reserva, (etapa["dados_execucao"] or {}).get("efeitos"))
        case ("INICIAR_CANCELAMENTO", 403 | 404, _) | ("INICIAR_CANCELAMENTO", 409, "ESTADO_INCOMPATIVEL"):
            mudar_estado(conexao, saga, "INTERROMPIDA", codigo or f"HTTP_{status}", encerrar=True)
        case "CANCELAR_AUTORIZACAO" | "REVOGAR_PARA_CANCELAR", 200, _:
            liberar_alocacao(conexao, saga, reserva)
        case "CANCELAR_AUTORIZACAO" | "REVOGAR_PARA_CANCELAR", 404, "AUTORIZACAO_NAO_ENCONTRADA" if legado:
            liberar_alocacao(conexao, saga, reserva)
        case "CANCELAR_AUTORIZACAO" | "REVOGAR_PARA_CANCELAR", 409, "ENTREGA_JA_REGISTRADA":
            registrar_entrega(conexao, saga, corpo["retiradaId"])
        case "LIBERAR_ALOCACAO" | "LIBERAR_PARA_CANCELAR", 204, _:
            finalizar(conexao, saga, reserva)
        case "FINALIZAR_CANCELAMENTO", 200, _:
            mudar_estado(conexao, saga, "CANCELADA", encerrar=True)
        case "FINALIZAR_CANCELAMENTO", 409, "ESTADO_INCOMPATIVEL" if legado and corpo.get("status") == "RETIRADA":
            mudar_estado(conexao, saga, "INTERROMPIDA", ENTREGA, encerrar=True)
        case _:
            # Inclui 404 na revogação: só se chega a ela quando a autorização existiu ou é desconhecida.
            return False
    return True


def ativar_pedido() -> bool:
    """Inicia o cancelamento de um pedido cuja confirmação já terminou (concluída ou compensada)."""
    with conectar(BANCO) as conexao:
        pedido = conexao.execute("""
            SELECT p.* FROM saga_pedidos_cancelamento p JOIN saga_execucoes s ON s.saga_id = p.saga_confirmacao_id
            WHERE p.fase = 'PENDENTE' AND s.encerrada_em IS NOT NULL
            ORDER BY p.atualizado_em LIMIT 1
            FOR UPDATE OF p SKIP LOCKED
        """).fetchone()
        if pedido is None:
            return False
        try:
            with conexao.transaction():
                iniciar_execucao(conexao, pedido["saga_id_solicitado"], pedido["reserva_id"], pedido["correlation_id"],
                                 pedido["ator_papel"], pedido["ator_id"], pedido["ator_unidade_id"], pedido["justificativa"])
        except UniqueViolation:
            # Há outra execução ativa: o pedido volta ao fim da fila e aguarda.
            conexao.execute("UPDATE saga_pedidos_cancelamento SET atualizado_em = now() WHERE saga_id_solicitado = %s",
                            (pedido["saga_id_solicitado"],))
            return False
        definir_fase(conexao, pedido["saga_id_solicitado"], "ATIVADO")
        return True


def processar_retirada(corpo: bytes) -> bool:
    """False = duplicata. Encerra o cancelamento ativo com a evidência da entrega, junto da Inbox."""
    evento = EventoRetirada.model_validate_json(corpo)
    with conectar(BANCO) as conexao:
        if not registrar_inbox(conexao, CONSUMIDOR, evento.eventId):
            return False
        execucao = conexao.execute("""
            SELECT saga_id FROM saga_execucoes
            WHERE reserva_id = %s AND tipo = 'CANCELAMENTO' AND encerrada_em IS NULL
            FOR NO KEY UPDATE
        """, (evento.payload.reservaId,)).fetchone()
        if execucao is not None:
            registrar_entrega(conexao, execucao["saga_id"], evento.payload.retiradaId, evento.eventId)
            conexao.execute("""
                UPDATE saga_etapas SET estado_tecnico = 'FALHOU', proximo_retry_em = NULL, erro_tecnico = %s,
                    atualizada_em = now()
                WHERE saga_id = %s AND estado_tecnico = 'PENDENTE'
            """, (ENTREGA, execucao["saga_id"]))
        return True
