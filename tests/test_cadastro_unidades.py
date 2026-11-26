import unittest

from pydantic import ValidationError

from servicos.unidades.esquemas import UnidadeInput


class TestDadosCadastroUnidades(unittest.TestCase):
    def setUp(self):
        self.dados = {
            "nome": "Unidade de Teste",
            "logradouro": "Rua Exemplo",
            "numero": "100",
            "bairro": "Centro",
            "cidade": "Cidade Exemplo",
            "estado": "MG",
            "cep": "30000200",
            "orientacoesRetirada": "Apresente a confirmação.",
            "prazoAnaliseHoras": 24,
            "contatos": [
                {"tipo": "telefone", "valor": "3000-0000"},
                {"tipo": "email", "valor": "unidade@example.org"},
            ],
            "horarios": [{"diaSemana": 1, "horarioInicial": "08:00", "horarioFinal": "17:00"}],
        }

    def test_payload_equivalente_tem_representacao_canonica_identica(self):
        original = UnidadeInput.model_validate(self.dados)
        repeticao = UnidadeInput.model_validate({
            **self.dados,
            "nome": " Unidade de Teste ",
            "cep": "30000-200",
            "contatos": self.dados["contatos"][::-1],
        })
        self.assertEqual(original.model_dump_json(), repeticao.model_dump_json())

    def test_rejeita_intervalo_invertido_antes_da_persistencia(self):
        with self.assertRaises(ValidationError):
            UnidadeInput.model_validate({
                **self.dados, "horarios": [{"diaSemana": 1, "horarioInicial": "17:00", "horarioFinal": "08:00"}],
            })

    def test_rejeita_contatos_e_horarios_repetidos(self):
        for campo in ("contatos", "horarios"):
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                UnidadeInput.model_validate({**self.dados, campo: self.dados[campo] * 2})
