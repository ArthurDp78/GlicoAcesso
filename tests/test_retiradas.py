import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from tests import ambiente as a


def setUpModule():
    a.preparar()


def preparar_autorizacao(status="CONFIRMADA", unidade=a.UNIDADE):
    reserva = a.criar_reserva()
    a.consultar("reservas", "UPDATE reservas SET status = %s WHERE reserva_id = %s", status, reserva)
    resposta = a.chamar("retiradas", "POST", "/internal/v1/autorizacoes", "orquestrador", a.nova_chave(), json={
        "sagaId": str(uuid4()), "reservaId": reserva, "unidadeId": unidade, "itemId": a.ITEM, "quantidade": 1})
    assert resposta.status_code == 201, resposta.text
    return reserva, resposta.json()["autorizacaoId"]


def revogar(reserva, chave=None, saga=None):
    return a.chamar("retiradas", "POST", f"/internal/v1/autorizacoes/{reserva}/cancelar", "orquestrador", chave or a.nova_chave(),
                    cabecalhos={"X-Saga-Id": saga or str(uuid4())})


class Entregas(unittest.TestCase):
    def tearDown(self):
        a.proxies["reservas"].limpar()

    def test_entrega_unica_com_evento(self):
        reserva, autorizacao = preparar_autorizacao()
        self.assertEqual(a.autorizacao(reserva).json()["status"], "ATIVA")
        chave = a.nova_chave()
        with ThreadPoolExecutor(6) as pool:
            respostas = list(pool.map(lambda _: a.entregar(autorizacao, chave), range(6)))
        self.assertEqual([(r.status_code, r.json()) for r in respostas], [(201, respostas[0].json())] * 6)
        self.assertEqual(a.entregar(autorizacao).status_code, 409)
        self.assertEqual(a.entregar(str(uuid4()), chave).json()["codigo"], "CHAVE_IDEMPOTENTE_CONFLITANTE")
        self.assertEqual(a.autorizacao(reserva).json()["status"], "UTILIZADA")
        linhas = a.consultar("retiradas", "SELECT * FROM outbox WHERE payload->>'reservaId' = %s", reserva)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(set(linhas[0]["payload"]), {"retiradaId", "reservaId", "unidadeId", "itemId", "quantidade"})
        self.assertEqual(a.consultar("retiradas", "SELECT ator_id FROM retiradas WHERE autorizacao_id = %s", autorizacao)[0]["ator_id"], "profissional-demo")
        saga, revogacao = str(uuid4()), a.nova_chave()
        for _ in range(2):
            r = revogar(reserva, revogacao, saga)
            self.assertEqual((r.status_code, r.json()), (409, {"codigo": "ENTREGA_JA_REGISTRADA", "retiradaId": respostas[0].json()["retiradaId"]}))

    def test_chaves_diferentes_concorrentes_entregam_uma_vez(self):
        _, autorizacao = preparar_autorizacao()
        with ThreadPoolExecutor(6) as pool:
            codigos = [r.status_code for r in pool.map(lambda _: a.entregar(autorizacao), range(6))]
        self.assertEqual((codigos.count(201), codigos.count(409)), (1, 5))

    def test_estado_diferente_recusa_e_nova_tentativa_reconsulta(self):
        reserva, autorizacao = preparar_autorizacao("EM_CONFIRMACAO")
        chave = a.nova_chave()
        self.assertEqual(a.entregar(autorizacao, chave).status_code, 409)
        a.consultar("reservas", "UPDATE reservas SET status = 'CONFIRMADA' WHERE reserva_id = %s", reserva)
        a.proxies["reservas"].recusar["/estado"] = 1
        self.assertEqual(a.entregar(autorizacao, chave).status_code, 503)
        a.proxies["reservas"].perder["/estado"] = 1
        self.assertEqual(a.entregar(autorizacao, chave).status_code, 503)
        self.assertEqual(a.entregar(autorizacao, chave).status_code, 201)

    def test_autorizacao_e_vinculo(self):
        reserva, autorizacao = preparar_autorizacao(unidade=str(uuid4()))
        self.assertEqual(a.entregar(autorizacao).status_code, 403)
        self.assertEqual(a.autorizacao(reserva).status_code, 403)
        self.assertEqual(a.entregar(autorizacao, token="cidadao").status_code, 403)
        self.assertEqual(a.entregar(str(uuid4())).status_code, 409)
        self.assertEqual(a.autorizacao(str(uuid4())).status_code, 404)
        self.assertEqual(a.chamar("retiradas", "POST", "/internal/v1/autorizacoes", "orquestrador", json={}).status_code, 400)
        reserva, autorizacao = preparar_autorizacao()
        self.assertEqual(revogar(reserva).json()["status"], "CANCELADA")
        r = a.entregar(autorizacao)
        self.assertEqual((r.status_code, r.json()["codigo"]), (409, "AUTORIZACAO_CANCELADA"))

    def test_entrega_e_revogacao_sao_exclusivas(self):
        vencedores = set()
        for _ in range(12):
            reserva, autorizacao = preparar_autorizacao()
            with ThreadPoolExecutor(2) as pool:
                entrega, revogacao = pool.submit(a.entregar, autorizacao), pool.submit(revogar, reserva)
            par = entrega.result().status_code, revogacao.result().status_code
            self.assertIn(par, {(201, 409), (409, 200)})
            vencedores.add(par)

    def test_revogacao_vence_depois_da_consulta_canonica(self):
        reserva, autorizacao = preparar_autorizacao()
        import threading
        proxy = a.proxies["reservas"]
        proxy.portoes["/estado"] = portao = threading.Event()
        with ThreadPoolExecutor(1) as pool:
            entrega = pool.submit(a.entregar, autorizacao)
            a.esperar(lambda: any("/estado" in v[1] for v in proxy.vistos))
            self.assertEqual(revogar(reserva).status_code, 200)
            portao.set()
        self.assertEqual((entrega.result().status_code, entrega.result().json()["codigo"]), (409, "AUTORIZACAO_CANCELADA"))
