"""API Gateway e BFFs: rotas, identidade, correlação, agregações, HATEOAS, erros e jornadas completas."""
import re
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from tests import ambiente as a


def setUpModule():
    a.preparar()


CID, UNI = "/api/cidadao/v1", "/api/unidade/v1"
JUSTIFICATIVA = {"justificativa": "item avariado"}


def gw(metodo, caminho, token=None, chave=None, **opcoes):
    return a.chamar("gateway", metodo, caminho, token, chave, **opcoes)


def cid(metodo, caminho, **opcoes):
    return gw(metodo, CID + caminho, "cidadao", a.nova_chave() if metodo != "GET" else None, **opcoes)


def uni(metodo, caminho, chave=None, **opcoes):
    return gw(metodo, UNI + caminho, "profissional", chave or (a.nova_chave() if metodo != "GET" else None), **opcoes)


def forcar(reserva, status):
    a.consultar("reservas", "UPDATE reservas SET status = %s WHERE reserva_id = %s", status, reserva)


class Base(unittest.TestCase):
    def setUp(self):
        for proxy in a.proxies.values():
            proxy.limpar()

    tearDown = setUp


class Roteamento(Base):
    def test_so_rotas_publicas_sao_alcancaveis(self):
        reserva = a.criar_reserva()
        for caminho in (f"/internal/v1/reservas/{reserva}", f"/internal/v1/unidades/{a.UNIDADE}", f"/internal/v1/sagas/{uuid4()}",
                        CID + "/estoque/itens", UNI + "/reservas", f"{UNI}/estoque/{a.UNIDADE}/itens", UNI + "/health",
                        CID + "/reservas/..", CID + "/reservas/%2e%2e", CID + "/reservas/..%2f..%2fhealth", CID + "/reservas/x%3fy"):
            for token in ("cidadao", "profissional", "bff-unidade", "orquestrador"):
                self.assertIn(gw("GET", caminho, token).status_code, (401, 404, 405, 422), caminho)
        self.assertEqual(gw("POST", f"/internal/v1/reservas/{reserva}/confirmacoes", "bff-unidade", "k").status_code, 404)
        self.assertEqual(gw("DELETE", f"{CID}/reservas/{reserva}", "cidadao").status_code, 405)
        chamados = [v[1] for p in ("gateway>bff-cidadao", "gateway>bff-unidade") for v in a.proxies[p].vistos]
        self.assertTrue(all(c.startswith((CID, UNI)) and ".." not in c for c in chamados), chamados)

    def test_preserva_query_corpo_e_metodos(self):
        a.proxies["gateway>bff-cidadao"].limpar()
        gw("GET", f"{CID}/explorar?itemId={a.ITEM}&x=1%262&x=b")
        self.assertIn(f"/explorar?itemId={a.ITEM}&x=1%262&x=b", a.proxies["gateway>bff-cidadao"].vistos[0][1])
        for metodo, caminho, corpo in (("PATCH", "/unidade/status", {"ativa": True}), ("PUT", "/unidade/prazo-analise", {"prazoAnaliseHoras": 30})):
            self.assertEqual(uni(metodo, caminho, json=corpo).status_code, 200)
        self.assertEqual(uni("GET", "/unidade").json()["prazoAnaliseHoras"], 30)
        uni("PUT", "/unidade/prazo-analise", json={"prazoAnaliseHoras": 24})


