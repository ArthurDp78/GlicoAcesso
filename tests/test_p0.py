"""Regressões do escopo da idempotência e da configuração do Compose."""
import os
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from servicos.migracoes import MIGRACOES_MAIN, SERVICOS, migrar
from tests import ambiente as a


class ConfiguracaoCompose(unittest.TestCase):
    def test_gera_valores_distintos_sem_expor_ou_substituir_credenciais(self):
        with TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / ".env"
            comando = [sys.executable, str(a.RAIZ / "scripts/configurar-compose.py"), "--arquivo", str(arquivo)]
            ambiente = {k: v for k, v in os.environ.items()
                        if not k.startswith(("GLICO_", "POSTGRES_", "RABBITMQ_"))}
            executar = lambda *args: subprocess.run(comando + list(args), capture_output=True, env=ambiente)
            primeira = executar()
            self.assertEqual((primeira.returncode, primeira.stdout, primeira.stderr), (0, b"", b""))
            inicial = arquivo.read_text()
            self.assertEqual(executar().returncode, 0)
            self.assertEqual(arquivo.read_text(), inicial)
            valores = dict(linha.split("=", 1) for linha in inicial.splitlines() if "=" in linha)
            valores["GLICO_BFF_CIDADAO_TOKEN"] = valores["GLICO_BFF_UNIDADE_TOKEN"]
            arquivo.write_text("\n".join(f"{k}={v}" for k, v in valores.items()))
            rejeitado = executar("--verificar")
            self.assertEqual(rejeitado.returncode, 1)
            self.assertNotIn(valores["GLICO_BFF_UNIDADE_TOKEN"].encode(), rejeitado.stderr)


class MigracaoMain(unittest.TestCase):
    # Snapshot atual de origin/main ao preparar esta suíte de regressão.
    MAIN_AUDITADA = "973cbb4e1c4149c8151715bda0512aa378ace977"

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=a.RAIZ, text=True, encoding="utf-8")

    def test_adapta_os_cinco_esquemas_e_preserva_a_entrega_legada(self):
        ambiente = os.environ.get("GLICO_TESTE_PG")
        if not ambiente:
            self.skipTest("Defina GLICO_TESTE_PG para o PostgreSQL descartável.")
        for servico, variavel in SERVICOS.items():
            with self.subTest(servico=servico), psycopg.connect(ambiente, autocommit=True) as admin:
                nome = f"teste_main_{uuid4().hex}"
                banco = sql.Identifier(nome)
                admin.execute(sql.SQL("CREATE DATABASE {}").format(banco))
                try:
                    dsn = make_conninfo(ambiente, dbname=nome)
                    prefixo = f"servicos/{servico}/migrations"
                    legado = self.MAIN_AUDITADA
                    arquivos = self.git("ls-tree", "-r", "--name-only", legado, prefixo).splitlines()
                    self.assertTrue(arquivos)
                    retirada, autorizacao, correlacao, evento = (uuid4() for _ in range(4))
                    with psycopg.connect(dsn) as conexao:
                        conexao.execute("CREATE TABLE migracoes (nome text PRIMARY KEY, aplicada_em timestamptz DEFAULT now())")
                        for arquivo in sorted(arquivos):
                            conexao.execute(self.git("show", f"{legado}:{arquivo}"))
                            conexao.execute("INSERT INTO migracoes(nome) VALUES (%s)", (Path(arquivo).name,))
                        if servico == "retiradas":
                            conexao.execute("""
                                INSERT INTO autorizacoes (autorizacao_id, reserva_id, saga_id, unidade_id, item_id,
                                    quantidade, idempotency_key) VALUES (%s, %s, %s, %s, %s, 1, 'teste')
                            """, (autorizacao, uuid4(), uuid4(), uuid4(), uuid4()))
                            conexao.execute("""
                                INSERT INTO entregas (retirada_id, autorizacao_id, profissional_id)
                                VALUES (%s, %s, 'profissional-demo')
                            """, (retirada, autorizacao))
                            conexao.execute("""
                                INSERT INTO outbox (event_id, event_type, event_version, aggregate_type,
                                    aggregate_id, correlation_id, occurred_at, payload)
                                VALUES (%s, 'retirada.concluida.v1', 1, 'Retirada', %s, %s, now(), '{}')
                            """, (evento, str(retirada), correlacao))
                    with patch.dict(os.environ, {variavel: dsn}):
                        migrar(servico, False)
                        migrar(servico, False)
                    with psycopg.connect(dsn) as conexao:
                        esperadas = {Path(c).name for c in arquivos} | {
                            c.name for c in (a.RAIZ / prefixo).glob("*.sql")}
                        aplicadas = {r[0] for r in conexao.execute("SELECT nome FROM migracoes")}
                        self.assertEqual(aplicadas, esperadas)
                        self.assertTrue(set(MIGRACOES_MAIN) & (aplicadas - {Path(c).name for c in arquivos}))
                        if servico == "estoque":
                            catalogo = {str(r[0]) for r in conexao.execute(
                                "SELECT item_id FROM itens WHERE item_id = ANY(%s)",
                                ([UUID(valor) for valor in [
                                    "31a8296a-87a9-58ef-b8fc-a2248dab22b3",
                                    "6eab6077-2ace-5313-bfd4-2597ab7fa680",
                                    "25057d00-8d2c-5ad0-87a8-b3f6f294493d",
                                    "06fa44c3-af81-5ff8-9749-76f2d46938e4",
                                    "84218dfb-8903-5ed8-96e5-64f6de33272b",
                                    "dde341d5-ea06-5dbe-bc38-44025b734ceb",
                                ]],)
                            )}
                            self.assertEqual(len(catalogo), 6)
                        if servico == "retiradas":
                            preservada = conexao.execute("""
                                SELECT retirada_id, autorizacao_id, ator_id, correlation_id FROM retiradas
                            """).fetchone()
                            self.assertEqual(preservada, (retirada, autorizacao, "profissional-demo", correlacao))
                            self.assertEqual(conexao.execute("SELECT event_id FROM outbox").fetchone(), (evento,))
                finally:
                    admin.execute(sql.SQL("DROP DATABASE {}").format(banco))


