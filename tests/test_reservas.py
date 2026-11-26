import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from servicos.reservas import segundo_plano
from tests import ambiente as a


def setUpModule():
    a.preparar()


def cancelar(reserva, token="cidadao", chave=None, corpo=None):
    ator = "cidadao" if token == "cidadao" else "unidade"
    opcoes = {"json": corpo if corpo is not None else {"justificativa": "  motivo da unidade "}} if ator == "unidade" else {}
    return a.chamar("reservas", "POST", f"/api/{ator}/v1/reservas/{reserva}/cancelar", token, chave or a.nova_chave(), **opcoes)


def interno(reserva, sufixo, corpo, papel="CIDADAO", ator="cidadao-demo", unidade=None, chave=None, token="orquestrador"):
    cabecalhos = {"X-Ator-Papel": papel, "X-Ator-Id": ator}
    if unidade:
        cabecalhos["X-Ator-Unidade-Id"] = unidade
    metodo = "GET" if corpo is None else "POST"
    return a.chamar("reservas", metodo, f"/internal/v1/reservas/{reserva}/{sufixo}", token, chave or a.nova_chave(),
                    json=corpo, cabecalhos=cabecalhos)


def forcar(reserva, status):
    a.consultar("reservas", "UPDATE reservas SET status = %s WHERE reserva_id = %s", status, reserva)


def historico(reserva):
    return a.consultar("reservas", "SELECT * FROM historico_reserva WHERE reserva_id = %s ORDER BY ocorrido_em", reserva)


def evento(reserva, event_id=None):
    return json.dumps({"eventId": event_id or str(uuid4()), "eventType": "retirada.concluida.v1", "eventVersion": 1,
                       "occurredAt": "2026-11-24T12:00:00Z", "correlationId": str(uuid4()), "payload": {
                           "retiradaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": a.ITEM,
                           "quantidade": 1}}).encode()


class CancelamentoLocal(unittest.TestCase):
    def test_cidadao_cancela_uma_unica_vez(self):
        reserva, chave = a.criar_reserva(), a.nova_chave()
        with ThreadPoolExecutor(5) as pool:
            respostas = list(pool.map(lambda _: cancelar(reserva, chave=chave), range(5)))
        self.assertEqual([(r.status_code, r.json()) for r in respostas], [(200, {"reservaId": reserva, "status": "CANCELADA"})] * 5)
        self.assertEqual([h["status_posterior"] for h in historico(reserva)], ["SOLICITADA", "CANCELADA"])
        nova = cancelar(reserva)
        self.assertEqual((nova.status_code, nova.json()["codigo"]), (409, "ESTADO_INCOMPATIVEL"))
        self.assertEqual(cancelar(a.criar_reserva(), chave=chave).json()["codigo"], "CHAVE_IDEMPOTENTE_CONFLITANTE")

    def test_profissional_exige_justificativa_e_vinculo(self):
        reserva = a.criar_reserva()
        for corpo in ({}, {"justificativa": "  abc   "}, {"justificativa": "válida", "x": 1}):
            self.assertEqual(cancelar(reserva, "profissional", corpo=corpo).status_code, 400)
        self.assertEqual(a.chamar("reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/cancelar", "profissional",
                                  json={"justificativa": "válida"}).status_code, 400)
        self.assertEqual(a.chamar("reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/cancelar", "cidadao", a.nova_chave(),
                                  json={"justificativa": "válida"}).status_code, 403)
        self.assertEqual(a.chamar("reservas", "POST", f"/api/cidadao/v1/reservas/{reserva}/cancelar", "profissional", a.nova_chave()).status_code, 403)
        a.consultar("reservas", "UPDATE reservas SET unidade_id = %s WHERE reserva_id = %s", str(uuid4()), reserva)
        self.assertEqual(cancelar(reserva, "profissional").status_code, 403)
        a.consultar("reservas", "UPDATE reservas SET unidade_id = %s, cidadao_id = 'outro' WHERE reserva_id = %s", a.UNIDADE, reserva)
        self.assertEqual(cancelar(reserva).status_code, 404)
        self.assertEqual(cancelar(str(uuid4())).status_code, 404)
        self.assertEqual(cancelar(reserva, "profissional").status_code, 200)
        self.assertEqual((historico(reserva)[-1]["justificativa"], historico(reserva)[-1]["ator_id"]), ("motivo da unidade", "profissional-demo"))

    def test_encaminhamento_persistido(self):
        for status in ("EM_CONFIRMACAO", "CONFIRMADA"):
            reserva, chave = a.criar_reserva(), a.nova_chave()
            forcar(reserva, status)
            self.assertEqual(cancelar(reserva, chave=chave).json()["codigo"], "CANCELAMENTO_DISTRIBUIDO")
            forcar(reserva, "CANCELAMENTO_EM_ANDAMENTO")
            self.assertEqual(cancelar(reserva, chave=chave).json()["codigo"], "CANCELAMENTO_DISTRIBUIDO")
            self.assertEqual(cancelar(reserva).json()["codigo"], "CANCELAMENTO_EM_ANDAMENTO")
            forcar(reserva, "CANCELADA")

    def test_cancelar_e_rejeitar_disputam_o_estado(self):
        for _ in range(5):
            reserva = a.criar_reserva()
            with ThreadPoolExecutor(2) as pool:
                cancela = pool.submit(cancelar, reserva)
                rejeita = pool.submit(a.chamar, "reservas", "POST", f"/api/unidade/v1/reservas/{reserva}/decisao",
                                      "profissional", a.nova_chave(), json={"decisao": "REJEITAR"})
            self.assertEqual(sorted([cancela.result().status_code, rejeita.result().status_code]), [200, 409])
            self.assertEqual(len(historico(reserva)), 2)


