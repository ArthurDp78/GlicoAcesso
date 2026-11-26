import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg

from tests import ambiente as a


def setUpModule():
    a.preparar()


ENTRADA = {"nome": "UBS Nova", "logradouro": "Rua A", "numero": "1", "bairro": "B", "cidade": "C", "estado": "MG",
           "cep": "37200-000", "orientacoesRetirada": "Documento e receita.",
           "contatos": [{"tipo": "telefone", "valor": "35 0000"}],
           "horarios": [{"diaSemana": 1, "horarioInicial": "08:00:00", "horarioFinal": "12:00:00"}],
           "prazoAnaliseHoras": 48}
BASE = f"/internal/v1/unidades/{a.UNIDADE}"
INVALIDOS = {
    "invertido": [(1, "12:00", "08:00")],
    "atravessa a meia-noite": [(1, "22:00", "02:00")],
    "termina à meia-noite": [(1, "18:00", "00:00")],
    "duração nula": [(1, "08:00", "08:00")],
    "sobreposição parcial": [(1, "08:00", "12:00"), (1, "11:59:59", "14:00")],
    "contido": [(1, "08:00", "17:00"), (1, "09:00", "10:00")],
    "contido com mesmo início": [(1, "08:00", "12:00"), (1, "08:00", "17:00")],
    "sobreposição não adjacente": [(1, "08:00", "18:00"), (1, "09:00", "10:00"), (1, "11:00", "12:00")],
    "duplicado": [(1, "08:00", "12:00"), (1, "08:00:00", "12:00:00")],
}


def agenda(periodos):
    return {"horarios": [{"diaSemana": d, "horarioInicial": i, "horarioFinal": f} for d, i, f in periodos]}


def horarios_por(metodo, sufixo, corpo, chave=None):
    return a.chamar("unidades", metodo, BASE + sufixo, "profissional", chave or a.nova_chave(), json=corpo)


