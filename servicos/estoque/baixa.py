"""Baixa física da retirada: consome a alocação em uma única transação local idempotente."""
import logging
from uuid import uuid4

from psycopg.types.json import Jsonb

from servicos.banco import conectar
from servicos.estoque.saldos import registrar_evento, variar_saldo
from servicos.mensageria import EventoRetirada, registrar_inbox


BANCO = "ESTOQUE_DATABASE_URL"
CONSUMIDOR = "baixa-retirada"
log = logging.getLogger("uvicorn.error")


class RetiradaDivergente(RuntimeError):
    """A alocação não corresponde à entrega: nenhuma baixa parcial ou arbitrária é feita."""


def baixar(evento: EventoRetirada) -> bool:
    """False = duplicata já processada."""
    dados = evento.payload
    with conectar(BANCO) as conexao:
        if not registrar_inbox(conexao, CONSUMIDOR, evento.eventId):
            return False
        alocacao = conexao.execute("""
            SELECT alocacao_id, unidade_id, item_id, quantidade, liberada_em, consumida_em
            FROM alocacoes WHERE reserva_id = %s FOR UPDATE
        """, (dados.reservaId,)).fetchone()
        if alocacao is None:
            raise RetiradaDivergente("ALOCACAO_INEXISTENTE")
        if alocacao["liberada_em"] is not None or alocacao["consumida_em"] is not None:
            raise RetiradaDivergente("ALOCACAO_ENCERRADA")
        if (alocacao["unidade_id"], alocacao["item_id"], alocacao["quantidade"]) != (
                dados.unidadeId, dados.itemId, dados.quantidade):
            raise RetiradaDivergente("DADOS_INCOMPATIVEIS")
        saldo = variar_saldo(conexao, dados.unidadeId, dados.itemId, -dados.quantidade, -dados.quantidade)
        conexao.execute("""
            INSERT INTO movimentacoes (movimentacao_id, unidade_id, item_id, variacao_fisica, ocorrida_em,
                alocacao_id, retirada_id, motivo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'RETIRADA')
        """, (uuid4(), dados.unidadeId, dados.itemId, -dados.quantidade, saldo["updated_at"],
              alocacao["alocacao_id"], dados.retiradaId))
        conexao.execute("UPDATE alocacoes SET consumida_em = now(), updated_at = now() WHERE alocacao_id = %s",
                        (alocacao["alocacao_id"],))
        registrar_evento(conexao, "estoque.retirada-baixada.v1", "AlocacaoEstoque", alocacao["alocacao_id"],
                         evento.correlationId, saldo, {
                             "retiradaId": str(dados.retiradaId), "reservaId": str(dados.reservaId),
                             "quantidadeBaixada": dados.quantidade}, evento.eventId)
        conexao.execute("UPDATE ocorrencias_retirada SET resolvida_em = now() WHERE event_id = %s", (evento.eventId,))
        return True


def registrar_ocorrencia(evento: EventoRetirada, motivo: str) -> None:
    with conectar(BANCO) as conexao:
        conexao.execute("""
            INSERT INTO ocorrencias_retirada (event_id, reserva_id, retirada_id, motivo, evento)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO UPDATE SET motivo = EXCLUDED.motivo, tentativas = ocorrencias_retirada.tentativas + 1
        """, (evento.eventId, evento.payload.reservaId, evento.payload.retiradaId, motivo,
              Jsonb(evento.model_dump(mode="json"))))


def processar_retirada(corpo: bytes) -> bool:
    evento = EventoRetirada.model_validate_json(corpo)
    try:
        return baixar(evento)
    except RetiradaDivergente as erro:
        # A transação da baixa foi desfeita (inclusive a Inbox): o evento segue para a fila de erros.
        registrar_ocorrencia(evento, str(erro))
        raise
