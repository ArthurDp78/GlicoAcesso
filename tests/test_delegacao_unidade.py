import os
import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from servicos.delegacao_unidade import VALIDADE_SEGUNDOS, emitir_credencial, profissional_delegado
from servicos.identidade_demo import Ator


class TestDelegacaoUnidade(unittest.TestCase):
    def setUp(self):
        self.ator = Ator("PROFISSIONAL", "profissional-demo", UUID("10000000-0000-4000-8000-000000000001"))
        self.chave = "chave-de-teste-exclusiva-da-delegacao"
        self.enterContext(patch.dict(os.environ, {"GLICO_BFF_UNIDADE_SIGNING_KEY": self.chave}))
        self.relogio = self.enterContext(patch("servicos.delegacao_unidade.time", return_value=1000))

    def validar(self, token):
        return profissional_delegado(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    def rejeitar(self, token, status):
        with self.assertRaises(HTTPException) as erro:
            self.validar(token)
        self.assertEqual(erro.exception.status_code, status)

    def test_credencial_recupera_identidade_delegada(self):
        self.assertEqual(self.validar(emitir_credencial(self.ator)), self.ator)

    def test_credenciais_diretas_nao_sao_aceitas(self):
        self.rejeitar("token-direto-do-profissional", 401)
        self.rejeitar(self.chave, 401)

    def test_papel_cidadao_nao_pode_ser_delegado(self):
        with self.assertRaises(HTTPException) as erro:
            emitir_credencial(Ator("CIDADAO", "cidadao-demo"))
        self.assertEqual(erro.exception.status_code, 403)

    def test_conteudo_alterado_e_rejeitado(self):
        token = emitir_credencial(self.ator)
        primeiro_caractere = "A" if token[0] != "A" else "B"
        self.rejeitar(primeiro_caractere + token[1:], 401)

    def test_credencial_expira(self):
        token = emitir_credencial(self.ator)
        self.relogio.return_value += VALIDADE_SEGUNDOS
        self.rejeitar(token, 401)

    def test_chave_ausente_e_diagnostico_de_configuracao(self):
        token = emitir_credencial(self.ator)
        with patch.dict(os.environ, {"GLICO_BFF_UNIDADE_SIGNING_KEY": ""}):
            self.rejeitar(token, 503)


if __name__ == "__main__":
    unittest.main()
