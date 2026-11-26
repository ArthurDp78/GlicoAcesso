"""Decisões do grupo: identidade delegada, credenciais, unidades inativas, conflitos, prazo e reconstrução."""
import os
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from uuid import uuid4

import psycopg

from servicos import identidade_demo
from servicos.estoque import projecao
from tests import ambiente as a


def setUpModule():
    a.preparar()


CIDADAO = {"X-Ator-Papel": "CIDADAO", "X-Ator-Id": "cidadao-demo"}
PROFISSIONAL = {"X-Ator-Papel": "PROFISSIONAL", "X-Ator-Id": "profissional-demo", "X-Ator-Unidade-Id": a.UNIDADE}


class IdentidadeDelegada(unittest.TestCase):
    def test_cabecalhos_so_valem_com_credencial_de_bff(self):
        reserva = a.criar_reserva()
        consultar = lambda token, cab: a.chamar("reservas", "GET", f"/internal/v1/reservas/{reserva}", token, cabecalhos=cab).status_code
        self.assertEqual([consultar("bff-cidadao", CIDADAO), consultar("bff-unidade", PROFISSIONAL)], [200, 200])
        self.assertEqual(consultar(None, PROFISSIONAL), 401)
        self.assertEqual(consultar("q" * 40, PROFISSIONAL), 401)
        # Token de usuário e de outros serviços não delegam identidade.
        for nome in ("cidadao", "profissional"):
            self.assertEqual(consultar(a.TOKENS[nome], PROFISSIONAL), 403)
        for nome in ("orquestrador", "retiradas", "reservas", "admin"):
            self.assertEqual(consultar(nome, PROFISSIONAL), 403)
        # Um BFF não age em nome do público do outro, nem sem ator ou com vínculo inválido.
        self.assertEqual([consultar("bff-cidadao", PROFISSIONAL), consultar("bff-unidade", CIDADAO)], [403, 403])
        for ruim in ({}, {"X-Ator-Papel": "PROFISSIONAL"}, {**PROFISSIONAL, "X-Ator-Unidade-Id": "x"}, {**PROFISSIONAL, "X-Ator-Papel": "ADMIN"}):
            self.assertEqual(consultar("bff-unidade", ruim), 403)
        self.assertEqual(consultar("bff-cidadao", {**CIDADAO, "X-Ator-Id": "outro"}), 404)
        self.assertEqual(consultar("bff-unidade", {**PROFISSIONAL, "X-Ator-Unidade-Id": str(uuid4())}), 403)

    def test_operacoes_por_publico(self):
        reserva = a.criar_reserva()
        corpo = {"justificativa": "motivo válido"}
        casos = (("reservas", "POST", "/api/cidadao/v1/reservas", "bff-unidade", PROFISSIONAL, {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}),
                 ("reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/cancelar", "bff-cidadao", CIDADAO, corpo),
                 ("orquestrador", "POST", f"/internal/v1/reservas/{reserva}/confirmacoes", "bff-cidadao", CIDADAO, None),
                 ("retiradas", "POST", "/api/unidade/v1/retiradas", "bff-cidadao", CIDADAO, {"autorizacaoId": str(uuid4())}),
                 ("unidades", "PATCH", f"/internal/v1/unidades/{a.UNIDADE}/status", "bff-cidadao", CIDADAO, {"ativa": True}))
        for servico, metodo, caminho, token, cab, dados in casos:
            self.assertEqual(a.chamar(servico, metodo, caminho, token, a.nova_chave(), json=dados, cabecalhos=cab).status_code, 403, caminho)

    def test_cliente_nao_forja_identidade_pela_borda(self):
        forjado = {"X-Ator-Papel": "CIDADAO", "X-Ator-Id": "vitima"}
        pedido = {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}
        for porta in ("gateway", "bff-cidadao"):
            r = a.chamar(porta, "POST", "/api/cidadao/v1/reservas", "cidadao", a.nova_chave(), json=pedido, cabecalhos=forjado)
            self.assertEqual(r.status_code, 201)
            dono = a.consultar("reservas", "SELECT cidadao_id FROM reservas WHERE reserva_id = %s", r.json()["reservaId"])
            self.assertEqual(dono[0]["cidadao_id"], "cidadao-demo")
        lista = lambda token, cab: a.chamar("gateway", "GET", "/api/unidade/v1/painel/reservas", token, cabecalhos=cab).status_code
        self.assertEqual([lista("cidadao", PROFISSIONAL), lista(None, PROFISSIONAL), lista("bff-unidade", PROFISSIONAL)], [403, 401, 401])

    def test_falha_da_credencial_do_bff_nao_vira_erro_do_usuario(self):
        a.matar("bff-unidade")
        a.subir("bff-unidade", GLICO_BFF_UNIDADE_TOKEN="credencial-desatualizada".ljust(40, "x"))
        try:
            self.assertEqual(a.chamar("gateway", "GET", "/api/unidade/v1/painel/reservas", "profissional").status_code, 503)
        finally:
            a.matar("bff-unidade")
            a.subir("bff-unidade")


