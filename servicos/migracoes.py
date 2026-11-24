import argparse
from pathlib import Path

from servicos.banco import BancoIndisponivel, conectar


SERVICOS = {
    "unidades": "UNIDADES_DATABASE_URL",
    "estoque": "ESTOQUE_DATABASE_URL",
}


def migrar(servico: str, carregar_demo: bool) -> None:
    pasta_servico = Path(__file__).resolve().parent / servico
    migracoes = sorted((pasta_servico / "migrations").glob("*.sql"))
    if not migracoes:
        raise RuntimeError(f"Nenhuma migração encontrada para {servico}.")

    with conectar(SERVICOS[servico]) as conexao:
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
                conexao.execute(arquivo.read_text(encoding="utf-8"))
                conexao.execute("INSERT INTO migracoes (nome) VALUES (%s)", (arquivo.name,))
        if carregar_demo:
            conexao.execute((pasta_servico / "demo.sql").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica as migrações do banco de um serviço.")
    parser.add_argument("servico", choices=SERVICOS)
    parser.add_argument("--demo", action="store_true", help="Inclui os dados iniciais de demonstração.")
    args = parser.parse_args()
    try:
        migrar(args.servico, args.demo)
    except BancoIndisponivel as erro:
        parser.exit(1, f"{erro}\n")
    print(f"Migrações concluídas: {args.servico}.")


if __name__ == "__main__":
    main()
