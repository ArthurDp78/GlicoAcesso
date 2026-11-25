import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from servicos.estoque import baixa
from servicos.estoque.eventos import aplicar
from tests import ambiente as a


def setUpModule():
    a.preparar()


def novo_item():
    return a.chamar("estoque", "POST", "/internal/v1/itens", "admin", a.nova_chave(),
                    json={"nome": "Insulina NPH", "tipo": "MEDICAMENTO"}).json()["itemId"]


def base(item, unidade=a.UNIDADE):
    return f"/api/unidade/v1/estoque/{unidade}/itens/{item}"


def prof(metodo, caminho, corpo, chave=None):
    return a.chamar("estoque", metodo, caminho, "profissional", chave or a.nova_chave(), json=corpo)


def saldo(item):
    return a.consultar("estoque", "SELECT * FROM saldos WHERE item_id = %s", item)[0]


def com_saldo(quantidade):
    item = novo_item()
    assert prof("PUT", base(item) + "/permissao", {"permiteReserva": True}).status_code == 200
    assert prof("POST", base(item) + "/entradas", {"quantidade": quantidade, "motivo": "compra"}).status_code == 201
    return item


def alocar(item, quantidade, reserva=None, chave=None):
    return a.chamar("estoque", "POST", "/internal/v1/alocacoes", "orquestrador", chave or a.nova_chave(), json={
        "sagaId": str(uuid4()), "reservaId": reserva or str(uuid4()), "unidadeId": a.UNIDADE, "itemId": item,
        "quantidade": quantidade})


def evento_retirada(reserva, item, quantidade, **extra):
    return json.dumps({"eventId": str(uuid4()), "eventType": "retirada.concluida.v1", "eventVersion": 1,
                       "occurredAt": "2026-11-24T12:00:00Z", "correlationId": str(uuid4()), "causationId": None, "payload": {
                           "retiradaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": item,
                           "quantidade": quantidade, **extra}}).encode()


class Catalogo(unittest.TestCase):
    def test_cadastro_e_atualizacao(self):
        chave, corpo = a.nova_chave(), {"nome": "Lancetas", "tipo": "INSUMO", "descricao": "cx"}
        criar = lambda c=corpo, t="admin": a.chamar("estoque", "POST", "/internal/v1/itens", t, chave, json=c)
        primeiro = criar()
        self.assertEqual((primeiro.status_code, criar().json()), (201, primeiro.json()))
        self.assertEqual(criar({**corpo, "nome": "X"}).status_code, 409)
        self.assertEqual(criar(t="profissional").status_code, 403)
        caminho = f"/internal/v1/itens/{primeiro.json()['itemId']}"
        self.assertEqual(a.chamar("estoque", "PUT", caminho, "admin", a.nova_chave(), json={"nome": "L2", "tipo": "INSUMO"}).json()["nome"], "L2")
        self.assertEqual(a.chamar("estoque", "PUT", f"/internal/v1/itens/{uuid4()}", "admin", a.nova_chave(), json=corpo).status_code, 404)
        self.assertIn("L2", [i["nome"] for i in a.chamar("estoque", "GET", "/api/unidade/v1/estoque/itens", "profissional").json()])
        self.assertEqual(a.chamar("estoque", "GET", "/api/unidade/v1/estoque/itens", "cidadao").status_code, 403)
        self.assertEqual(a.chamar("estoque", "GET", "/api/unidade/v1/estoque/itens").status_code, 401)