class Credenciais(unittest.TestCase):
    def test_validacao(self):
        base = {nome: valor for nome, valor in os.environ.items() if not nome.startswith("GLICO_")}
        exigir = lambda: identidade_demo.exigir_credenciais("GLICO_ADMIN_SERVICE_TOKEN")
        def com(**tokens):
            with mock.patch.dict(os.environ, {**base, **tokens}, clear=True):
                exigir()
        com(GLICO_ADMIN_SERVICE_TOKEN="a" * 32, GLICO_PROFISSIONAL_TOKEN="b" * 32)
        for ruim in ({}, {"GLICO_ADMIN_SERVICE_TOKEN": "a" * 31}, {"GLICO_ADMIN_SERVICE_TOKEN": " " + "a" * 32},
                     {"GLICO_ADMIN_SERVICE_TOKEN": "a" * 32, "GLICO_PROFISSIONAL_TOKEN": "a" * 32},
                     {"GLICO_ADMIN_SERVICE_TOKEN": "a" * 32, "GLICO_CIDADAO_TOKEN": "b" * 32, "GLICO_BFF_UNIDADE_TOKEN": "b" * 32}):
            with self.assertRaises(identidade_demo.CredenciaisInvalidas) as erro:
                com(**ruim)
            for valor in ruim.values():
                self.assertNotIn(valor, str(erro.exception))

    def test_servicos_nao_iniciam_com_tokens_repetidos_ou_ausentes(self):
        for servico in ("unidades", "estoque", "reservas", "retiradas", "orquestrador", "bff_cidadao", "bff_unidade"):
            for alteracao in ({"GLICO_BFF_UNIDADE_TOKEN": a.TOKENS["bff-cidadao"]},
                              {"GLICO_BFF_UNIDADE_TOKEN": "", "GLICO_BFF_CIDADAO_TOKEN": ""}):
                processo = subprocess.run([sys.executable, "-m", "uvicorn", f"servicos.{servico}.main:app", "--port", str(a.porta_livre())],
                                          cwd=a.RAIZ, env={**os.environ, **alteracao}, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(processo.returncode, 0, servico)
                self.assertIn("CredenciaisInvalidas", processo.stderr)


class UnidadeInativa(unittest.TestCase):
    def setUp(self):
        self.item = a.item_com_saldo(10)
        self.solicitadas = [a.criar_reserva(1, self.item) for _ in range(3)]
        self.confirmadas = [a.confirmada(1, self.item) for _ in range(2)]
        a.chamar("unidades", "PATCH", f"/internal/v1/unidades/{a.UNIDADE}/status", "profissional", a.nova_chave(), json={"ativa": False})

    def tearDown(self):
        a.chamar("unidades", "PATCH", f"/internal/v1/unidades/{a.UNIDADE}/status", "profissional", a.nova_chave(), json={"ativa": True})

    def test_nao_recebe_nem_aceita_mas_conclui_o_existente(self):
        pedido = {"unidadeId": a.UNIDADE, "itemId": self.item, "quantidade": 1}
        self.assertEqual(a.chamar("gateway", "POST", "/api/cidadao/v1/reservas", "cidadao", a.nova_chave(), json=pedido).status_code, 422)
        aceita, rejeita, cancela = self.solicitadas
        self.assertEqual(a.aceitar(aceita).status_code, 403)
        # Um pedido direto à SAGA também é recusado por Reservas.
        a.chamar("orquestrador", "POST", f"/internal/v1/reservas/{aceita}/confirmacoes", "profissional", a.nova_chave())
        a.esperar(lambda: (s := a.saga_do_tipo(aceita, "CONFIRMACAO")) and s["estado"] == "INTERROMPIDA")
        self.assertEqual(a.estado(aceita), "SOLICITADA")

        painel = a.chamar("gateway", "GET", "/api/unidade/v1/painel/reservas", "profissional")
        self.assertIn(aceita, [r["reservaId"] for r in painel.json()])
        self.assertEqual(a.chamar("gateway", "GET", f"/api/unidade/v1/painel/reservas/{self.confirmadas[0]}", "profissional").status_code, 200)
        r = a.chamar("gateway", "POST", f"/api/unidade/v1/reservas/{rejeita}/decisao", "profissional", a.nova_chave(), json={"decisao": "REJEITAR"})
        self.assertEqual((r.status_code, a.estado(rejeita)), (200, "REJEITADA"))
        r = a.chamar("reservas", "POST", f"/api/unidade/v1/reservas/{cancela}/cancelar", "profissional", a.nova_chave(), json={"justificativa": "unidade inativa"})
        self.assertEqual((r.status_code, a.estado(cancela)), (200, "CANCELADA"))
        self.assertEqual(a.cancelar_saga(self.confirmadas[0], "profissional").status_code, 202)
        a.esperar_estado(self.confirmadas[0], "CANCELADA")
        self.assertEqual(a.entregar(a.autorizacao(self.confirmadas[1]).json()["autorizacaoId"]).status_code, 201)
        a.esperar_estado(self.confirmadas[1], "RETIRADA")

    def test_bff_cidadao_le_so_campos_publicos(self):
        caminho = f"/internal/v1/unidades/{a.UNIDADE}"
        publica = a.chamar("unidades", "GET", caminho, "bff-cidadao")
        self.assertEqual(set(publica.json()), {"unidadeId", "nome", "endereco", "horarioAtendimento", "orientacoesRetirada"})
        completa = a.chamar("unidades", "GET", caminho, "profissional").json()
        self.assertEqual(completa["ativa"], False)
        self.assertIn("contatos", completa)
        self.assertEqual([a.chamar("unidades", "GET", caminho, t).status_code for t in (a.TOKENS["cidadao"], "admin", None)], [403, 403, 401])
        self.assertEqual(a.chamar("unidades", "GET", f"/internal/v1/unidades/{uuid4()}", "bff-cidadao").status_code, 404)


class PrazoEExpiracao(unittest.TestCase):
    def test_limite_do_prazo(self):
        prazo = lambda h: a.chamar("unidades", "PUT", f"/internal/v1/unidades/{a.UNIDADE}/prazo-analise", "profissional", a.nova_chave(), json={"prazoAnaliseHoras": h}).status_code
        self.assertEqual([prazo(h) for h in (1, 720, 721, 0, 70000000)], [200, 200, 422, 422, 422])
        with self.assertRaises(psycopg.errors.CheckViolation):
            a.consultar("unidades", "UPDATE unidades SET prazo_analise_horas = 721 WHERE unidade_id = %s", a.UNIDADE)
        # Um prazo anterior à regra é preservado, mas Reservas o trata como configuração inválida.
        a.consultar("unidades", "UPDATE unidades SET prazo_analise_horas = 70000000, prazo_legado = true WHERE unidade_id = %s", a.UNIDADE)
        try:
            self.assertEqual(a.chamar("unidades", "GET", f"/internal/v1/unidades/{a.UNIDADE}/prazo-analise", "reservas").json(), {"prazoAnaliseHoras": 70000000})
            pedido = {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}
            self.assertEqual(a.chamar("gateway", "POST", "/api/cidadao/v1/reservas", "cidadao", a.nova_chave(), json=pedido).status_code, 503)
        finally:
            self.assertEqual(prazo(24), 200)
        self.assertFalse(a.consultar("unidades", "SELECT prazo_legado FROM unidades WHERE unidade_id = %s", a.UNIDADE)[0]["prazo_legado"])

    def test_cancelamento_depois_do_prazo_e_antes_da_expiracao(self):
        a.matar("reservas")
        a.subir("reservas", GLICO_EXPIRACAO_INTERVALO="3600")
        try:
            reserva, outra = a.criar_reserva(), a.criar_reserva()
            a.consultar("reservas", "UPDATE reservas SET decisao_ate = now() - interval '1 second'")
            rejeitar = a.chamar("gateway", "POST", f"/api/unidade/v1/reservas/{outra}/decisao", "profissional", a.nova_chave(), json={"decisao": "REJEITAR"})
            self.assertEqual(rejeitar.status_code, 409)
            r = a.chamar("reservas", "POST", f"/api/cidadao/v1/reservas/{reserva}/cancelar", "cidadao", a.nova_chave())
            self.assertEqual((r.status_code, a.estado(reserva)), (200, "CANCELADA"))
        finally:
            a.matar("reservas")
            a.subir("reservas")
        a.esperar_estado(outra, "EXPIRADA")


class Conflitos(unittest.TestCase):
    def item(self, nome, tipo="INSUMO", chave=None):
        return a.chamar("estoque", "POST", "/internal/v1/itens", "admin", chave or a.nova_chave(), json={"nome": nome, "tipo": tipo})

    def test_itens(self):
        nome, chave = f"Água  Destilada {uuid4()}", a.nova_chave()
        primeiro = self.item(nome, chave=chave)
        self.assertEqual(primeiro.status_code, 201)
        for igual in (nome, nome.upper(), "  " + nome.replace("  ", " \t ") + " "):
            r = self.item(igual)
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "CADASTRO_CONFLITANTE"))
        self.assertEqual(self.item(nome, chave=chave).json(), primeiro.json())
        outro = self.item(nome, "MEDICAMENTO")
        self.assertEqual(outro.status_code, 201)
        atualizar = lambda corpo: a.chamar("estoque", "PUT", f"/internal/v1/itens/{outro.json()['itemId']}", "admin", a.nova_chave(), json=corpo)
        self.assertEqual(atualizar({"nome": nome.lower(), "tipo": "INSUMO"}).json()["codigo"], "CADASTRO_CONFLITANTE")
        self.assertEqual(atualizar({"nome": nome.upper(), "tipo": "MEDICAMENTO", "descricao": "x"}).status_code, 200)
        self.assertEqual(self.item("n" * 20000).status_code, 201)
        chave = a.nova_chave()
        self.assertEqual([self.item(nome, chave=chave).status_code for _ in range(2)], [409, 409])

    def test_itens_concorrentes(self):
        nome = f"Concorrente {uuid4()}"
        with ThreadPoolExecutor(8) as pool:
            codigos = sorted(r.status_code for r in pool.map(lambda i: self.item(nome.upper() if i % 2 else nome), range(8)))
        self.assertEqual(codigos, [201] + [409] * 7)

    def test_unidades(self):
        dados = {"nome": f"UBS {uuid4()}", "logradouro": "Rua A", "numero": "1", "bairro": "Centro", "cidade": "Lavras", "estado": "MG",
                 "cep": "37200-000", "orientacoesRetirada": "Documento.", "contatos": [], "horarios": [], "prazoAnaliseHoras": 24}
        criar = lambda **m: a.chamar("unidades", "POST", "/internal/v1/unidades", "admin", a.nova_chave(), json={**dados, **m})
        with ThreadPoolExecutor(6) as pool:
            respostas = list(pool.map(lambda i: criar(cidade="LAVRAS " if i % 2 else "Lavras"), range(6)))
        self.assertEqual(sorted(r.status_code for r in respostas), [201] + [409] * 5)
        self.assertEqual(criar(nome=dados["nome"].upper(), logradouro=" rua   a ").json()["codigo"], "CADASTRO_CONFLITANTE")
        outra = criar(numero="2")
        self.assertEqual(outra.status_code, 201)
        identificador = outra.json()["unidadeId"]
        atualizar = lambda corpo: a.chamar("unidades", "PUT", f"/internal/v1/unidades/{identificador}", "profissional", a.nova_chave(), json=corpo, cabecalhos={"X-Ator-Unidade-Id": identificador})
        conflito = atualizar({**dados, "horarios": [{"diaSemana": 1, "horarioInicial": "08:00:00", "horarioFinal": "09:00:00"}]})
        self.assertEqual((conflito.status_code, conflito.json()["codigo"]), (409, "CADASTRO_CONFLITANTE"))
        self.assertEqual(a.chamar("unidades", "GET", f"/internal/v1/unidades/{identificador}", "reservas").json(), outra.json())
        self.assertEqual(atualizar({**dados, "numero": "2", "prazoAnaliseHoras": 48}).status_code, 200)

    def test_migracoes_preservam_duplicatas(self):
        admin = os.environ["GLICO_TESTE_PG"]
        for servico, ate in (("estoque", "005"), ("unidades", "004")):
            banco = f"teste_legado_{servico}"
            with psycopg.connect(admin, autocommit=True) as conexao:
                conexao.execute(f"DROP DATABASE IF EXISTS {banco} WITH (FORCE)")
                conexao.execute(f"CREATE DATABASE {banco}")
            with psycopg.connect(psycopg.conninfo.make_conninfo(admin, dbname=banco)) as c:
                arquivos = sorted((a.RAIZ / f"servicos/{servico}/migrations").glob("*.sql"))
                for arquivo in arquivos:
                    if arquivo.name.startswith(ate):
                        break
                    c.execute(arquivo.read_text(encoding="utf-8"))
                c.execute((a.RAIZ / f"servicos/{servico}/demo.sql").read_text(encoding="utf-8"))
                if servico == "estoque":
                    inserir, tabela = "INSERT INTO itens (item_id, nome, tipo) VALUES (gen_random_uuid(), 'TIRAS  reagentes para glicemia', 'INSUMO')", "itens"
                else:
                    inserir, tabela = """INSERT INTO unidades SELECT gen_random_uuid(), upper(nome), logradouro, numero, bairro, cidade, estado, cep,
                        orientacoes_retirada, 9999, ativa, now() + interval '1 hour', now() FROM unidades LIMIT 1""", "unidades"
                c.execute(inserir)
                if servico == "estoque":
                    c.execute("UPDATE itens SET created_at = now() + interval '1 hour' WHERE nome LIKE 'TIRAS%'")
                c.execute(arquivos[int(ate) - 1].read_text(encoding="utf-8"))
                c.execute((a.RAIZ / f"servicos/{servico}/demo.sql").read_text(encoding="utf-8"))
                self.assertEqual(c.execute(f"SELECT count(*), count(*) FILTER (WHERE duplicidade_legada) FROM {tabela}").fetchone(), (2, 1))
                if servico == "unidades":
                    # A unidade legada continua operável em campos não relacionados.
                    c.execute("UPDATE unidades SET ativa = false WHERE duplicidade_legada")
                    self.assertEqual(c.execute("SELECT prazo_analise_horas FROM unidades WHERE prazo_legado").fetchall(), [(9999,)])
                    inserir = inserir.replace("9999", "24").replace("upper(nome)", "lower(nome)").replace("LIMIT 1", "WHERE NOT duplicidade_legada LIMIT 1")
                with self.assertRaises(psycopg.errors.UniqueViolation), c.transaction():
                    c.execute(inserir)