class IdentidadeECorrelacao(Base):
    def test_cabecalhos_na_borda_e_nos_servicos(self):
        forjados = {"X-Ator-Papel": "PROFISSIONAL", "X-Ator-Id": "invasor", "X-Ator-Unidade-Id": str(uuid4()), "X-Saga-Id": "x", "Cookie": "c=1", "X-Forwarded-For": "1"}
        correlacao, chave = str(uuid4()), a.nova_chave()
        pedido = {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}
        r = gw("POST", CID + "/reservas", "cidadao", chave, json=pedido, cabecalhos={**forjados, "X-Correlation-Id": correlacao})
        self.assertEqual((r.status_code, r.headers["x-correlation-id"]), (201, correlacao))
        no_bff = a.proxies["gateway>bff-cidadao"].vistos[-1][3]
        self.assertEqual((no_bff["x-correlation-id"], no_bff["idempotency-key"]), (correlacao, chave))
        for nome in forjados:
            self.assertNotIn(nome.lower(), no_bff)
        no_servico = a.proxies["bff>reservas"].vistos[-1][3]
        self.assertEqual(no_servico["authorization"], "Bearer " + a.TOKENS["bff-cidadao"])
        self.assertEqual((no_servico["x-ator-papel"], no_servico["x-ator-id"], no_servico["x-correlation-id"], no_servico["idempotency-key"]),
                         ("CIDADAO", "cidadao-demo", correlacao, chave))
        self.assertNotIn("x-ator-unidade-id", no_servico)

        uni("GET", "/painel/reservas/" + r.json()["reservaId"])
        for servico in ("reservas", "retiradas", "unidades"):
            visto = a.proxies[f"bff>{servico}"].vistos[-1][3]
            self.assertEqual((visto["authorization"], visto["x-ator-papel"], visto["x-ator-unidade-id"]),
                             ("Bearer " + a.TOKENS["bff-unidade"], "PROFISSIONAL", a.UNIDADE))
        # O token do usuário nunca sai dos BFFs.
        for nome, proxy in a.proxies.items():
            if nome.startswith("bff>"):
                for visto in proxy.vistos:
                    self.assertNotIn(visto[3].get("authorization", ""), ("Bearer " + a.TOKENS["cidadao"], "Bearer " + a.TOKENS["profissional"]))

    def test_correlacao_gerada_ou_substituida(self):
        for enviado in (None, "invalido", "a" * 500):
            for porta in ("gateway", "bff-cidadao"):
                r = a.chamar(porta, "GET", CID + "/itens", cabecalhos={"X-Correlation-Id": enviado} if enviado else {})
                self.assertEqual(str(UUID(r.headers["x-correlation-id"])), r.headers["x-correlation-id"])
                self.assertEqual(a.proxies["bff>estoque"].vistos[-1][3]["x-correlation-id"], r.headers["x-correlation-id"])
        self.assertIn("x-correlation-id", gw("GET", "/nao-existe").headers)
        self.assertIn("x-correlation-id", gw("GET", UNI + "/unidade").headers)

    def test_correlacao_chega_a_saga_e_ao_evento(self):
        item, aceite, cancelamento, entrega = a.item_com_saldo(5), str(uuid4()), str(uuid4()), str(uuid4())
        reservas = [a.criar_reserva(1, item) for _ in range(2)]
        for reserva in reservas:
            uni("POST", f"/reservas/{reserva}/decisao", json={"decisao": "ACEITAR"}, cabecalhos={"X-Correlation-Id": aceite})
            a.esperar_estado(reserva, "CONFIRMADA")
            self.assertEqual(str(a.saga_do_tipo(reserva, "CONFIRMACAO")["correlation_id"]), aceite)
            self.assertEqual(str(a.alocacao(reserva)["correlation_id"]), aceite)
        cid("POST", f"/reservas/{reservas[0]}/cancelar", cabecalhos={"X-Correlation-Id": cancelamento})
        a.esperar_estado(reservas[0], "CANCELADA")
        self.assertEqual(str(a.saga_do_tipo(reservas[0], "CANCELAMENTO")["correlation_id"]), cancelamento)
        autorizacao = uni("GET", f"/painel/reservas/{reservas[1]}").json()["dadosAutorizacao"]["autorizacaoId"]
        uni("POST", "/retiradas", json={"autorizacaoId": autorizacao}, cabecalhos={"X-Correlation-Id": entrega})
        for servico in ("retiradas", "estoque"):
            evento = a.esperar(lambda: a.consultar(servico, "SELECT correlation_id FROM outbox WHERE payload->>'reservaId' = %s AND payload ? 'retiradaId'", reservas[1]))
            self.assertEqual(str(evento[0]["correlation_id"]), entrega)

    def test_autorizacao_por_publico(self):
        reserva = a.criar_reserva()
        for metodo, caminho, errado in (("GET", f"{CID}/reservas/{reserva}", "profissional"), ("POST", f"{CID}/reservas/{reserva}/cancelar", "profissional"),
                                        ("GET", UNI + "/unidade", "cidadao"), ("PATCH", UNI + "/unidade/status", "cidadao"), ("POST", UNI + "/retiradas", "cidadao")):
            respostas = [gw(metodo, caminho, t, a.nova_chave(), json=None if metodo == "GET" else {}).status_code for t in (None, "z" * 40, "bff-unidade", errado)]
            self.assertEqual(respostas, [401, 401, 401, 403], caminho)
        self.assertEqual(gw("GET", UNI + "/unidade", cabecalhos={"Authorization": "Basic abc"}).headers["www-authenticate"], "Bearer")


