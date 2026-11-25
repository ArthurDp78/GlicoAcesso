"""Os contratos gerados em execução devem documentar a borda publicada."""
import unittest

from servicos.bff_unidade.main import app as unidade
from servicos.gateway.main import app as gateway
from servicos.gateway.rotas import OPERACOES, UNIDADE


class OpenAPIRuntime(unittest.TestCase):
    def test_gateway_documenta_path_auth_idempotencia_e_503(self):
        schema = gateway.openapi()
        operation = schema["paths"]["/api/unidade/v1/reservas/{reservaId}/decisao"]["post"]
        parametros = {(p["in"], p["name"]) for p in operation["parameters"]}
        self.assertIn(("path", "reservaId"), parametros)
        self.assertIn(("header", "Idempotency-Key"), parametros)
        self.assertEqual(operation["security"], [{"bearerAuth": []}])
        self.assertIn("503", operation["responses"])
        self.assertEqual(schema["components"]["securitySchemes"]["bearerAuth"]["scheme"], "bearer")

    def test_bff_unidade_documenta_os_nove_corpos_aceitos(self):
        schema = unidade.openapi()
        operacoes = [
            ("/api/unidade/v1/unidade", "put"),
            ("/api/unidade/v1/unidade/horarios", "put"),
            ("/api/unidade/v1/unidade/prazo-analise", "put"),
            ("/api/unidade/v1/unidade/status", "patch"),
            ("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/permissao", "put"),
            ("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/entradas", "post"),
            ("/api/unidade/v1/painel/estoque/{unidadeId}/itens/{itemId}/ajustes", "post"),
            ("/api/unidade/v1/reservas/{reservaId}/cancelar", "post"),
            ("/api/unidade/v1/retiradas", "post"),
        ]
        for caminho, metodo in operacoes:
            with self.subTest(caminho=caminho, metodo=metodo):
                self.assertIn("requestBody", schema["paths"][caminho][metodo])

    def test_catalogo_de_estoque_publicado_no_bff_e_gateway(self):
        caminho = "/api/unidade/v1/painel/estoque/catalogo"
        operacao = unidade.openapi()["paths"][caminho]["get"]
        self.assertEqual(operacao["security"], [{"bearerAuth": []}])
        self.assertIn("200", operacao["responses"])
        self.assertIn(("GET", "/painel/estoque/catalogo"), OPERACOES[UNIDADE])
        self.assertIn(caminho, gateway.openapi()["paths"])