class Reconstrucao(unittest.TestCase):
    def linha(self, item):
        return a.consultar("estoque", "SELECT estoque_fisico_atual, quantidade_alocada, estoque_version FROM disponibilidade WHERE item_id = %s", item)

    def canonico(self, item):
        return a.consultar("estoque", "SELECT estoque_fisico_atual, quantidade_alocada, estoque_version FROM saldos WHERE item_id = %s", item)

    def test_recupera_projecao_ausente_divergente_e_orfa(self):
        itens = [a.item_com_saldo(n) for n in (3, 4, 5)]
        a.esperar(lambda: all(self.linha(i) == self.canonico(i) for i in itens))
        inbox = a.consultar("estoque", "SELECT count(*) AS n FROM inbox")
        a.consultar("estoque", "DELETE FROM disponibilidade WHERE item_id = %s", itens[0])
        a.consultar("estoque", "UPDATE disponibilidade SET estoque_fisico_atual = 99, estoque_version = 999 WHERE item_id = %s", itens[1])
        a.consultar("estoque", """
            INSERT INTO disponibilidade (unidade_id, item_id, estoque_fisico_atual, quantidade_alocada, permite_reserva, atualizado_em, estoque_version)
            SELECT gen_random_uuid(), item_id, 1, 0, true, now(), 1 FROM itens LIMIT 1""")
        saida = subprocess.run([sys.executable, "-m", "servicos.estoque.projecao"], cwd=a.RAIZ, capture_output=True, text=True, timeout=60)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertIn("1 sem saldo removidas", saida.stdout)
        self.assertEqual([self.linha(i) for i in itens], [self.canonico(i) for i in itens])
        self.assertEqual(a.consultar("estoque", "SELECT count(*) AS n FROM inbox"), inbox)

    def test_eventos_pendentes_nao_regridem_nem_se_perdem(self):
        item = a.item_com_saldo(5)
        a.esperar(lambda: self.linha(item) == self.canonico(item))
        a.matar("estoque")
        a.subir("estoque", RABBITMQ_URL="amqp://guest:guest@127.0.0.1:1/%2F")
        base = f"/api/unidade/v1/estoque/{a.UNIDADE}/itens/{item}/entradas"
        entrada = lambda: a.chamar("estoque", "POST", base, "profissional", a.nova_chave(), json={"quantidade": 1, "motivo": "m"})
        try:
            for _ in range(5):
                self.assertEqual(entrada().status_code, 201)
            self.assertNotEqual(self.linha(item), self.canonico(item))
            projecao.reconstruir()
            refletido = self.canonico(item)
            self.assertEqual(self.linha(item), refletido)
            entrada()  # Posterior à reconstrução: chega pela Outbox.
        finally:
            a.matar("estoque")
            a.subir("estoque")
        a.esperar(lambda: self.linha(item) == self.canonico(item) != refletido)
        pendentes = "SELECT 1 FROM outbox WHERE status = 'PENDENTE' AND payload->>'itemId' = %s"
        a.esperar(lambda: not a.consultar("estoque", pendentes, item))
        self.assertEqual(self.linha(item), self.canonico(item))

    def test_concorre_com_escritas_e_consumo(self):
        item, parar, regressoes = a.item_com_saldo(1), threading.Event(), []
        a.esperar(lambda: self.linha(item))

        def observar():
            ultima = 0
            while not parar.is_set():
                atual = self.linha(item)[0]["estoque_version"]
                if atual < ultima:
                    regressoes.append((ultima, atual))
                ultima = atual

        def repetir():
            while not parar.is_set():
                projecao.reconstruir()

        threads = [threading.Thread(target=f) for f in (observar, repetir)]
        for t in threads:
            t.start()
        base = f"/api/unidade/v1/estoque/{a.UNIDADE}/itens/{item}/entradas"
        with ThreadPoolExecutor(4) as pool:
            codigos = {r.status_code for r in pool.map(lambda _: a.chamar("estoque", "POST", base, "profissional", a.nova_chave(), json={"quantidade": 1, "motivo": "m"}), range(60))}
        parar.set()
        for t in threads:
            t.join()
        self.assertEqual((codigos, regressoes), ({201}, []))
        a.esperar(lambda: self.linha(item) == self.canonico(item))
        self.assertEqual(self.canonico(item)[0]["estoque_fisico_atual"], 61)

    def test_espera_evento_em_aplicacao(self):
        item = a.item_com_saldo(2)
        a.esperar(lambda: self.linha(item) == self.canonico(item))
        with psycopg.connect(os.environ["ESTOQUE_DATABASE_URL"]) as consumidor, ThreadPoolExecutor(1) as pool:
            consumidor.execute("UPDATE disponibilidade SET estoque_fisico_atual = 2 WHERE item_id = %s", (item,))
            futuro = pool.submit(projecao.reconstruir)
            with self.assertRaises(TimeoutError):
                futuro.result(timeout=1)
            self.assertTrue(self.linha(item))  # As consultas não são bloqueadas.
            consumidor.commit()
            futuro.result(timeout=10)