class Agregacao(Base):
    def test_detalhe_do_cidadao(self):
        reserva = a.criar_reserva()
        r = cid("GET", f"/reservas/{reserva}")
        dados, unidade = r.json(), next(u for u in gw("GET", CID + "/unidades").json() if u["unidadeId"] == a.UNIDADE)
        self.assertEqual((dados["itemNome"], dados["unidadeNome"], dados["enderecoLocal"], dados["orientacoesRetirada"]),
                         ("Tiras reagentes para glicemia", unidade["nome"], unidade["endereco"], unidade["orientacoesRetirada"]))
        self.assertEqual(r.headers["cache-control"], "no-store")
        for sensivel in ("cidadaoId", "dadosAutorizacao", "estoqueFisicoAtual", "contatos", "prazoAnaliseHoras"):
            self.assertNotIn(sensivel, dados)

    def test_unidade_inativa(self):
        reserva, solicitada = a.confirmada(1, a.item_com_saldo(3)), a.criar_reserva()
        self.assertEqual(uni("PATCH", "/unidade/status", json={"ativa": False}).json()["ativa"], False)
        try:
            self.assertNotIn(a.UNIDADE, [u["unidadeId"] for u in gw("GET", CID + "/unidades").json()])
            self.assertTrue(cid("GET", f"/reservas/{reserva}").json()["enderecoLocal"])
            self.assertEqual(set(uni("GET", f"/painel/reservas/{solicitada}").json()["_links"]), {"self", "rejeitar", "cancelar"})
            self.assertIn("autorizacao-retirada", uni("GET", f"/painel/reservas/{reserva}").json()["_links"])
            na_lista = next(x for x in uni("GET", "/painel/reservas").json() if x["reservaId"] == solicitada)
            self.assertNotIn("aceitar", na_lista["_links"])
            aceite = uni("POST", f"/reservas/{solicitada}/decisao", json={"decisao": "ACEITAR"})
            self.assertEqual(aceite.status_code, 403)
        finally:
            self.assertEqual(uni("PATCH", "/unidade/status", json={"ativa": True}).status_code, 200)

    def test_reserva_alheia_nao_consulta_complementos(self):
        reserva = a.criar_reserva()
        a.consultar("reservas", "UPDATE reservas SET cidadao_id = 'outro', unidade_id = %s WHERE reserva_id = %s", str(uuid4()), reserva)
        self.assertEqual(cid("GET", f"/reservas/{reserva}").status_code, 404)
        self.assertEqual(uni("GET", f"/painel/reservas/{reserva}").status_code, 403)
        for servico in ("unidades", "estoque", "retiradas"):
            self.assertEqual(a.proxies[f"bff>{servico}"].vistos, [])

    def test_detalhe_da_unidade(self):
        item = a.item_com_saldo(7)
        a.esperar(lambda: a.consultar("estoque", "SELECT 1 FROM disponibilidade WHERE item_id = %s AND estoque_fisico_atual = 7", item))
        reserva = a.confirmada(2, item)
        dados = uni("GET", f"/painel/reservas/{reserva}").json()
        autorizacao = a.autorizacao(reserva).json()
        self.assertEqual(dados["dadosAutorizacao"], {"autorizacaoId": autorizacao["autorizacaoId"], "status": "ATIVA"})
        self.assertEqual((dados["estoqueFisicoAtual"], dados["cidadaoId"]), (7, "cidadao-demo"))
        self.assertTrue(dados["itemNome"] and dados["orientacoesRetirada"])
        self.assertNotIn("dadosAutorizacao", uni("GET", f"/painel/reservas/{a.criar_reserva()}").json())

    def test_complemento_indisponivel_e_omitido_e_principal_e_503(self):
        reserva = a.criar_reserva()
        for servico, campos in (("unidades", ("unidadeNome", "enderecoLocal")), ("estoque", ("itemNome",))):
            a.proxies[f"bff>{servico}"].recusar["/"] = 1
            dados = cid("GET", f"/reservas/{reserva}")
            self.assertEqual((dados.status_code, [c for c in campos if c in dados.json()]), (200, []))
        a.proxies["bff>retiradas"].recusar["/"] = 1
        self.assertEqual(uni("GET", f"/painel/reservas/{reserva}").status_code, 200)
        confirmada = a.confirmada(1, a.item_com_saldo(2))
        a.proxies["bff>retiradas"].recusar["/"] = 1
        self.assertEqual(uni("GET", f"/painel/reservas/{confirmada}").status_code, 503)
        a.proxies["bff>reservas"].recusar["/"] = 2
        self.assertEqual([cid("GET", f"/reservas/{reserva}").status_code, uni("GET", f"/painel/reservas/{reserva}").status_code], [503, 503])
        a.proxies["bff>estoque"].recusar["/disponibilidade"] = 1
        self.assertEqual(gw("GET", f"{CID}/explorar?itemId={a.ITEM}").status_code, 503)
        self.assertEqual(gw("GET", f"{CID}/explorar?itemId={uuid4()}").json(), [])


