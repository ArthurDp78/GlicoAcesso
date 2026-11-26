"""Classificação de 404 de recurso versus 404 de rota na comunicação interna."""
import unittest

import httpx

from servicos.http import falha_de_configuracao


class Classificacao404(unittest.TestCase):
    def response(self, status, body):
        return httpx.Response(status, json=body, request=httpx.Request("GET", "http://estoque.local/x"))

    def test_404_rota_inexistente_e_falha_de_integracao(self):
        resposta = self.response(404, {"detail": "Not Found"})
        self.assertTrue(falha_de_configuracao(resposta))

    def test_404_de_projecao_ausente_e_resposta_de_dominio(self):
        resposta = self.response(404, {"detail": "Disponibilidade não encontrada."})
        self.assertFalse(falha_de_configuracao(resposta))

    def test_403_de_credencial_de_servico_e_falha_de_integracao(self):
        resposta = self.response(403, {"detail": {"codigo": "CHAMADOR_NAO_AUTORIZADO"}})
        self.assertTrue(falha_de_configuracao(resposta))
