import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from servicos.unidades.cli import main


class TestCliUnidades(unittest.TestCase):
    def setUp(self):
        pasta = self.enterContext(TemporaryDirectory())
        self.arquivo = Path(pasta) / "unidade.json"
        self.dados = {"nome": "Unidade São José"}
        self.arquivo.write_text(json.dumps(self.dados, ensure_ascii=False), encoding="utf-8-sig")
        self.token = "credencial-exclusiva-para-o-teste-local"
        self.enterContext(patch.dict(os.environ, {
            "UNIDADES_URL": "http://unidades:8002",
            "GLICO_ADMIN_SERVICE_TOKEN": self.token,
        }))
        self.saida = self.enterContext(redirect_stdout(io.StringIO()))
        self.erro = self.enterContext(redirect_stderr(io.StringIO()))
        self.post = self.enterContext(patch("servicos.unidades.cli.httpx.post"))

    def executar(self):
        return main(["--arquivo", str(self.arquivo), "--chave", "chave-estavel"])

    def test_envia_cadastro_e_imprime_apenas_o_id(self):
        unidade_id = "10000000-0000-4000-8000-000000000002"
        self.post.return_value = httpx.Response(201, json={"unidadeId": unidade_id})
        self.assertEqual(self.executar(), 0)
        self.assertEqual(self.saida.getvalue(), unidade_id + "\n")
        self.assertEqual(self.erro.getvalue(), "")
        self.post.assert_called_once_with(
            "http://unidades:8002/internal/v1/unidades",
            headers={"Authorization": f"Bearer {self.token}", "Idempotency-Key": "chave-estavel"},
            json=self.dados, timeout=5.0, trust_env=False,
        )

    def test_mostra_conflito_sem_escrever_na_saida_padrao(self):
        self.post.return_value = httpx.Response(409, json={
            "codigo": "CADASTRO_DUPLICADO", "mensagem": "A unidade já existe.",
        })
        self.assertEqual(self.executar(), 1)
        self.assertIn("CADASTRO_DUPLICADO", self.erro.getvalue())
        self.assertEqual(self.saida.getvalue(), "")

    def test_timeout_orienta_repetir_a_mesma_chave(self):
        self.post.side_effect = httpx.ReadTimeout("Simulação de resposta perdida")
        self.assertEqual(self.executar(), 1)
        self.assertIn("mesma chave", self.erro.getvalue())
        self.assertEqual(self.saida.getvalue(), "")