class Saldos(unittest.TestCase):
    def test_permissao_inicializa_e_projeta(self):
        item = novo_item()
        self.assertEqual(prof("POST", base(item) + "/entradas", {"quantidade": 1, "motivo": "m"}).status_code, 404)
        self.assertEqual(prof("PUT", base(item) + "/permissao", {"permiteReserva": False}).status_code, 200)
        self.assertEqual((saldo(item)["estoque_fisico_atual"], saldo(item)["estoque_version"]), (0, 1))
        prof("PUT", base(item) + "/permissao", {"permiteReserva": False})
        self.assertEqual(saldo(item)["estoque_version"], 1)
        prof("PUT", base(item) + "/permissao", {"permiteReserva": True})
        consulta = f"/api/cidadao/v1/estoque/disponibilidade?unidadeId={a.UNIDADE}&itemId={item}"
        a.esperar(lambda: (r := a.chamar("estoque", "GET", consulta)).status_code == 200 and r.json()["permiteReserva"])
        self.assertEqual(prof("PUT", base(str(uuid4())) + "/permissao", {"permiteReserva": True}).status_code, 404)
        self.assertEqual(prof("PUT", base(item, str(uuid4())) + "/permissao", {"permiteReserva": True}).status_code, 403)

    def test_entrada_e_ajuste(self):
        item, chave = com_saldo(10), a.nova_chave()
        corpo = {"quantidade": 5, "motivo": "reposição"}
        with ThreadPoolExecutor(5) as pool:
            respostas = list(pool.map(lambda _: prof("POST", base(item) + "/entradas", corpo, chave), range(5)))
        self.assertEqual([(r.status_code, r.json()) for r in respostas], [(201, respostas[0].json())] * 5)
        self.assertEqual(saldo(item)["estoque_fisico_atual"], 15)
        self.assertEqual(prof("POST", base(item) + "/entradas", {**corpo, "quantidade": 6}, chave).status_code, 409)
        self.assertEqual(alocar(item, 12).status_code, 201)
        ajuste = prof("POST", base(item) + "/ajustes", {"variacaoFisica": -4, "motivo": "perda"})
        self.assertEqual((ajuste.status_code, ajuste.json()["codigo"]), (409, "AJUSTE_INCOMPATIVEL"))
        ok = prof("POST", base(item) + "/ajustes", {"variacaoFisica": -3, "motivo": "perda"})
        self.assertEqual((ok.status_code, ok.json()["variacaoFisica"]), (201, -3))
        self.assertEqual(ok.json()["estoqueVersion"], saldo(item)["estoque_version"])
        for corpo in ({"variacaoFisica": 0, "motivo": "m"}, {"variacaoFisica": 1, "motivo": " "}, {"motivo": "m"}):
            self.assertEqual(prof("POST", base(item) + "/ajustes", corpo).status_code, 422)
        self.assertEqual(prof("POST", base(item) + "/entradas", {"quantidade": 2147483647, "motivo": "m"}).status_code, 422)
        tipos = [l["event_type"] for l in a.consultar("estoque", "SELECT event_type FROM outbox WHERE payload->>'itemId' = %s ORDER BY (payload->>'estoqueVersion')::int", item)]
        self.assertEqual(tipos, ["estoque.permissao-reserva-alterada.v1", "estoque.entrada-registrada.v1",
                                 "estoque.entrada-registrada.v1", "estoque.alocacao-criada.v1", "estoque.ajustado.v1"])

    def test_alocacoes_concorrentes_nao_excedem_o_saldo(self):
        item = com_saldo(5)
        with ThreadPoolExecutor(10) as pool:
            codigos = [r.status_code for r in pool.map(lambda _: alocar(item, 1), range(10))]
        self.assertEqual((codigos.count(201), codigos.count(409)), (5, 5))
        self.assertEqual(alocar(item, 0).status_code, 400)


class Baixa(unittest.TestCase):
    def test_baixa_idempotente_sem_desconto_duplicado(self):
        item, reserva = com_saldo(10), str(uuid4())
        alocar(item, 2, reserva)
        corpo = evento_retirada(reserva, item, 2)
        with ThreadPoolExecutor(5) as pool:
            self.assertEqual(sorted(pool.map(lambda _: baixa.processar_retirada(corpo), range(5))), [False] * 4 + [True])
        atual = saldo(item)
        self.assertEqual((atual["estoque_fisico_atual"], atual["quantidade_alocada"]), (8, 0))
        movimento = a.consultar("estoque", "SELECT * FROM movimentacoes WHERE item_id = %s AND retirada_id IS NOT NULL", item)
        self.assertEqual([m["variacao_fisica"] for m in movimento], [-2])
        evento = a.consultar("estoque", "SELECT * FROM outbox WHERE event_type = 'estoque.retirada-baixada.v1' AND payload->>'reservaId' = %s", reserva)
        self.assertEqual([e["payload"]["quantidadeBaixada"] for e in evento], [2])
        self.assertEqual(str(evento[0]["causation_id"]), json.loads(corpo)["eventId"])
        resposta = a.chamar("estoque", "DELETE", f"/internal/v1/alocacoes/{reserva}", "orquestrador", a.nova_chave(), cabecalhos={"X-Saga-Id": str(uuid4())})
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (409, "ALOCACAO_CONSUMIDA"))

    def test_divergencia_nao_baixa_e_pode_ser_reprocessada(self):
        item, reserva = com_saldo(10), str(uuid4())
        corpo = evento_retirada(reserva, item, 2)
        with self.assertRaises(baixa.RetiradaDivergente):
            baixa.processar_retirada(corpo)
        alocar(item, 2, reserva)
        with self.assertRaises(baixa.RetiradaDivergente):
            baixa.processar_retirada(evento_retirada(reserva, item, 1))
        self.assertEqual(saldo(item)["estoque_fisico_atual"], 10)
        ocorrencias = a.consultar("estoque", "SELECT motivo FROM ocorrencias_retirada WHERE reserva_id = %s ORDER BY registrada_em", reserva)
        self.assertEqual([o["motivo"] for o in ocorrencias], ["ALOCACAO_INEXISTENTE", "DADOS_INCOMPATIVEIS"])
        self.assertTrue(baixa.processar_retirada(corpo))
        self.assertEqual(saldo(item)["estoque_fisico_atual"], 8)
        with self.assertRaises(Exception):
            baixa.processar_retirada(evento_retirada(reserva, item, 0))

    def test_projecao_nao_regride(self):
        item = com_saldo(3)
        lida = lambda: a.consultar("estoque", "SELECT * FROM disponibilidade WHERE item_id = %s", item)
        a.esperar(lambda: lida() and lida()[0]["estoque_fisico_atual"] == 3)
        antigo = {"eventId": str(uuid4()), "eventType": "estoque.ajustado.v1", "occurredAt": "2026-01-01T00:00:00Z", "payload": {
            "unidadeId": a.UNIDADE, "itemId": item, "estoqueVersion": 1, "estoqueFisicoAtual": 99, "quantidadeAlocada": 0, "permiteReserva": True}}
        self.assertTrue(aplicar(json.dumps(antigo).encode()))
        self.assertEqual(lida()[0]["estoque_fisico_atual"], 3)
