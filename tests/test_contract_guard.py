"""O verificador de contratos deve fornecer sinal de falha utilizável pelo CI."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class GuardiaoDeContrato(unittest.TestCase):
    def test_troca_de_sucesso_fora_do_contrato_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            trocas = Path(pasta) / "trocas.jsonl"
            trocas.write_text(
                '{"servico":"gateway","metodo":"GET","caminho":"/rota-inexistente",'
                '"status":200,"entrada":"","saida":"{}","cabecalhos":{},"chave":false}\n',
                encoding="utf-8",
            )
            resultado = subprocess.run(
                [sys.executable, "-m", "tests.contratos", str(trocas)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            )
            self.assertNotEqual(resultado.returncode, 0, resultado.stdout)
            self.assertIn("fora do contrato", resultado.stdout)

    def test_arquivo_vazio_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            trocas = Path(pasta) / "trocas.jsonl"
            trocas.write_text("", encoding="utf-8")
            resultado = subprocess.run(
                [sys.executable, "-m", "tests.contratos", str(trocas)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            )
            self.assertNotEqual(resultado.returncode, 0)
            self.assertIn("Nenhuma troca HTTP", resultado.stdout)