class CancelamentoDistribuido(unittest.TestCase):
    def test_transicoes_e_autorizacao(self):
        reserva, saga, chave = a.criar_reserva(), str(uuid4()), a.nova_chave()
        self.assertEqual(interno(reserva, "iniciar-cancelamento", {"sagaId": saga}).status_code, 409)
        self.assertEqual(interno(reserva, "finalizar-cancelamento", {"sagaId": saga}).status_code, 409)
        forcar(reserva, "CONFIRMADA")
        self.assertEqual(interno(reserva, "permissao-cancelamento", None).json(), {"reservaId": reserva, "status": "CONFIRMADA"})
        self.assertEqual(interno(reserva, "permissao-cancelamento", None, ator="outro").status_code, 404)
        self.assertEqual(interno(reserva, "permissao-cancelamento", None, "PROFISSIONAL", "p", str(uuid4())).status_code, 403)
        self.assertEqual(interno(reserva, "permissao-cancelamento", None, "ADMIN").status_code, 403)
        self.assertEqual(interno(reserva, "permissao-cancelamento", None, token="cidadao").status_code, 403)
        self.assertEqual(interno(reserva, "iniciar-cancelamento", {"sagaId": saga}, "PROFISSIONAL", "p", a.UNIDADE).status_code, 400)
        self.assertEqual(interno(reserva, "iniciar-cancelamento", {"sagaId": "x"}).status_code, 400)
        primeira = interno(reserva, "iniciar-cancelamento", {"sagaId": saga}, chave=chave)
        self.assertEqual(primeira.json()["status"], "CANCELAMENTO_EM_ANDAMENTO")
        fim = interno(reserva, "finalizar-cancelamento", {"sagaId": saga})
        self.assertEqual((fim.status_code, a.estado(reserva)), (200, "CANCELADA"))
        self.assertEqual(interno(reserva, "iniciar-cancelamento", {"sagaId": saga}, chave=chave).json(), primeira.json())
        self.assertEqual(interno(reserva, "iniciar-cancelamento", {"sagaId": str(uuid4())}, chave=chave).json()["codigo"], "CHAVE_IDEMPOTENTE_CONFLITANTE")

    def test_aceite_perdido_e_recuperado_com_unidade_inativa(self):
        reserva, saga, chave = a.criar_reserva(), str(uuid4()), a.nova_chave()
        aceite = lambda k=chave: interno(reserva, "aceite", {"sagaId": saga}, "PROFISSIONAL", "profissional-demo", a.UNIDADE, k)
        primeiro = aceite()
        self.assertEqual(primeiro.status_code, 200)
        a.consultar("unidades", "UPDATE unidades SET ativa = false WHERE unidade_id = %s", a.UNIDADE)
        try:
            self.assertEqual(aceite().json(), primeiro.json())
            self.assertEqual(aceite(a.nova_chave()).status_code, 403)
        finally:
            a.consultar("unidades", "UPDATE unidades SET ativa = true WHERE unidade_id = %s", a.UNIDADE)


class EstadoExpiracaoRetirada(unittest.TestCase):
    def test_estado_canonico_restrito(self):
        reserva = a.criar_reserva()
        estado = lambda token, r=reserva: a.chamar("reservas", "GET", f"/internal/v1/reservas/{r}/estado", token)
        resposta = estado("retiradas")
        self.assertEqual((resposta.json(), resposta.headers["cache-control"]), ({"reservaId": reserva, "status": "SOLICITADA"}, "no-store"))
        self.assertEqual([estado(t).status_code for t in (None, "z" * 40, "profissional", "orquestrador")], [401, 401, 403, 403])
        self.assertEqual(estado("retiradas", str(uuid4())).status_code, 404)

    def test_expira_somente_solicitada_vencida(self):
        vencida, aceita, futura = (a.criar_reserva() for _ in range(3))
        forcar(aceita, "EM_CONFIRMACAO")
        for r in (vencida, aceita):
            a.consultar("reservas", "UPDATE reservas SET decisao_ate = now() - interval '1 second' WHERE reserva_id = %s", r)
        a.esperar_estado(vencida, "EXPIRADA")
        self.assertEqual((a.estado(aceita), a.estado(futura)), ("EM_CONFIRMACAO", "SOLICITADA"))
        ultimo = historico(vencida)[-1]
        self.assertEqual((ultimo["motivo"], ultimo["ator_id"]), ("PRAZO_DECISAO_VENCIDO", None))
        self.assertEqual(a.aceitar(vencida).json()["codigo"], "ESTADO_INCOMPATIVEL")
        self.assertEqual(cancelar(vencida).status_code, 409)

    def test_consumo_da_retirada(self):
        for origem in ("CONFIRMADA", "CANCELAMENTO_EM_ANDAMENTO"):
            reserva = a.criar_reserva()
            forcar(reserva, origem)
            corpo = evento(reserva)
            with ThreadPoolExecutor(4) as pool:
                self.assertEqual(sorted(pool.map(lambda _: segundo_plano.processar_retirada(corpo), range(4))), [False] * 3 + [True])
            self.assertEqual(a.estado(reserva), "RETIRADA")
            self.assertEqual(str(historico(reserva)[-1]["event_id"]), json.loads(corpo)["eventId"])
            self.assertEqual(interno(reserva, "finalizar-cancelamento", {"sagaId": str(uuid4())}).status_code, 409)
        reserva = a.criar_reserva()
        corpo = evento(reserva)
        with self.assertRaises(segundo_plano.RetiradaInesperada):
            segundo_plano.processar_retirada(corpo)
        forcar(reserva, "CONFIRMADA")
        self.assertTrue(segundo_plano.processar_retirada(corpo))  # A falha não marcou a Inbox.
