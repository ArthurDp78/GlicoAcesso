"""A identidade do catálogo não deve depender da collation padrão do banco."""
import os
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.errors import UniqueViolation

from tests import ambiente as a


class NormalizacaoCatalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a.preparar()

    def test_capitalizacao_colide_mas_acentos_sao_preservados(self):
        prefixo = "Medicamento São José " + uuid4().hex
        primeiro, segundo, terceiro = uuid4(), uuid4(), uuid4()
        dsn = make_conninfo(os.environ["GLICO_TESTE_PG"], dbname="teste_estoque")
        with psycopg.connect(dsn) as conexao:
            conexao.execute("INSERT INTO itens (item_id,nome,tipo) VALUES (%s,%s,'INSUMO')",
                            (primeiro, prefixo + "ÁCIDO"))
            with self.assertRaises(UniqueViolation):
                with conexao.transaction():
                    conexao.execute("INSERT INTO itens (item_id,nome,tipo) VALUES (%s,%s,'INSUMO')",
                                    (segundo, prefixo.lower() + "ácido"))
            conexao.execute("INSERT INTO itens (item_id,nome,tipo) VALUES (%s,%s,'INSUMO')",
                            (terceiro, prefixo.lower() + " acido"))
        linhas = a.consultar("estoque", "SELECT count(*) AS n FROM itens WHERE item_id IN (%s,%s)",
                             str(primeiro), str(terceiro))
        self.assertEqual(linhas[0]["n"], 2)