class ContratosDeEntrada(unittest.TestCase):
    def test_chave_idempotente_ate_128_e_campos_extras(self):
        criar = lambda chave, **extra: a.chamar("estoque", "POST", "/internal/v1/itens", "admin", chave, json={"nome": f"C {uuid4()}", "tipo": "INSUMO", **extra}).status_code
        chave = uuid4().hex * 4
        self.assertEqual((len(chave), criar(chave), criar(chave + "x"), criar(a.nova_chave(), extra=1)), (128, 201, 422, 422))
        cancelar = lambda k: a.chamar("reservas", "POST", f"/api/cidadao/v1/reservas/{uuid4()}/cancelar", "cidadao", k).status_code
        self.assertEqual([cancelar(chave), cancelar(chave + "x")], [404, 400])

    def test_credenciais_e_entradas_invalidas_em_todas_as_operacoes(self):
        unidade, item = f"/internal/v1/unidades/{a.UNIDADE}", f"/api/unidade/v1/estoque/{a.UNIDADE}/itens/{uuid4()}"
        # (serviço, método, caminho, token certo, token de outro chamador, caminho ou corpo inválido → 422)
        casos = (
            ("estoque", "GET", f"/api/unidade/v1/estoque/{a.UNIDADE}/itens", "profissional", "cidadao", "/api/unidade/v1/estoque/x/itens"),
            ("estoque", "POST", "/internal/v1/itens", "admin", "profissional", {}),
            ("estoque", "PUT", f"/internal/v1/itens/{uuid4()}", "admin", "profissional", {}),
            ("estoque", "GET", f"/internal/v1/unidades/{a.UNIDADE}/itens/{uuid4()}/permissao-reserva", "reservas", "profissional", "/internal/v1/unidades/x/itens/x/permissao-reserva"),
            ("estoque", "PUT", item + "/permissao", "profissional", "cidadao", {}),
            ("estoque", "POST", item + "/entradas", "profissional", "cidadao", {}),
            ("estoque", "POST", item + "/ajustes", "profissional", "cidadao", {}),
            ("reservas", "GET", "/api/unidade/v1/reservas", "profissional", "cidadao", None),
            ("reservas", "GET", f"/internal/v1/reservas/{uuid4()}/estado", "retiradas", "profissional", "/internal/v1/reservas/x/estado"),
            ("reservas", "GET", f"/internal/v1/reservas/{uuid4()}", "cidadao", "admin", "/internal/v1/reservas/x"),
            ("retiradas", "POST", "/api/unidade/v1/retiradas", "profissional", "cidadao", {}),
            ("retiradas", "GET", f"/internal/v1/autorizacoes/{uuid4()}", "profissional", "cidadao", "/internal/v1/autorizacoes/x"),
            ("orquestrador", "GET", f"/internal/v1/sagas/{uuid4()}", "cidadao", "retiradas", "/internal/v1/sagas/x"),
            ("unidades", "GET", unidade, "reservas", "admin", "/internal/v1/unidades/x"),
            ("unidades", "GET", unidade + "/prazo-analise", "reservas", "profissional", "/internal/v1/unidades/x/prazo-analise"),
            *(("unidades", m, unidade + s, "profissional", "cidadao", {}) for m, s in (("PUT", ""), ("PUT", "/horarios"), ("PATCH", "/status"), ("PUT", "/prazo-analise"))),
        )
        for servico, metodo, caminho, certo, errado, invalido in casos:
            with self.subTest(f"{metodo} {caminho}"):
                chamar = lambda token, c=caminho, **kw: a.chamar(servico, metodo, c, token, a.nova_chave(), **kw).status_code
                self.assertEqual([chamar(None), chamar("z" * 40), chamar(errado)], [401, 401, 403])
                if isinstance(invalido, str):
                    self.assertEqual(chamar(certo, invalido), 422)
                elif invalido is not None:
                    self.assertEqual(chamar(certo, json=invalido), 422)
        self.assertEqual(a.chamar("estoque", "GET", "/api/cidadao/v1/estoque/disponibilidade").status_code, 422)
        permissao = a.chamar("reservas", "GET", "/internal/v1/reservas/x/permissao-cancelamento", "orquestrador", cabecalhos=CIDADAO)
        self.assertEqual(permissao.status_code, 422)