class Hateoas(Base):
    CIDADAO = {"SOLICITADA": {"cancelar"}, "EM_CONFIRMACAO": {"cancelar"}, "CONFIRMADA": {"cancelar"}}
    UNIDADE = {"SOLICITADA": {"aceitar", "rejeitar", "cancelar"}, "EM_CONFIRMACAO": {"cancelar"}, "CONFIRMADA": {"cancelar", "autorizacao-retirada"}}
    TODOS = ("SOLICITADA", "EM_CONFIRMACAO", "CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO", "CANCELADA", "REJEITADA", "EXPIRADA", "FALHA_CONFIRMACAO", "RETIRADA")

    def test_links_por_estado_e_ator(self):
        reserva = a.criar_reserva()
        autorizacao = a.chamar("retiradas", "POST", "/internal/v1/autorizacoes", "orquestrador", a.nova_chave(), json={
            "sagaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}).json()["autorizacaoId"]
        for status in self.TODOS:
            with self.subTest(status):
                forcar(reserva, status)
                links = cid("GET", f"/reservas/{reserva}").json()["_links"]
                self.assertEqual(set(links), {"self"} | self.CIDADAO.get(status, set()))
                if "cancelar" in links:
                    self.assertEqual(links["cancelar"], {"href": f"{CID}/reservas/{reserva}/cancelar", "method": "POST"})
                links = uni("GET", f"/painel/reservas/{reserva}").json()["_links"]
                self.assertEqual(set(links), {"self"} | self.UNIDADE.get(status, set()))
                self.assertEqual(links["self"], {"href": f"{UNI}/painel/reservas/{reserva}", "method": "GET"})
                if status == "CONFIRMADA":
                    self.assertEqual(links["autorizacao-retirada"], {"href": UNI + "/retiradas", "method": "POST", "body": {"autorizacaoId": autorizacao}})
        forcar(reserva, "CONFIRMADA")
        a.chamar("retiradas", "POST", f"/internal/v1/autorizacoes/{reserva}/cancelar", "orquestrador", a.nova_chave(), cabecalhos={"X-Saga-Id": str(uuid4())})
        dados = uni("GET", f"/painel/reservas/{reserva}").json()
        self.assertEqual((dados["dadosAutorizacao"]["status"], set(dados["_links"])), ("CANCELADA", {"self", "cancelar"}))

    def test_links_sao_executaveis(self):
        def seguir(link, token):
            return gw(link["method"], link["href"], token, a.nova_chave(), json=link.get("body"))
        reserva = a.criar_reserva(1, a.item_com_saldo(5))
        item = next(x for x in uni("GET", "/painel/reservas").json() if x["reservaId"] == reserva)
        self.assertEqual(seguir(item["_links"]["aceitar"], "profissional").status_code, 202)
        a.esperar_estado(reserva, "CONFIRMADA")
        detalhe = seguir(item["_links"]["self"], "profissional").json()
        self.assertEqual(seguir(detalhe["_links"]["autorizacao-retirada"], "profissional").status_code, 201)
        a.esperar_estado(reserva, "RETIRADA")
        criada = cid("POST", "/reservas", json={"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1})
        self.assertEqual(criada.headers["location"], criada.json()["_links"]["self"]["href"])
        self.assertEqual(seguir(criada.json()["_links"]["cancelar"], "cidadao").status_code, 200)
        outra = a.criar_reserva()
        links = uni("GET", f"/painel/reservas/{outra}").json()["_links"]
        self.assertEqual(seguir(links["cancelar"], "profissional").status_code, 200)


class Erros(Base):
    def test_400_e_422_sao_propagados(self):
        reserva = a.criar_reserva()
        for corpo in ({}, {"justificativa": " a "}, {**JUSTIFICATIVA, "extra": 1}):
            r = uni("POST", f"/reservas/{reserva}/cancelar", json=corpo)
            self.assertEqual((r.status_code, r.json()["codigo"]), (400, "ENTRADA_INVALIDA"))
        self.assertEqual(gw("POST", f"{UNI}/reservas/{reserva}/cancelar", "profissional", a.nova_chave(), content=b"{").status_code, 400)
        forcar(reserva, "CONFIRMADA")  # O mesmo vale quando o pedido seria distribuído.
        self.assertEqual(uni("POST", f"/reservas/{reserva}/cancelar", json={"justificativa": "x"}).status_code, 400)
        for corpo in ({}, {"decisao": "TALVEZ"}, {"decisao": "REJEITAR", "extra": 1}):
            self.assertEqual(uni("POST", f"/reservas/{reserva}/decisao", json=corpo).status_code, 400)
        for porta, caminho in (("gateway", f"{CID}/reservas/x/cancelar"), ("bff-cidadao", f"{CID}/reservas/x/cancelar")):
            self.assertEqual(a.chamar(porta, "POST", caminho, "cidadao", "k").status_code, 400)
        self.assertEqual(gw("POST", f"{CID}/reservas/{reserva}/cancelar", "cidadao").status_code, 400)
        base = f"/painel/estoque/{a.UNIDADE}/itens/{a.ITEM}"
        for metodo, caminho, corpo in (("PUT", "/unidade", {}), ("PUT", "/unidade/horarios", {"horarios": [{"diaSemana": 1, "horarioInicial": "12:00:00", "horarioFinal": "08:00:00"}]}),
                                       ("PUT", "/unidade/prazo-analise", {"prazoAnaliseHoras": 721}), ("PATCH", "/unidade/status", {"ativa": True, "extra": 1}),
                                       ("PUT", base + "/permissao", {"permiteReserva": 1}), ("POST", base + "/entradas", {"quantidade": 0, "motivo": "m"}),
                                       ("POST", base + "/ajustes", {"variacaoFisica": 0, "motivo": "m"}), ("POST", "/retiradas", {"autorizacaoId": "x"})):
            self.assertEqual(uni(metodo, caminho, json=corpo).status_code, 422, caminho)
            self.assertEqual(gw(metodo, UNI + caminho, "profissional", json=corpo).status_code, 422)  # Sem chave.
        self.assertEqual(cid("POST", "/reservas", json={"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1, "cidadaoId": "outro"}).status_code, 422)
        self.assertEqual(cid("GET", "/reservas/x").status_code, 422)

    def test_503_para_falhas_tecnicas_e_credencial_do_bff(self):
        reserva = a.criar_reserva()
        a.proxies["bff>reservas"].recusar["/cancelar"] = 1
        r = cid("POST", f"/reservas/{reserva}/cancelar")
        self.assertEqual((r.status_code, a.proxies["bff>orquestrador"].vistos), (503, []))
        a.proxies["gateway>bff-cidadao"].perder["/itens"] = 1
        self.assertEqual(gw("GET", CID + "/itens").status_code, 503)
        a.matar("bff-cidadao")
        try:
            self.assertEqual(a.cliente.get(f"http://127.0.0.1:{a.portas['gateway']}{CID}/itens").status_code, 503)
        finally:
            a.subir("bff-cidadao")
        a.matar("bff-cidadao")
        a.subir("bff-cidadao", GLICO_BFF_CIDADAO_TOKEN="desatualizada".ljust(40, "x"))
        try:
            for r in (cid("GET", f"/reservas/{reserva}"), cid("POST", f"/reservas/{reserva}/cancelar")):
                self.assertEqual(r.status_code, 503)
                self.assertNotIn("www-authenticate", r.headers)
        finally:
            a.matar("bff-cidadao")
            a.subir("bff-cidadao")

    def test_tempo_esgotado_e_retry_com_a_mesma_chave(self):
        reserva, chave = a.criar_reserva(), a.nova_chave()
        proxy = a.proxies["bff>reservas"]
        proxy.portoes["/cancelar"] = portao = threading.Event()
        r = gw("POST", f"{CID}/reservas/{reserva}/cancelar", "cidadao", chave)
        portao.set()
        proxy.portoes.clear()
        self.assertEqual((r.status_code, a.estado(reserva)), (503, "CANCELADA"))
        r = gw("POST", f"{CID}/reservas/{reserva}/cancelar", "cidadao", chave)
        self.assertEqual((r.status_code, r.json()["status"]), (200, "CANCELADA"))

    def test_resposta_perdida_do_orquestrador_recupera_o_mesmo_pedido(self):
        item = a.item_com_saldo(5)
        reserva, chave = a.criar_reserva(1, item), a.nova_chave()
        a.proxies["bff>orquestrador"].perder["/confirmacoes"] = 1
        self.assertEqual(a.aceitar(reserva, chave).status_code, 503)
        a.esperar_estado(reserva, "CONFIRMADA")
        self.assertEqual(a.aceitar(reserva, chave).status_code, 202)
        self.assertEqual(len(a.sagas(reserva)), 1)
        chave = a.nova_chave()
        a.proxies["bff>orquestrador"].perder["/cancelamentos"] = 1
        cancelar = lambda: gw("POST", f"{UNI}/reservas/{reserva}/cancelar", "profissional", chave, json=JUSTIFICATIVA)
        self.assertEqual(cancelar().status_code, 503)
        a.esperar_estado(reserva, "CANCELADA")
        self.assertEqual(cancelar().status_code, 202)
        self.assertEqual(len(a.sagas(reserva)), 2)

    def test_outros_conflitos_nao_sao_redirecionados(self):
        reserva = a.criar_reserva()
        for status, codigo in (("CANCELAMENTO_EM_ANDAMENTO", "CANCELAMENTO_EM_ANDAMENTO"), ("RETIRADA", "ESTADO_INCOMPATIVEL"), ("EXPIRADA", "ESTADO_INCOMPATIVEL")):
            forcar(reserva, status)
            for r in (cid("POST", f"/reservas/{reserva}/cancelar"), uni("POST", f"/reservas/{reserva}/cancelar", json=JUSTIFICATIVA)):
                self.assertEqual((r.status_code, r.json()["codigo"]), (409, codigo))
            r = uni("POST", f"/reservas/{reserva}/decisao", json={"decisao": "ACEITAR"})
            self.assertEqual((r.status_code, r.json()["codigo"]), (409, "ESTADO_INCOMPATIVEL"))
        self.assertEqual(a.proxies["bff>orquestrador"].vistos, [])

    def test_estado_incompativel_nao_se_aplica_a_confirmacoes(self):
        reserva = a.criar_reserva()
        for status in Hateoas.TODOS[1:]:
            forcar(reserva, status)
            r = a.chamar("orquestrador", "POST", f"/internal/v1/reservas/{reserva}/confirmacoes", "profissional", a.nova_chave())
            self.assertEqual(r.status_code, 202, status)
            a.esperar(lambda: not a.sagas(reserva, "encerrada_em IS NULL"))
            self.assertEqual((a.sagas(reserva)[-1]["estado"], a.estado(reserva)), ("INTERROMPIDA", status))


class Jornadas(Base):
    def test_consulta_reserva_confirmacao_e_retirada(self):
        item = a.item_com_saldo(4)
        explorar = lambda: next((u for u in gw("GET", f"{CID}/explorar?itemId={item}").json() if u["unidadeId"] == a.UNIDADE), None)
        visto = a.esperar(lambda: (u := explorar()) and u["disponivel"] and u)
        self.assertTrue(visto["permiteReserva"])
        self.assertIn(item, [i["itemId"] for i in gw("GET", CID + "/itens").json()])
        chave, pedido = a.nova_chave(), {"unidadeId": a.UNIDADE, "itemId": item, "quantidade": 4}
        respostas = [gw("POST", CID + "/reservas", "cidadao", chave, json=pedido) for _ in range(2)]
        self.assertEqual([r.status_code for r in respostas], [201, 201])
        self.assertEqual(respostas[0].json(), respostas[1].json())
        reserva = respostas[0].json()["reservaId"]
        self.assertIn(reserva, [r["reservaId"] for r in uni("GET", "/painel/reservas").json()])
        decisao = uni("POST", f"/reservas/{reserva}/decisao", json={"decisao": "ACEITAR"})
        self.assertEqual((decisao.status_code, decisao.json(), decisao.headers["location"]),
                         (202, {"reservaId": reserva}, f"{UNI}/painel/reservas/{reserva}"))
        a.esperar(lambda: gw("GET", decisao.headers["location"], "profissional").json()["status"] == "CONFIRMADA")
        a.esperar(lambda: explorar()["disponivel"] is False)
        autorizacao = uni("GET", f"/painel/reservas/{reserva}").json()["dadosAutorizacao"]["autorizacaoId"]
        chave = a.nova_chave()
        entregas = [gw("POST", UNI + "/retiradas", "profissional", chave, json={"autorizacaoId": autorizacao}) for _ in range(2)]
        self.assertEqual([r.status_code for r in entregas], [201, 201])
        self.assertEqual(entregas[0].json(), entregas[1].json())
        a.esperar(lambda: cid("GET", f"/reservas/{reserva}").json()["status"] == "RETIRADA")
        linha = lambda: next(i for i in uni("GET", "/painel/estoque").json() if i["itemId"] == item)
        a.esperar(lambda: (linha()["estoqueFisicoAtual"], linha()["quantidadeAlocada"], linha()["quantidadeDisponivel"]) == (0, 0, 0))
        self.assertEqual(uni("POST", "/retiradas", json={"autorizacaoId": autorizacao}).status_code, 409)
        self.assertEqual(cid("POST", f"/reservas/{reserva}/cancelar").status_code, 409)

    def test_rejeicao(self):
        reserva, chave = a.criar_reserva(), a.nova_chave()
        rejeitar = lambda d="REJEITAR": uni("POST", f"/reservas/{reserva}/decisao", chave, json={"decisao": d})
        self.assertEqual([rejeitar().status_code, rejeitar().status_code], [200, 200])
        self.assertEqual(rejeitar("ACEITAR").json()["codigo"], "CHAVE_IDEMPOTENTE_CONFLITANTE")
        self.assertEqual(cid("GET", f"/reservas/{reserva}").json()["status"], "REJEITADA")

    def test_cancelamentos_local_e_distribuido(self):
        item = a.item_com_saldo(10)
        for ator in ("cidadao", "unidade"):
            cancelar = (lambda r: cid("POST", f"/reservas/{r}/cancelar")) if ator == "cidadao" else (lambda r: uni("POST", f"/reservas/{r}/cancelar", json=JUSTIFICATIVA))
            acompanhar = f"{CID}/reservas/" if ator == "cidadao" else f"{UNI}/painel/reservas/"
            local = a.criar_reserva(1, item)
            r = cancelar(local)
            self.assertEqual((r.status_code, r.json()), (200, {"reservaId": local, "status": "CANCELADA"}))
            distribuida = a.confirmada(2, item)
            r = cancelar(distribuida)
            self.assertEqual((r.status_code, r.json(), r.headers["location"]), (202, {"reservaId": distribuida}, acompanhar + distribuida))
            token = "cidadao" if ator == "cidadao" else "profissional"
            a.esperar(lambda: gw("GET", r.headers["location"], token).json()["status"] == "CANCELADA")
            self.assertEqual(a.saldo(item), (10, 0))
        historico = a.consultar("reservas", "SELECT justificativa FROM historico_reserva WHERE reserva_id = %s AND justificativa IS NOT NULL", distribuida)
        self.assertEqual(historico[0]["justificativa"], "item avariado")

    def test_falha_de_confirmacao(self):
        reserva = a.criar_reserva(99, a.item_com_saldo(1))
        self.assertEqual(a.aceitar(reserva).status_code, 202)
        a.esperar(lambda: cid("GET", f"/reservas/{reserva}").json()["status"] == "FALHA_CONFIRMACAO")

    def test_disputa_entre_retirada_e_cancelamento(self):
        item = a.item_com_saldo(10)
        for _ in range(4):
            reserva = a.confirmada(1, item)
            autorizacao = uni("GET", f"/painel/reservas/{reserva}").json()["dadosAutorizacao"]["autorizacaoId"]
            with ThreadPoolExecutor(2) as pool:
                entrega = pool.submit(uni, "POST", "/retiradas", json={"autorizacaoId": autorizacao})
                pool.submit(cid, "POST", f"/reservas/{reserva}/cancelar")
            final = a.esperar_estado(reserva, "RETIRADA", "CANCELADA")
            self.assertEqual(final == "RETIRADA", entrega.result().status_code == 201)

    def test_administracao_da_unidade(self):
        original = uni("GET", "/unidade").json()
        cadastro = {"nome": original["nome"], "logradouro": "Rua Exemplo", "numero": "100", "bairro": "Centro", "cidade": "Cidade Exemplo", "estado": "MG",
                    "cep": "00000-000", "orientacoesRetirada": "Leve documento.", "contatos": [{"tipo": "telefone", "valor": "35 1"}],
                    "horarios": [{"diaSemana": 1, "horarioInicial": "08:00:00", "horarioFinal": "12:00:00"}], "prazoAnaliseHoras": 48}
        chave = a.nova_chave()
        respostas = [uni("PUT", "/unidade", chave, json=cadastro) for _ in range(2)]
        self.assertEqual([r.status_code for r in respostas], [200, 200])
        self.assertEqual(respostas[0].json(), uni("GET", "/unidade").json())
        self.assertEqual(uni("PUT", "/unidade", chave, json={**cadastro, "nome": "X"}).status_code, 409)
        horarios = [{"diaSemana": 2, "horarioInicial": "08:00:00", "horarioFinal": "12:00:00"}, {"diaSemana": 2, "horarioInicial": "12:00:00", "horarioFinal": "17:00:00"}]
        self.assertEqual(uni("PUT", "/unidade/horarios", json={"horarios": horarios}).json()["horarios"], horarios)
        self.assertEqual(uni("PUT", "/unidade/prazo-analise", json={"prazoAnaliseHoras": 24}).json()["prazoAnaliseHoras"], 24)
        publica = next(u for u in gw("GET", CID + "/unidades").json() if u["unidadeId"] == a.UNIDADE)
        self.assertEqual((publica["orientacoesRetirada"], publica["horarioAtendimento"]), ("Leve documento.", "Ter 08:00–12:00; Ter 12:00–17:00"))

        item = a.chamar("estoque", "POST", "/internal/v1/itens", "admin", a.nova_chave(), json={"nome": f"Adm {uuid4()}", "tipo": "INSUMO"}).json()["itemId"]
        base = f"/painel/estoque/{a.UNIDADE}/itens/{item}"
        self.assertEqual(uni("PUT", base + "/permissao", json={"permiteReserva": True}).json()["permiteReserva"], True)
        chave = a.nova_chave()
        entradas = [uni("POST", base + "/entradas", chave, json={"quantidade": 5, "motivo": "compra"}) for _ in range(2)]
        self.assertEqual([r.status_code for r in entradas], [201, 201])
        self.assertEqual(entradas[0].json(), entradas[1].json())
        a.confirmada(4, item)
        r = uni("POST", base + "/ajustes", json={"variacaoFisica": -2, "motivo": "perda"})
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "AJUSTE_INCOMPATIVEL"))
        self.assertEqual(uni("POST", base + "/ajustes", json={"variacaoFisica": -1, "motivo": "perda"}).status_code, 201)
        self.assertEqual(a.saldo(item), (4, 4))
        alheia = f"/painel/estoque/{uuid4()}/itens/{item}"
        for metodo, sufixo, corpo in (("PUT", "/permissao", {"permiteReserva": True}), ("POST", "/entradas", {"quantidade": 1, "motivo": "m"}), ("POST", "/ajustes", {"variacaoFisica": 1, "motivo": "m"})):
            self.assertEqual(uni(metodo, alheia + sufixo, json=corpo).status_code, 403)


class RespostasDocumentadas(Base):
    """Exercita em ambas as portas as respostas declaradas; `tests.contratos` valida o que foi gravado."""

    OPERACOES = [(CID, m, c) for m, c in (("POST", "/reservas"), ("GET", "/reservas/{r}"), ("POST", "/reservas/{r}/cancelar"))] + [(UNI, m, c) for m, c in (
        ("GET", "/unidade"), ("PUT", "/unidade"), ("PUT", "/unidade/horarios"), ("PATCH", "/unidade/status"), ("PUT", "/unidade/prazo-analise"),
        ("GET", "/painel/estoque"), ("GET", "/painel/reservas"), ("GET", "/painel/reservas/{r}"), ("PUT", "/painel/estoque/{u}/itens/{i}/permissao"),
        ("POST", "/painel/estoque/{u}/itens/{i}/entradas"), ("POST", "/painel/estoque/{u}/itens/{i}/ajustes"),
        ("POST", "/reservas/{r}/decisao"), ("POST", "/reservas/{r}/cancelar"), ("POST", "/retiradas"))]
    CORPOS = {"/reservas": {"unidadeId": a.UNIDADE, "itemId": a.ITEM, "quantidade": 1}, "/unidade/horarios": {"horarios": []}, "/unidade/status": {"ativa": True},
              "/unidade/prazo-analise": {"prazoAnaliseHoras": 24}, "/permissao": {"permiteReserva": True}, "/entradas": {"quantidade": 1, "motivo": "m"},
              "/ajustes": {"variacaoFisica": 1, "motivo": "m"}, "/decisao": {"decisao": "REJEITAR"}, "/cancelar": JUSTIFICATIVA,
              "/retiradas": {"autorizacaoId": str(uuid4())},
              "/unidade": {"nome": "Unidade de Demonstração", "logradouro": "Rua Exemplo", "numero": "100", "bairro": "Centro", "cidade": "Cidade Exemplo", "estado": "MG",
                           "cep": "00000-000", "orientacoesRetirada": "O", "contatos": [], "horarios": [], "prazoAnaliseHoras": 24}}

    def executar(self, porta, prefixo, metodo, modelo, token, chave=None, reserva=None, unidade=a.UNIDADE, corpo=None):
        caminho = modelo.format(r=reserva or uuid4(), u=unidade, i=uuid4() if reserva is None else a.ITEM)
        if metodo != "GET":
            padrao = None if (prefixo, modelo) == (CID, "/reservas/{r}/cancelar") else next(v for s, v in self.CORPOS.items() if modelo.endswith(s))
            return a.chamar(porta, metodo, prefixo + caminho, token, chave or a.nova_chave(), json=corpo if corpo is not None else padrao)
        return a.chamar(porta, metodo, prefixo + caminho, token)

    def dono(self, prefixo):
        return ("cidadao", "profissional", "bff-cidadao") if prefixo == CID else ("profissional", "cidadao", "bff-unidade")

    def test_credencial_publico_e_indisponibilidade(self):
        for prefixo, metodo, modelo in self.OPERACOES:
            certo, errado, bff = self.dono(prefixo)
            for porta in ("gateway", bff):
                with self.subTest(f"{porta} {metodo} {prefixo}{modelo}"):
                    codigos = [self.executar(porta, prefixo, metodo, modelo, t).status_code for t in (None, "z" * 40, errado)]
                    self.assertEqual(codigos, [401, 401, 403])
                    for nome in a.DOMINIO:
                        a.proxies[f"bff>{nome}"].recusar["/"] = 50
                    self.assertEqual(self.executar(porta, prefixo, metodo, modelo, certo).status_code, 503)
                    for proxy in a.proxies.values():
                        proxy.limpar()
        for porta in ("gateway", "bff-cidadao"):
            for caminho in ("/itens", "/unidades", f"/explorar?itemId={a.ITEM}"):
                self.assertEqual(a.chamar(porta, "GET", CID + caminho).status_code, 200)
                for nome in ("unidades", "estoque"):
                    a.proxies[f"bff>{nome}"].recusar["/"] = 50
                self.assertEqual(a.chamar(porta, "GET", CID + caminho).status_code, 503)
                for proxy in a.proxies.values():
                    proxy.limpar()
            self.assertEqual(a.chamar(porta, "GET", CID + "/explorar").status_code, 422)

    def test_inexistentes_conflitos_e_entradas(self):
        for prefixo, metodo, modelo in self.OPERACOES:
            certo, _, bff = self.dono(prefixo)
            for porta in ("gateway", bff):
                with self.subTest(f"{porta} {metodo} {prefixo}{modelo}"):
                    if "{r}" in modelo or ("{i}" in modelo):
                        self.assertEqual(self.executar(porta, prefixo, metodo, modelo, certo).status_code, 404)
                        invalido = prefixo + re.sub(r"\{\w\}", "x", modelo)
                        r = a.chamar(porta, metodo, invalido, certo, "k", json=None if metodo == "GET" else {})
                        self.assertIn(r.status_code, (400, 422))
                    if metodo != "GET" and (prefixo, modelo) != (CID, "/reservas/{r}/cancelar"):
                        r = self.executar(porta, prefixo, metodo, modelo, certo, reserva=a.criar_reserva(), corpo={})
                        self.assertIn(r.status_code, (400, 422))
                    if metodo != "GET" and "{r}" not in modelo and modelo != "/retiradas":
                        chave = a.nova_chave()
                        primeiro = self.executar(porta, prefixo, metodo, modelo, certo, chave, reserva="-")
                        self.assertIn(primeiro.status_code, (200, 201), primeiro.text)
                        outro = {**next(v for s, v in self.CORPOS.items() if modelo.endswith(s))}
                        campo = next(iter(outro))
                        outro[campo] = {"unidadeId": a.UNIDADE, "nome": "Outro", "horarios": [{"diaSemana": 4, "horarioInicial": "08:00:00", "horarioFinal": "09:00:00"}],
                                        "ativa": False, "prazoAnaliseHoras": 25, "permiteReserva": False, "quantidade": 2, "variacaoFisica": 2}[campo]
                        if modelo == "/reservas":
                            outro["quantidade"] = 2
                        self.assertEqual(self.executar(porta, prefixo, metodo, modelo, certo, chave, reserva="-", corpo=outro).status_code, 409)
        for porta in ("gateway", "bff-cidadao"):
            r = a.chamar(porta, "POST", CID + "/reservas", "cidadao", a.nova_chave(), json={"unidadeId": str(uuid4()), "itemId": a.ITEM, "quantidade": 1})
            self.assertEqual(r.status_code, 422)
            reserva = a.criar_reserva()
            self.assertEqual([a.chamar(porta, "POST", f"{CID}/reservas/{reserva}/cancelar", "cidadao", a.nova_chave()).status_code for _ in range(2)], [200, 409])

    def test_caminhos_de_sucesso_direto_no_bff(self):
        item = a.item_com_saldo(10)
        for porta in ("bff-unidade", "gateway"):
            b = lambda m, c, corpo=None: a.chamar(porta, m, UNI + c, "profissional", a.nova_chave(), json=corpo)
            reserva = a.criar_reserva(1, item)
            self.assertEqual(b("GET", "/painel/estoque").status_code, 200)
            self.assertEqual(b("GET", "/painel/reservas").status_code, 200)
            self.assertEqual(b("GET", "/unidade").status_code, 200)
            self.assertEqual(b("GET", f"/painel/reservas/{reserva}").status_code, 200)
            self.assertEqual(b("POST", f"/reservas/{reserva}/decisao", {"decisao": "ACEITAR"}).status_code, 202)
            a.esperar_estado(reserva, "CONFIRMADA")
            self.assertEqual(b("POST", f"/reservas/{reserva}/decisao", {"decisao": "ACEITAR"}).status_code, 409)
            outra = a.confirmada(1, item)
            self.assertEqual(b("POST", f"/reservas/{outra}/cancelar", JUSTIFICATIVA).status_code, 202)
            a.esperar_estado(outra, "CANCELADA")
            self.assertEqual(b("POST", f"/reservas/{outra}/cancelar", JUSTIFICATIVA).status_code, 409)
            alheia = a.criar_reserva()
            a.consultar("reservas", "UPDATE reservas SET unidade_id = %s WHERE reserva_id = %s", str(uuid4()), alheia)
            self.assertEqual(b("GET", f"/painel/reservas/{alheia}").status_code, 403)
            self.assertEqual(b("POST", "/retiradas", {"autorizacaoId": a.autorizacao(reserva).json()["autorizacaoId"]}).status_code, 201)
            self.assertEqual(b("POST", "/retiradas", {"autorizacaoId": a.autorizacao(reserva).json()["autorizacaoId"]}).status_code, 409)
            for decisao, local in (("REJEITAR", "decisao"), (None, "cancelar")):
                r = a.criar_reserva()
                self.assertEqual(b("POST", f"/reservas/{r}/{local}", {"decisao": decisao} if decisao else JUSTIFICATIVA).status_code, 200)
        for porta in ("bff-cidadao", "gateway"):
            reserva = a.confirmada(1, item)
            self.assertEqual(a.chamar(porta, "GET", f"{CID}/reservas/{reserva}", "cidadao").status_code, 200)
            self.assertEqual(a.chamar(porta, "POST", f"{CID}/reservas/{reserva}/cancelar", "cidadao", a.nova_chave()).status_code, 202)

    def test_unidade_do_vinculo_inexistente(self):
        a.matar("bff-unidade")
        a.subir("bff-unidade", GLICO_PROFISSIONAL_UNIDADE_ID=str(uuid4()))
        try:
            for porta in ("gateway", "bff-unidade"):
                for metodo, modelo in (("GET", "/unidade"), ("PUT", "/unidade"), ("PUT", "/unidade/horarios"), ("PATCH", "/unidade/status"), ("PUT", "/unidade/prazo-analise")):
                    self.assertEqual(self.executar(porta, UNI, metodo, modelo, "profissional").status_code, 404)
        finally:
            a.matar("bff-unidade")
            a.subir("bff-unidade")
