from psycopg.types.json import Jsonb

from servicos.banco import conectar


def resultado_anterior(conexao, operacao: str, principal: str, chave: str, resumo: str, *,
                       resumo_legado: str | None = None):
    """Serializa a chave na transação e devolve o resultado gravado; 409 se o conteúdo divergir."""
    conexao.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{operacao}:{principal}:{chave}",))
    anterior = conexao.execute("""
        SELECT request_hash, http_status, resposta FROM idempotencia_comandos
        WHERE operacao = %s AND principal_id = %s AND chave = %s
    """, (operacao, principal, chave)).fetchone()
    if anterior is None:
        return None
    if anterior["request_hash"] not in (resumo, resumo_legado):
        return 409, {"codigo": "CHAVE_IDEMPOTENTE_CONFLITANTE", "mensagem": "Chave reutilizada com outro conteúdo."}
    return anterior["http_status"], anterior["resposta"]


def gravar_resultado(conexao, operacao: str, principal: str, chave: str, resumo: str, resultado):
    conexao.execute("""
        INSERT INTO idempotencia_comandos (operacao, principal_id, chave, request_hash, http_status, resposta)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (operacao, principal, chave, resumo, resultado[0], Jsonb(resultado[1])))
    return resultado


def reobter_resultado(variavel_dsn: str, operacao: str, principal: str, chave: str, resumo: str):
    """Consulta o resultado gravado antes de validações remotas, para que um retry não dependa delas."""
    with conectar(variavel_dsn) as conexao:
        return resultado_anterior(conexao, operacao, principal, chave, resumo)
