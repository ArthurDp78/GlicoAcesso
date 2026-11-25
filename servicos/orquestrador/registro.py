"""Persistência das execuções e das intenções de comando da SAGA."""
from psycopg.types.json import Jsonb


BANCO = "ORQUESTRADOR_DATABASE_URL"


def nova_etapa(conexao, saga_id, etapa_id, destino, metodo, caminho, corpo=None, cabecalhos=None, chave=None):
    comando = {"metodo": metodo, "caminho": caminho, "corpo": corpo, "cabecalhos": cabecalhos or {}}
    conexao.execute("""
        INSERT INTO saga_etapas (saga_id, etapa_id, operacao, destino, idempotency_key, estado_tecnico,
            dados_comando, proximo_retry_em, criada_em, atualizada_em)
        VALUES (%s, %s, %s, %s, %s, 'PENDENTE', %s, now(), now(), now())
    """, (saga_id, etapa_id, etapa_id.split(":")[0], destino, chave or f"{saga_id}:{etapa_id}", Jsonb(comando)))
    conexao.execute("""
        UPDATE saga_execucoes SET etapa_atual = %s, versao = versao + 1, atualizada_em = now() WHERE saga_id = %s
    """, (etapa_id, saga_id))


def mudar_estado(conexao, saga_id, estado, motivo=None, encerrar=False):
    conexao.execute("""
        UPDATE saga_execucoes SET estado = %s, motivo_encerramento = COALESCE(%s, motivo_encerramento),
            etapa_atual = CASE WHEN %s THEN NULL ELSE etapa_atual END,
            encerrada_em = CASE WHEN %s THEN now() ELSE encerrada_em END,
            versao = versao + 1, atualizada_em = now()
        WHERE saga_id = %s
    """, (estado, motivo, encerrar, encerrar, saga_id))


def criar_execucao(conexao, saga_id, reserva_id, correlacao, tipo, estado, ator_papel, ator_id, ator_unidade_id,
                   resultado=None):
    conexao.execute("""
        INSERT INTO saga_execucoes (saga_id, reserva_id, correlation_id, tipo, estado, ator_papel, ator_id,
            ator_unidade_id, resultado, criada_em, atualizada_em)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
    """, (saga_id, reserva_id, correlacao, tipo, estado, ator_papel, ator_id, ator_unidade_id,
          Jsonb(resultado) if resultado is not None else None))


def cabecalhos_do_ator(papel, ator_id, unidade_id) -> dict:
    cabecalhos = {"X-Ator-Papel": papel, "X-Ator-Id": ator_id}
    if unidade_id is not None:
        cabecalhos["X-Ator-Unidade-Id"] = str(unidade_id)
    return cabecalhos


def efeitos_conhecidos(conexao, reserva_id) -> dict | None:
    """Efeitos das confirmações, já reconciliados por resultados conclusivos; None sem registro."""
    linhas = conexao.execute("""
        SELECT e.etapa_id, (e.resultado->>'status')::int AS status
        FROM saga_etapas e JOIN saga_execucoes s USING (saga_id)
        WHERE s.reserva_id = %s AND s.tipo = 'CONFIRMACAO' AND e.estado_tecnico = 'CONCLUIDA'
    """, (reserva_id,)).fetchall()
    if not linhas:
        return None
    criados = {linha["etapa_id"] for linha in linhas if linha["status"] == 201}
    return {"alocacao": "ALOCAR_ESTOQUE" in criados, "autorizacao": "PREPARAR_AUTORIZACAO" in criados}


def concluir_etapa(conexao, saga_id, etapa_id, status: int, corpo: dict) -> None:
    conexao.execute("""
        UPDATE saga_etapas SET estado_tecnico = %s, resultado = %s, tentativas = tentativas + 1,
            ultima_tentativa_em = now(), proximo_retry_em = NULL, erro_tecnico = NULL, atualizada_em = now()
        WHERE saga_id = %s AND etapa_id = %s
    """, ("CONCLUIDA" if status < 300 else "FALHOU", Jsonb({"status": status, "corpo": corpo}), saga_id, etapa_id))
