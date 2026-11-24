import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


class BancoIndisponivel(RuntimeError):
    """O serviço está sem configuração de banco ou perdeu a conexão."""


@contextmanager
def conectar(variavel_dsn: str):
    dsn = os.getenv(variavel_dsn)
    if not dsn:
        raise BancoIndisponivel(f"Configure {variavel_dsn} para acessar o banco.")

    try:
        with psycopg.connect(
            dsn, connect_timeout=3, options="-c timezone=UTC", row_factory=dict_row
        ) as conexao:
            yield conexao
    except psycopg.OperationalError as erro:
        raise BancoIndisponivel("Banco de dados temporariamente indisponível.") from erro
