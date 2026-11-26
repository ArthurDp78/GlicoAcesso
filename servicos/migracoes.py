import argparse
from pathlib import Path

from servicos.banco import BancoIndisponivel, conectar


SERVICOS = {
    "unidades": "UNIDADES_DATABASE_URL",
    "estoque": "ESTOQUE_DATABASE_URL",
    "reservas": "RESERVAS_DATABASE_URL",
    "orquestrador": "ORQUESTRADOR_DATABASE_URL",
    "retiradas": "RETIRADAS_DATABASE_URL",
}
# Perfil opcional com pgvector: migra pelo mesmo comando, fora dos bancos do domínio.
BANCOS = SERVICOS | {"orientacao": "ORIENTACAO_DATABASE_URL"}


# As duas linhas criaram parte do esquema sob nomes diferentes. Para um banco da main,
# o SQL de adaptação executa no lugar da criação original, dentro da mesma transação.
MIGRACOES_MAIN = {
    "004_movimentacoes.sql": "005_movimentacoes_estoque.sql",
    "002_cancelamento.sql": "003_eventos_retirada.sql",
    "003_cancelamento_retirada.sql": "003_eventos_retirada.sql",
    "002_entregas.sql": "002_entregas_outbox.sql",
    "002_idempotencia.sql": "002_cadastro_administrativo.sql",
}


def migrar(servico: str, carregar_demo: bool) -> None:
    pasta_servico = Path(__file__).resolve().parent / servico
    migracoes = sorted((pasta_servico / "migrations").glob("*.sql"))
    if not migracoes:
        raise RuntimeError(f"Nenhuma migração encontrada para {servico}.")

    with conectar(BANCOS[servico]) as conexao:
        conexao.execute("SELECT pg_advisory_xact_lock(6122026)")
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS migracoes (
                nome text PRIMARY KEY,
                aplicada_em timestamptz NOT NULL DEFAULT now()
            )
        """)
        aplicadas = {linha["nome"] for linha in conexao.execute("SELECT nome FROM migracoes")}
        for arquivo in migracoes:
            if arquivo.name not in aplicadas:
                origem_main = MIGRACOES_MAIN.get(arquivo.name)
                sql = arquivo.parent / "main" / arquivo.name if origem_main in aplicadas else arquivo
                conexao.execute(sql.read_text(encoding="utf-8"))
                conexao.execute("INSERT INTO migracoes (nome) VALUES (%s)", (arquivo.name,))
        demo = pasta_servico / "demo.sql"
        if carregar_demo and demo.is_file():
            conexao.execute(demo.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica as migrações do banco de um serviço.")
    parser.add_argument("servico", choices=BANCOS)
    parser.add_argument("--demo", action="store_true", help="Inclui os dados iniciais de demonstração.")
    args = parser.parse_args()
    try:
        migrar(args.servico, args.demo)
    except BancoIndisponivel as erro:
        parser.exit(1, f"{erro}\n")
    print(f"Migrações concluídas: {args.servico}.")


if __name__ == "__main__":
    main()
