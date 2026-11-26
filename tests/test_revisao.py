"""Regressões encontradas na revisão crítica e cobertura das respostas documentadas."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import psycopg
from pika.exceptions import AMQPConnectionError
from psycopg.types.json import Jsonb

from servicos import mensageria
from servicos.orquestrador import executor
from tests import ambiente as a


def setUpModule():
    a.preparar()


def corpo_alocacao(item, reserva=None):
    return {"sagaId": str(uuid4()), "reservaId": reserva or str(uuid4()), "unidadeId": a.UNIDADE, "itemId": item, "quantidade": 1}


class Executor(unittest.TestCase):
    def chamar(self, status, corpo):
        etapa = {"saga_id": uuid4(), "etapa_id": "ACEITAR_RESERVA", "destino": "reservas", "idempotency_key": "k",
                 "correlation_id": uuid4(), "dados_comando": {"metodo": "POST", "caminho": "/x", "corpo": {}, "cabecalhos": {}}}
        transporte = httpx.MockTransport(lambda _: httpx.Response(status, json=corpo))
        with httpx.Client(transport=transporte) as cliente:
            return executor.chamar(cliente, etapa)[0]

    def test_erro_de_configuracao_nao_e_recusa_de_negocio(self):
        # Credencial de outro serviço ou rota inexistente não provam ausência de efeito: o comando é repetido.
        real = a.chamar("reservas", "POST", f"/internal/v1/reservas/{uuid4()}/aceite", "retiradas", "k", json={"sagaId": str(uuid4())})
        self.assertEqual(real.status_code, 403)
        self.assertIsNone(self.chamar(403, real.json()))
        self.assertIsNone(self.chamar(404, a.chamar("reservas", "POST", "/internal/v1/rota-errada").json()))
        self.assertEqual(self.chamar(403, {"detail": "Reserva de outra unidade."}), 403)
        self.assertEqual(self.chamar(404, {"detail": "Reserva não encontrada."}), 404)

    def test_revogacao_404_apos_autorizacao_criada_nao_libera(self):
        class Falsa:
            def execute(self, *_):
                return self
        etapa = {"saga_id": "S", "reserva_id": "R", "etapa_id": "CANCELAR_AUTORIZACAO", "dados_comando": {}}
        corpo = {"codigo": "AUTORIZACAO_NAO_ENCONTRADA"}
        self.assertFalse(executor.avancar(Falsa(), {**etapa, "autorizacao_criada": True}, 404, corpo))
        self.assertTrue(executor.avancar(Falsa(), {**etapa, "autorizacao_criada": False}, 404, corpo))


class Concorrencia(unittest.TestCase):
    def test_alocacoes_da_mesma_reserva_em_itens_diferentes(self):
        itens = [a.item_com_saldo(10) for _ in range(2)]
        for _ in range(12):
            reserva = str(uuid4())
            with ThreadPoolExecutor(4) as pool:
                codigos = sorted(r.status_code for r in pool.map(lambda i: a.chamar(
                    "estoque", "POST", "/internal/v1/alocacoes", "orquestrador", a.nova_chave(),
                    json=corpo_alocacao(itens[i % 2], reserva)), range(4)))
            self.assertEqual(codigos, [201, 409, 409, 409])
            a.chamar("estoque", "DELETE", f"/internal/v1/alocacoes/{reserva}", "orquestrador", a.nova_chave(), cabecalhos={"X-Saga-Id": str(uuid4())})
        self.assertEqual([a.saldo(i) for i in itens], [(10, 0)] * 2)

    def test_preparacoes_concorrentes(self):
        for _ in range(12):
            reserva = str(uuid4())
            with ThreadPoolExecutor(4) as pool:
                codigos = sorted(r.status_code for r in pool.map(lambda _: a.chamar(
                    "retiradas", "POST", "/internal/v1/autorizacoes", "orquestrador", a.nova_chave(),
                    json=corpo_alocacao(a.ITEM, reserva)), range(4)))
            self.assertEqual(codigos, [201, 409, 409, 409])


class Replicas(unittest.TestCase):
    def test_dois_orquestradores_nao_duplicam_etapas(self):
        a.APPS["orquestrador-2"], a.portas["orquestrador-2"] = "orquestrador", a.porta_livre()
        a.subir("orquestrador-2", **a.desvios("orquestrador"))
        try:
            a.proxies["estoque"].limpar()
            item = a.item_com_saldo(10)
            reservas = [a.criar_reserva(1, item) for _ in range(8)]
            with ThreadPoolExecutor(8) as pool:
                self.assertEqual({r.status_code for r in pool.map(a.aceitar, reservas)}, {202})
            for reserva in reservas:
                a.esperar_estado(reserva, "CONFIRMADA")
            self.assertEqual(a.saldo(item), (10, 8))
            with ThreadPoolExecutor(8) as pool:
                list(pool.map(a.cancelar_saga, reservas))
            for reserva in reservas:
                a.esperar_estado(reserva, "CANCELADA")
            a.esperar(lambda: a.saldo(item) == (10, 0))
            # Cada comando lógico chegou ao destino uma única vez, sem disputa entre as réplicas.
            chaves = [v[2] for v in a.proxies["estoque"].vistos]
            self.assertEqual((len(chaves), len(set(chaves))), (16, 16))
        finally:
            a.matar("orquestrador-2")


class Entradas(unittest.TestCase):
    def test_texto_com_nulo_e_tipos_incorretos(self):
        admin = lambda corpo: a.chamar("estoque", "POST", "/internal/v1/itens", "admin", a.nova_chave(), json=corpo).status_code
        self.assertEqual(admin({"nome": "a\u0000b", "tipo": "INSUMO"}), 422)
        self.assertEqual(admin({"nome": "ab", "tipo": "INSUMO", "descricao": "\u0000"}), 422)
        self.assertEqual(admin({"nome": "ab", "tipo": "INSUMO", "descricao": None}), 422)
        reserva = a.criar_reserva()
        cancelar = a.chamar("reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/cancelar", "profissional", a.nova_chave(), json={"justificativa": "abcde\u0000"})
        self.assertEqual(cancelar.status_code, 400)
        self.assertEqual(a.cancelar_saga(reserva, json={"justificativa": None}).status_code, 400)
        horarios = {"horarios": [{"diaSemana": 1, "horarioInicial": 28800, "horarioFinal": 43200}]}
        self.assertEqual(a.chamar("unidades", "PUT", f"/internal/v1/unidades/{a.UNIDADE}/horarios", "profissional", a.nova_chave(), json=horarios).status_code, 422)

    def test_correlacao_e_sempre_gravada(self):
        item, reserva = a.item_com_saldo(1), str(uuid4())
        a.chamar("estoque", "POST", "/internal/v1/alocacoes", "orquestrador", a.nova_chave(), json=corpo_alocacao(item, reserva))
        a.chamar("retiradas", "POST", "/internal/v1/autorizacoes", "orquestrador", a.nova_chave(), json=corpo_alocacao(item, reserva))
        for servico, tabela in (("estoque", "alocacoes"), ("retiradas", "autorizacoes")):
            linha = a.consultar(servico, f"SELECT correlation_id FROM {tabela} WHERE reserva_id = %s", reserva)
            self.assertIsNotNone(linha[0]["correlation_id"])


class Outbox(unittest.TestCase):
    def test_queda_do_broker_registra_tentativa_e_adia(self):
        dsn = psycopg.conninfo.make_conninfo(os.environ["GLICO_TESTE_PG"], dbname="teste_outbox")
        with psycopg.connect(os.environ["GLICO_TESTE_PG"], autocommit=True) as conexao:
            conexao.execute("DROP DATABASE IF EXISTS teste_outbox WITH (FORCE)")
            conexao.execute("CREATE DATABASE teste_outbox")
        os.environ["TESTE_OUTBOX_URL"] = dsn
        with psycopg.connect(dsn) as conexao:
            for arquivo in sorted((a.RAIZ / "servicos/retiradas/migrations").glob("*.sql")):
                conexao.execute(arquivo.read_text(encoding="utf-8"))
            for _ in range(2):
                conexao.execute("""INSERT INTO outbox (event_id, event_type, event_version, aggregate_type, aggregate_id, correlation_id, occurred_at, payload)
                    VALUES (%s, 'x', 1, 'X', 'x', %s, now(), %s)""", (uuid4(), uuid4(), Jsonb({})))

        class Canal:
            caido, publicados = True, []

            def basic_publish(self, _exchange, _rota, corpo, *_, **__):
                if self.caido:
                    raise AMQPConnectionError("segredo")
                self.publicados.append(corpo)

        canal = Canal()
        ler = lambda: psycopg.connect(dsn).execute("SELECT status, attempts, last_error, next_retry_at > now() FROM outbox ORDER BY created_at, attempts DESC").fetchall()
        with self.assertRaises(AMQPConnectionError):
            mensageria.publicar_pendentes("TESTE_OUTBOX_URL", canal)
        self.assertEqual(sorted(ler(), key=lambda l: -l[1]), [("PENDENTE", 1, "AMQPConnectionError", True), ("PENDENTE", 0, None, False)])
        canal.caido = False
        a.esperar(lambda: mensageria.publicar_pendentes("TESTE_OUTBOX_URL", canal) == 0 and len(canal.publicados) == 2)
        self.assertEqual({l[:3] for l in ler()}, {("PUBLICADO", 2, None), ("PUBLICADO", 1, None)})


def sem_banco(nome, variavel, operacoes):
    """Reinicia o serviço com o banco inacessível e devolve os status das operações."""
    a.matar(nome)
    a.subir(nome, **{variavel: "postgresql://x:x@127.0.0.1:1/x"})
    try:
        return [a.chamar(nome, *args, **kw).status_code for args, kw in operacoes]
    finally:
        a.matar(nome)
        a.subir(nome)


class RespostasDocumentadas(unittest.TestCase):
    """Percorre as respostas dos contratos; `tests.contratos` valida corpos e cabeçalhos gravados."""

    def test_unidades_404_e_409(self):
        base, desconhecida = f"/internal/v1/unidades/{a.UNIDADE}", str(uuid4())
        cadastro = {"nome": "N", "logradouro": "L", "numero": "1", "bairro": "B", "cidade": "C", "estado": "MG", "cep": "12345-678",
                    "orientacoesRetirada": "O", "contatos": [], "horarios": [], "prazoAnaliseHoras": 24}
        comandos = (("PUT", "", cadastro, {**cadastro, "nome": "M"}), ("PUT", "/horarios", {"horarios": []}, {"horarios": [{"diaSemana": 2, "horarioInicial": "08:00:00", "horarioFinal": "09:00:00"}]}),
                    ("PATCH", "/status", {"ativa": True}, {"ativa": False}), ("PUT", "/prazo-analise", {"prazoAnaliseHoras": 24}, {"prazoAnaliseHoras": 25}))
        for metodo, sufixo, corpo, _ in comandos:
            r = a.chamar("unidades", metodo, f"/internal/v1/unidades/{desconhecida}{sufixo}", "profissional", a.nova_chave(),
                         json=corpo, cabecalhos={"X-Ator-Unidade-Id": desconhecida})
            self.assertEqual(r.status_code, 404)
        for metodo, sufixo, corpo, outro in comandos:
            chave = a.nova_chave()
            self.assertEqual(a.chamar("unidades", metodo, base + sufixo, "profissional", chave, json=corpo).status_code, 200)
            r = a.chamar("unidades", metodo, base + sufixo, "profissional", chave, json=outro)
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "CHAVE_IDEMPOTENTE_CONFLITANTE"))

    def test_estoque(self):
        item, chave = a.item_com_saldo(5), a.nova_chave()
        base, outra = f"/api/unidade/v1/estoque/{a.UNIDADE}/itens/{item}", f"/api/unidade/v1/estoque/{uuid4()}/itens/{item}"
        prof = lambda m, c, corpo=None, k=None, t="profissional": a.chamar("estoque", m, c, t, k or a.nova_chave(), json=corpo).status_code
        self.assertEqual(a.chamar("estoque", "GET", "/api/cidadao/v1/estoque/itens").status_code, 200)
        self.assertEqual(prof("GET", f"/api/unidade/v1/estoque/{a.UNIDADE}/itens"), 200)
        self.assertEqual(prof("GET", f"/api/unidade/v1/estoque/{uuid4()}/itens"), 403)
        self.assertEqual(prof("PUT", base + "/permissao", {"permiteReserva": True}, chave), 200)
        self.assertEqual(prof("PUT", base + "/permissao", {"permiteReserva": False}, chave), 409)
        self.assertEqual(prof("PUT", base + "/permissao", {"permiteReserva": True}, t="q" * 40), 401)
        self.assertEqual(prof("POST", outra + "/entradas", {"quantidade": 1, "motivo": "m"}), 403)
        self.assertEqual(prof("POST", outra + "/ajustes", {"variacaoFisica": 1, "motivo": "m"}), 403)
        self.assertEqual(prof("POST", f"/api/unidade/v1/estoque/{a.UNIDADE}/itens/{uuid4()}/ajustes", {"variacaoFisica": 1, "motivo": "m"}), 404)
        self.assertEqual(prof("PUT", f"/internal/v1/itens/{item}", {"nome": "A", "tipo": "INSUMO"}, chave, "admin"), 200)
        self.assertEqual(prof("PUT", f"/internal/v1/itens/{item}", {"nome": "B", "tipo": "INSUMO"}, chave, "admin"), 409)
        permissao = f"/internal/v1/unidades/{a.UNIDADE}/itens/{item}/permissao-reserva"
        self.assertEqual(prof("GET", permissao, t="reservas"), 200)
        self.assertEqual(prof("GET", f"/internal/v1/unidades/{a.UNIDADE}/itens/{uuid4()}/permissao-reserva", t="reservas"), 404)
        alocar = lambda corpo, t="orquestrador", k=None: prof("POST", "/internal/v1/alocacoes", corpo, k, t)
        self.assertEqual([alocar(corpo_alocacao(str(uuid4()))), alocar(corpo_alocacao(item), "q" * 40), alocar(corpo_alocacao(item), "profissional")], [404, 401, 403])
        liberar = lambda t="orquestrador", c={"X-Saga-Id": str(uuid4())}: a.chamar("estoque", "DELETE", f"/internal/v1/alocacoes/{uuid4()}", t, a.nova_chave(), cabecalhos=c).status_code
        self.assertEqual([liberar(), liberar(c={}), liberar("q" * 40), liberar("cidadao")], [204, 400, 401, 403])
        self.assertEqual(sem_banco("estoque", "ESTOQUE_DATABASE_URL", [
            (("POST", "/internal/v1/alocacoes", "orquestrador", "k"), {"json": corpo_alocacao(item)}),
            (("DELETE", f"/internal/v1/alocacoes/{uuid4()}", "orquestrador", "k"), {"cabecalhos": {"X-Saga-Id": str(uuid4())}}),
            (("GET", permissao, "reservas"), {})]), [503] * 3)

    def test_reservas(self):
        reserva, saga = a.criar_reserva(), {"sagaId": str(uuid4())}
        ator = {"X-Ator-Papel": "PROFISSIONAL", "X-Ator-Id": "p", "X-Ator-Unidade-Id": a.UNIDADE}
        r = lambda m, c, t=None, k=None, corpo=None, cab={}: a.chamar("reservas", m, c, t, k or a.nova_chave(), json=corpo, cabecalhos=cab).status_code
        pedido, chave = {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}, a.nova_chave()
        self.assertEqual([r("POST", "/api/cidadao/v1/reservas", "cidadao", chave, c) for c in (pedido, pedido, {**pedido, "quantidade": 2})], [201, 201, 409])
        self.assertEqual(r("POST", "/api/cidadao/v1/reservas", "cidadao", None, {**pedido, "unidadeId": str(uuid4())}), 422)
        self.assertEqual(r("POST", "/api/cidadao/v1/reservas", None, None, pedido), 401)
        self.assertEqual([r("GET", "/api/unidade/v1/reservas", t) for t in ("profissional", "cidadao")], [200, 403])
        self.assertEqual([r("GET", f"/internal/v1/reservas/{reserva}", t) for t in ("cidadao", "profissional", "q" * 40)], [200, 200, 401])
        self.assertEqual(r("GET", f"/internal/v1/reservas/{uuid4()}", "cidadao"), 404)
        decidir = lambda corpo, t="profissional", i=reserva: r("POST", f"/api/unidade/v1/reservas/{i}/decisao", t, None, corpo)
        self.assertEqual([decidir({}), decidir({"decisao": "ACEITAR"}, "q" * 40), decidir({"decisao": "ACEITAR"}, "cidadao"), decidir({"decisao": "ACEITAR"}, i=uuid4())], [400, 401, 403, 404])
        cidadao, unidade = (f"/api/{p}/v1/reservas/{reserva}/cancelar" for p in ("cidadao", "unidade"))
        self.assertEqual(a.chamar("reservas", "POST", cidadao, "cidadao").status_code, 400)
        self.assertEqual([r("POST", cidadao, "q" * 40), r("POST", unidade, "q" * 40, None, {"justificativa": "válida"})], [401, 401])
        self.assertEqual(r("POST", f"/api/unidade/v1/reservas/{uuid4()}/cancelar", "profissional", None, {"justificativa": "válida"}), 404)
        for comando in ("aceite", "confirmar", "falhar-confirmacao", "finalizar-cancelamento", "iniciar-cancelamento"):
            com = lambda t="orquestrador", corpo=saga, i=reserva: r("POST", f"/internal/v1/reservas/{i}/{comando}", t, None, corpo, ator)
            self.assertEqual([com(corpo={}), com("q" * 40), com("retiradas")], [400, 401, 403], comando)
            corpo = {**saga, "justificativa": "motivo válido"} if comando.startswith("iniciar") else saga
            self.assertEqual(com(corpo=corpo, i=uuid4()), 404, comando)
            if comando != "aceite":
                self.assertEqual(com(corpo=corpo), 409, comando)
        permissao = f"/internal/v1/reservas/{reserva}/permissao-cancelamento"
        self.assertEqual([r("GET", permissao, t, cab=ator) for t in ("orquestrador", "q" * 40)], [200, 401])
        self.assertEqual(decidir({"decisao": "REJEITAR"}), 200)
        self.assertEqual(r("POST", unidade, "profissional", None, {"justificativa": "válida"}), 409)
        self.assertEqual(r("POST", f"/internal/v1/reservas/{reserva}/aceite", "orquestrador", None, saga, ator), 409)
        alvo = f"/internal/v1/reservas/{reserva}"
        self.assertEqual(sem_banco("reservas", "RESERVAS_DATABASE_URL", [
            (("GET", alvo + "/estado", "retiradas"), {}), (("POST", cidadao, "cidadao", "k"), {}),
            (("POST", unidade, "profissional", "k"), {"json": {"justificativa": "válida"}}),
            (("POST", alvo + "/aceite", "orquestrador", "k"), {"json": saga, "cabecalhos": ator}),
            (("GET", permissao, "orquestrador"), {"cabecalhos": ator}),
            *((("POST", f"{alvo}/{c}", "orquestrador", "k"), {"json": saga}) for c in ("confirmar", "falhar-confirmacao", "finalizar-cancelamento")),
            (("POST", alvo + "/iniciar-cancelamento", "orquestrador", "k"), {"json": {**saga, "justificativa": "válida"}, "cabecalhos": ator})]), [503] * 9)

    def test_dependencia_indisponivel_em_reservas_e_503(self):
        reserva, saga = a.criar_reserva(), {"sagaId": str(uuid4())}
        ator = {"X-Ator-Papel": "PROFISSIONAL", "X-Ator-Id": "p", "X-Ator-Unidade-Id": a.UNIDADE}
        a.matar("unidades")
        try:
            self.assertEqual(a.chamar("reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/decisao", "profissional", a.nova_chave(), json={"decisao": "ACEITAR"}).status_code, 503)
            self.assertEqual(a.chamar("reservas", "POST", f"/internal/v1/reservas/{reserva}/aceite", "orquestrador", a.nova_chave(), json=saga, cabecalhos=ator).status_code, 503)
        finally:
            a.subir("unidades")

    def test_retiradas(self):
        corpo, chave = corpo_alocacao(a.ITEM), a.nova_chave()
        preparar = lambda t="orquestrador", k=None, c=corpo: a.chamar("retiradas", "POST", "/internal/v1/autorizacoes", t, k or a.nova_chave(), json=c).status_code
        self.assertEqual([preparar(k=chave), preparar(k=chave), preparar(), preparar("q" * 40), preparar("retiradas")], [201, 201, 409, 401, 403])
        revogar = lambda t="orquestrador", c={"X-Saga-Id": str(uuid4())}: a.chamar("retiradas", "POST", f"/internal/v1/autorizacoes/{uuid4()}/cancelar", t, a.nova_chave(), cabecalhos=c).status_code
        self.assertEqual([revogar(), revogar(c={}), revogar("q" * 40), revogar("profissional")], [404, 400, 401, 403])
        self.assertEqual(sem_banco("retiradas", "RETIRADAS_DATABASE_URL", [
            (("GET", f"/internal/v1/autorizacoes/{uuid4()}", "profissional"), {}),
            (("POST", "/internal/v1/autorizacoes", "orquestrador", "k"), {"json": corpo}),
            (("POST", f"/internal/v1/autorizacoes/{uuid4()}/cancelar", "orquestrador", "k"), {"cabecalhos": {"X-Saga-Id": str(uuid4())}}),
            (("POST", "/api/unidade/v1/retiradas", "profissional", "k"), {"json": {"autorizacaoId": str(uuid4())}})]), [503] * 4)

    def test_orquestrador(self):
        reserva, outra, chave = a.criar_reserva(), str(uuid4()), a.nova_chave()
        o = lambda i, t="profissional", k=None: a.chamar("orquestrador", "POST", f"/internal/v1/reservas/{i}/confirmacoes", t, k or a.nova_chave()).status_code
        self.assertEqual([o(reserva, k=chave), o(reserva, k=chave), o(outra, k=chave), o(outra, "cidadao"), o(outra, "q" * 40)], [202, 202, 409, 403, 401])
        self.assertEqual(a.chamar("orquestrador", "POST", f"/internal/v1/reservas/{reserva}/confirmacoes", "profissional").status_code, 400)
        consulta = lambda t: a.chamar("orquestrador", "GET", f"/internal/v1/sagas/{uuid4()}", t).status_code
        self.assertEqual([consulta("cidadao"), consulta("q" * 40)], [404, 401])
        a.esperar_estado(reserva, "CONFIRMADA")
        self.assertEqual(sem_banco("orquestrador", "ORQUESTRADOR_DATABASE_URL", [
            (("POST", f"/internal/v1/reservas/{reserva}/confirmacoes", "profissional", "k"), {}),
            (("POST", f"/internal/v1/reservas/{reserva}/cancelamentos", "cidadao", "k"), {}),
            (("GET", f"/internal/v1/sagas/{uuid4()}", "cidadao"), {})]), [503] * 3)