class Unidades(unittest.TestCase):
    def tearDown(self):
        a.consultar("unidades", "UPDATE unidades SET ativa = true, prazo_analise_horas = 24 WHERE unidade_id = %s", a.UNIDADE)

    def test_cadastro_idempotente_e_autorizado(self):
        chave = a.nova_chave()
        criar = lambda corpo=ENTRADA, token="admin", k=chave: a.chamar("unidades", "POST", "/internal/v1/unidades", token, k, json=corpo)
        with ThreadPoolExecutor(6) as pool:
            respostas = list(pool.map(lambda _: criar(), range(6)))
        self.assertEqual({r.status_code for r in respostas}, {201})
        self.assertEqual([r.json() for r in respostas], [respostas[0].json()] * 6)
        dados = respostas[0].json()
        self.assertTrue(dados["ativa"])
        self.assertEqual(dados["horarios"], ENTRADA["horarios"])
        self.assertEqual(dados["contatos"], ENTRADA["contatos"])
        self.assertEqual(criar({**ENTRADA, "nome": "Outra"}).status_code, 409)
        self.assertEqual(criar(token=None).status_code, 401)
        self.assertEqual(criar(token="invalido" * 8).status_code, 401)
        self.assertEqual(criar(token="profissional").status_code, 403)
        self.assertEqual(a.chamar("unidades", "POST", "/internal/v1/unidades", "admin", json=ENTRADA).status_code, 422)
        for ruim in ({"nome": "  "}, {"prazoAnaliseHoras": 0}, {"horarios": ENTRADA["horarios"] * 2},
                     {"horarios": [{"diaSemana": 8, "horarioInicial": "08:00", "horarioFinal": "09:00"}]}):
            self.assertEqual(criar({**ENTRADA, **ruim}, k=a.nova_chave()).status_code, 422, ruim)
        outra = f"/internal/v1/unidades/{dados['unidadeId']}"
        self.assertEqual(a.chamar("unidades", "PUT", outra, "profissional", a.nova_chave(), json=ENTRADA).status_code, 403)
        self.assertEqual(a.chamar("unidades", "GET", outra, "profissional").status_code, 403)
        self.assertEqual(a.chamar("unidades", "GET", outra, "reservas").json(), dados)

    def test_atualizacao_horarios_prazo_e_status(self):
        por = lambda metodo, sufixo, corpo, k=None: a.chamar("unidades", metodo, BASE + sufixo, "profissional", k or a.nova_chave(), json=corpo)
        original = a.chamar("unidades", "GET", BASE, "profissional").json()
        resposta = por("PUT", "", {**ENTRADA, "nome": "Unidade de Demonstração"})
        self.assertEqual((resposta.status_code, resposta.json()["prazoAnaliseHoras"]), (200, 48))
        novos = [{"diaSemana": 5, "horarioInicial": "13:00:00", "horarioFinal": "17:30:00"}]
        self.assertEqual(por("PUT", "/horarios", {"horarios": novos}).json()["horarios"], novos)
        self.assertEqual(a.chamar("unidades", "GET", BASE, "profissional").json()["horarioAtendimento"], "Sex 13:00–17:30")

        chave = a.nova_chave()
        self.assertEqual(por("PUT", "/prazo-analise", {"prazoAnaliseHoras": 72}, chave).status_code, 200)
        self.assertEqual(por("PUT", "/prazo-analise", {"prazoAnaliseHoras": 12}).status_code, 200)
        self.assertEqual(por("PUT", "/prazo-analise", {"prazoAnaliseHoras": 72}, chave).json()["prazoAnaliseHoras"], 72)
        prazo = lambda token="reservas": a.chamar("unidades", "GET", BASE + "/prazo-analise", token)
        self.assertEqual(prazo().json(), {"prazoAnaliseHoras": 12})  # O replay não reaplicou o efeito.
        self.assertEqual(prazo("profissional").status_code, 403)

        self.assertEqual(por("PATCH", "/status", {"ativa": False}).json()["ativa"], False)
        self.assertEqual(prazo().status_code, 404)
        publicas = a.chamar("unidades", "GET", "/api/cidadao/v1/unidades").json()
        self.assertNotIn(a.UNIDADE, [u["unidadeId"] for u in publicas])
        self.assertEqual(por("PATCH", "/status", {"ativa": "sim"}).status_code, 422)
        self.assertEqual(por("PATCH", "/status", {"ativa": True}).json()["unidadeId"], original["unidadeId"])

    def test_periodos_validos(self):
        for periodos in (
            [(1, "08:00", "12:00"), (1, "13:00", "17:00")],   # Independentes.
            [(1, "12:00", "17:00"), (1, "08:00", "12:00")],   # Consecutivos, fora de ordem.
            [(1, "08:00", "12:00"), (2, "08:00", "12:00")],   # Iguais em dias diferentes.
            [(7, "00:00", "23:59:59")], [],
        ):
            with self.subTest(periodos):
                resposta = horarios_por("PUT", "/horarios", agenda(periodos))
                self.assertEqual(resposta.status_code, 200, resposta.text)
                self.assertEqual(len(resposta.json()["horarios"]), len(periodos))

    def test_periodos_invalidos_preservam_os_dados(self):
        self.assertEqual(horarios_por("PUT", "/horarios", agenda([(3, "08:00", "12:00")])).status_code, 200)
        consultar = lambda: a.chamar("unidades", "GET", BASE, "profissional").json()
        total = lambda: a.consultar("unidades", "SELECT count(*) AS n FROM unidades")[0]["n"]
        antes, unidades = consultar(), total()
        for nome, periodos in INVALIDOS.items():
            # Um período válido acompanha os inválidos: nada do conjunto pode ser persistido.
            horarios = agenda([(6, "08:00", "09:00"), *periodos])
            cadastro = {**ENTRADA, **horarios, "nome": "Não deve persistir"}
            with self.subTest(nome):
                chave = a.nova_chave()
                self.assertEqual(horarios_por("PUT", "/horarios", horarios, chave).status_code, 422)
                self.assertEqual(horarios_por("PUT", "", cadastro).status_code, 422)
                self.assertEqual(a.chamar("unidades", "POST", "/internal/v1/unidades", "admin", a.nova_chave(), json=cadastro).status_code, 422)
                self.assertEqual((consultar(), total()), (antes, unidades))
                # A recusa não consome a chave: a requisição corrigida é aceita com ela.
                self.assertEqual(horarios_por("PUT", "/horarios", agenda([(3, "08:00", "12:00")]), chave).status_code, 200)

    def test_banco_protege_as_invariantes(self):
        self.assertEqual(horarios_por("PUT", "/horarios", agenda([(1, "08:00", "12:00")])).status_code, 200)
        inserir = lambda dia, inicio, fim: a.consultar(
            "unidades", "INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final) VALUES (%s, %s, %s, %s)",
            a.UNIDADE, dia, inicio, fim)
        for inicio, fim in (("12:00", "08:00"), ("14:00", "14:00"), ("20:00", "24:00")):
            with self.assertRaises(psycopg.errors.CheckViolation):
                inserir(1, inicio, fim)
        for inicio, fim in (("11:00", "13:00"), ("09:00", "10:00"), ("07:00", "13:00")):
            with self.assertRaises(psycopg.errors.ExclusionViolation):
                inserir(1, inicio, fim)
        inserir(1, "12:00", "17:00")
        inserir(2, "08:00", "12:00")

    def test_migracao_preserva_horarios_antigos_invalidos(self):
        dsn = psycopg.conninfo.make_conninfo(os.environ["GLICO_TESTE_PG"], dbname="teste_unidades_legado")
        with psycopg.connect(os.environ["GLICO_TESTE_PG"], autocommit=True) as conexao:
            conexao.execute("DROP DATABASE IF EXISTS teste_unidades_legado WITH (FORCE)")
            conexao.execute("CREATE DATABASE teste_unidades_legado")
        migracoes = sorted((a.RAIZ / "servicos/unidades/migrations").glob("*.sql"))
        inserir = ("INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final) VALUES (%s, %s, %s, %s)")
        with psycopg.connect(dsn) as conexao:
            for arquivo in migracoes[:2]:
                conexao.execute(arquivo.read_text(encoding="utf-8"))
            conexao.execute((a.RAIZ / "servicos/unidades/demo.sql").read_text(encoding="utf-8"))
            for periodo in ((6, "08:00", "12:00"), (6, "11:00", "13:00"), (6, "13:00", "15:00"), (7, "22:00", "02:00"), (7, "09:00", "09:00")):
                conexao.execute(inserir, (a.UNIDADE, *periodo))
            listar = lambda: conexao.execute("SELECT dia_semana, horario_inicial, horario_final FROM horarios_unidade ORDER BY 1, 2, 3").fetchall()
            antes = listar()
            conexao.execute(migracoes[2].read_text(encoding="utf-8"))
            # Reaplicar a demonstração, como faz o script local, continua inofensivo.
            conexao.execute((a.RAIZ / "servicos/unidades/demo.sql").read_text(encoding="utf-8"))
            self.assertEqual(listar(), antes)
            marcados = conexao.execute("SELECT dia_semana, horario_inicial::text FROM horarios_unidade WHERE legado ORDER BY 1, 2").fetchall()
            self.assertEqual(marcados, [(6, "08:00:00"), (6, "11:00:00"), (7, "09:00:00"), (7, "22:00:00")])
            # As regras valem para os novos registros mesmo havendo legado.
            with self.assertRaises(psycopg.errors.ExclusionViolation), conexao.transaction():
                conexao.execute(inserir, (a.UNIDADE, 1, "09:00", "10:00"))

    def test_unidade_inexistente(self):
        self.assertEqual(a.chamar("unidades", "GET", f"/internal/v1/unidades/{uuid4()}", "reservas").status_code, 404)