class RepeticaoAutorizada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        a.preparar()

    def tearDown(self):
        for proxy in a.proxies.values():
            proxy.limpar()

    def comparar(self, servico, caminho, corpo, status, chave=None, ator=None):
        chave = chave or a.nova_chave()
        ator = ator or {}
        executar = lambda cab: a.chamar(servico, "POST", caminho, "profissional", chave,
                                       json=corpo, cabecalhos=ator | cab)
        inicial = executar({})
        self.assertEqual(inicial.status_code, status, inicial.text)
        repetido = executar({})
        self.assertEqual((repetido.status_code, repetido.json()), (status, inicial.json()))
        incompativel = executar({"X-Ator-Unidade-Id": str(uuid4())})
        self.assertEqual(incompativel.status_code, 403, incompativel.text)
        return inicial.json()

    def test_decisao_e_cancelamento_local(self):
        reserva = a.criar_reserva()
        self.comparar("reservas", f"/api/unidade/v1/reservas/{reserva}/decisao",
                      {"decisao": "REJEITAR"}, 200)
        reserva = a.criar_reserva()
        self.comparar("reservas", f"/api/unidade/v1/reservas/{reserva}/cancelar",
                      {"justificativa": "cancelamento de teste"}, 200)

    def test_transicao_de_aceite_exige_o_mesmo_ator_e_unidade(self):
        reserva = a.criar_reserva()
        caminho = f"/internal/v1/reservas/{reserva}/aceite"
        corpo = {"sagaId": str(uuid4())}
        chave = a.nova_chave()
        ator = {"X-Ator-Papel": "PROFISSIONAL", "X-Ator-Id": "profissional-demo",
                "X-Ator-Unidade-Id": a.UNIDADE}
        def executar(**alteracoes):
            return a.chamar("reservas", "POST", caminho, "orquestrador", chave, json=corpo,
                            cabecalhos=ator | alteracoes)
        resposta = executar()
        self.assertEqual(resposta.status_code, 200, resposta.text)
        self.assertEqual(executar().json(), resposta.json())
        self.assertEqual(executar(**{"X-Ator-Unidade-Id": str(uuid4())}).status_code, 403)
        self.assertEqual(executar(**{"X-Ator-Id": "outro-profissional"}).status_code, 403)

    def test_repeticao_dos_pedidos_no_orquestrador(self):
        item = a.item_com_saldo(3)
        reserva = a.criar_reserva(1, item)
        self.comparar("orquestrador", f"/internal/v1/reservas/{reserva}/confirmacoes", None, 202)
        a.esperar_estado(reserva, "CONFIRMADA")
        a.esperar(lambda: not a.sagas(reserva, "encerrada_em IS NULL"))
        resultado = self.comparar("orquestrador", f"/internal/v1/reservas/{reserva}/cancelamentos",
                                   {"justificativa": "cancelamento de teste"}, 202)
        a.esperar_estado(reserva, "CANCELADA")
        chave = resultado["sagaId"]
        caminho = f"/internal/v1/sagas/{chave}"
        self.assertEqual(a.chamar("orquestrador", "GET", caminho, "profissional").status_code, 200)
        self.assertIn(a.chamar("orquestrador", "GET", caminho, "profissional",
                               cabecalhos={"X-Ator-Unidade-Id": str(uuid4())}).status_code, (403, 404))

    def test_entrega_apos_perda_de_resposta_e_repeticoes_concorrentes(self):
        reserva = a.confirmada(1, a.item_com_saldo(3))
        autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
        caminho = "/api/unidade/v1/retiradas"
        corpo = {"autorizacaoId": autorizacao}
        chave = a.nova_chave()
        a.proxies["bff>retiradas"].perder[caminho] = 1
        perdida = a.chamar("gateway", "POST", caminho, "profissional", chave, json=corpo)
        self.assertEqual(perdida.status_code, 503, perdida.text)
        a.esperar_estado(reserva, "RETIRADA")
        esperado = self.comparar("retiradas", caminho, corpo, 201, chave)

        reserva = a.confirmada(1, a.item_com_saldo(3))
        autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
        chave = a.nova_chave()
        barreira = Barrier(6, timeout=10)
        def executar(_):
            barreira.wait()
            return a.entregar(autorizacao, chave)
        with ThreadPoolExecutor(max_workers=6) as executor:
            respostas = list(executor.map(executar, range(6)))
        self.assertEqual([r.status_code for r in respostas], [201] * 6)
        self.assertEqual([r.json() for r in respostas], [respostas[0].json()] * 6)
        self.assertNotEqual(esperado["retiradaId"], respostas[0].json()["retiradaId"])
        retirada = respostas[0].json()["retiradaId"]
        entrega = a.consultar("retiradas", "SELECT count(*) AS n FROM retiradas WHERE autorizacao_id = %s",
                             autorizacao)
        publicacao = a.consultar("retiradas", "SELECT count(*) AS n FROM outbox WHERE aggregate_id = %s", retirada)
        self.assertEqual((entrega[0]["n"], publicacao[0]["n"]), (1, 1))
