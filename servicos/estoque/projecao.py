"""Reconstrução da projeção de disponibilidade a partir do saldo canônico.

uv run --locked python -m servicos.estoque.projecao

Pode ser executada com o serviço no ar. A trava espera os eventos em aplicação e pausa o consumidor até o commit;
as consultas continuam lendo o estado anterior. A Inbox é preservada: eventos pendentes com versão já refletida são
ignorados, e alterações posteriores à leitura chegam pela Outbox com versão maior.
"""
import argparse

from servicos.banco import BancoIndisponivel, conectar


BANCO = "ESTOQUE_DATABASE_URL"


def reconstruir() -> tuple[int, int]:
    """Devolve (linhas recriadas, linhas sem saldo removidas)."""
    with conectar(BANCO) as conexao:
        conexao.execute("SET LOCAL lock_timeout = '30s'")
        conexao.execute("LOCK TABLE disponibilidade IN SHARE ROW EXCLUSIVE MODE")
        # Cada comando lê um retrato posterior à trava, portanto nunca anterior ao que a projeção já aplicou.
        removidas = conexao.execute("""
            DELETE FROM disponibilidade d WHERE NOT EXISTS (
                SELECT 1 FROM saldos s WHERE s.unidade_id = d.unidade_id AND s.item_id = d.item_id)
        """).rowcount
        recriadas = conexao.execute("""
            INSERT INTO disponibilidade (unidade_id, item_id, estoque_fisico_atual, quantidade_alocada,
                permite_reserva, atualizado_em, estoque_version)
            SELECT unidade_id, item_id, estoque_fisico_atual, quantidade_alocada, permite_reserva, updated_at, estoque_version
            FROM saldos
            ON CONFLICT (unidade_id, item_id) DO UPDATE SET
                estoque_fisico_atual = EXCLUDED.estoque_fisico_atual,
                quantidade_alocada = EXCLUDED.quantidade_alocada,
                permite_reserva = EXCLUDED.permite_reserva,
                atualizado_em = EXCLUDED.atualizado_em,
                estoque_version = EXCLUDED.estoque_version
        """).rowcount
        return recriadas, removidas


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstrói a projeção de disponibilidade a partir dos saldos.")
    parser.parse_args()
    try:
        recriadas, removidas = reconstruir()
    except BancoIndisponivel as erro:
        parser.exit(1, f"{erro}\n")
    print(f"Projeção reconstruída: {recriadas} linhas; {removidas} sem saldo removidas.")


if __name__ == "__main__":
    main()
