import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pika

from servicos import mensageria, reprocessar
from servicos.orquestrador import cancelamento
from tests import ambiente as a


def setUpModule():
    a.preparar()


def etapas(saga):
    return [l["operacao"] for l in a.consultar("orquestrador", "SELECT operacao FROM saga_etapas WHERE saga_id = %s ORDER BY criada_em", saga["saga_id"])]


def encerrada(reserva, tipo, estado, motivo=None):
    saga = a.esperar(lambda: (s := a.saga_do_tipo(reserva, tipo)) and s["encerrada_em"] and s, 30, f"{tipo} não encerrou")
    assert (saga["estado"], motivo or saga["motivo_encerramento"]) == (estado, saga["motivo_encerramento"]), saga
    return saga


class Base(unittest.TestCase):
    def setUp(self):
        self.item = a.item_com_saldo(10)

    def tearDown(self):
        for proxy in a.proxies.values():
            proxy.limpar()

    def segurar(self, servico, trecho):
        proxy = a.proxies[servico]
        proxy.portoes[trecho] = portao = threading.Event()
        return portao, lambda: a.esperar(lambda: any(trecho in v[1] for v in proxy.vistos))


class Confirmacao(Base):
    def test_caminho_feliz_e_retirada_nas_tres_filas(self):
        reserva = a.confirmada(2, self.item)
        self.assertEqual(a.saldo(self.item), (10, 2))
        encerrada(reserva, "CONFIRMACAO", "CONCLUIDA")
        self.assertEqual(a.entregar(a.autorizacao(reserva).json()["autorizacaoId"]).status_code, 201)
        a.esperar_estado(reserva, "RETIRADA")
        a.esperar(lambda: a.saldo(self.item) == (8, 0))
        evento = a.consultar("retiradas", "SELECT event_id FROM outbox WHERE payload->>'reservaId' = %s", reserva)[0]["event_id"]
        for servico in ("estoque", "reservas", "orquestrador"):
            a.esperar(lambda: a.consultar(servico, "SELECT 1 FROM inbox WHERE event_id = %s", evento))
        consulta = f"/api/cidadao/v1/estoque/disponibilidade?unidadeId={a.UNIDADE}&itemId={self.item}"
        a.esperar(lambda: a.consultar("estoque", "SELECT 1 FROM disponibilidade WHERE item_id = %s AND estoque_fisico_atual = 8", self.item))
        self.assertEqual(a.chamar("estoque", "GET", consulta).json()["quantidadeDisponivel"], 8)

    def test_respostas_perdidas_sao_recuperadas_com_a_mesma_chave(self):
        a.proxies["reservas"].perder |= {"/aceite": 1, "/confirmar": 1}
        a.proxies["estoque"].perder["/alocacoes"] = 1
        a.proxies["retiradas"].perder["/autorizacoes"] = 1
        reserva = a.criar_reserva(2, self.item)
        a.aceitar(reserva)
        a.esperar_estado(reserva, "CONFIRMADA")
        encerrada(reserva, "CONFIRMACAO", "CONCLUIDA")
        self.assertEqual(a.saldo(self.item), (10, 2))
        chaves = [v[2] for v in a.proxies["estoque"].vistos if v[0] == "POST"]
        self.assertEqual((len(chaves), len(set(chaves))), (2, 1))

    def test_compensacoes(self):
        reserva = a.criar_reserva(11, self.item)
        a.aceitar(reserva)
        a.esperar_estado(reserva, "FALHA_CONFIRMACAO")
        encerrada(reserva, "CONFIRMACAO", "COMPENSADA", "SALDO_INSUFICIENTE")
        a.matar("retiradas")
        a.subir("retiradas", GLICO_FALHA_PREPARAR_AUTORIZACAO="1")
        try:
            a.proxies["estoque"].perder["/alocacoes/"] = 1
            reserva = a.criar_reserva(3, self.item)
            a.aceitar(reserva)
            a.esperar_estado(reserva, "FALHA_CONFIRMACAO")
            encerrada(reserva, "CONFIRMACAO", "COMPENSADA", "AUTORIZACAO_NAO_CRIADA")
            self.assertEqual(a.saldo(self.item), (10, 0))
        finally:
            a.matar("retiradas")
            a.subir("retiradas")


class Cancelamento(Base):
    def test_confirmada(self):
        for token in ("cidadao", "profissional"):
            reserva, chave = a.confirmada(2, self.item), a.nova_chave()
            with ThreadPoolExecutor(4) as pool:
                respostas = list(pool.map(lambda _: a.cancelar_saga(reserva, token, chave), range(4)))
            self.assertEqual([(r.status_code, r.json()) for r in respostas], [(202, respostas[0].json())] * 4)
            a.esperar_estado(reserva, "CANCELADA")
            saga = encerrada(reserva, "CANCELAMENTO", "CANCELADA")
            self.assertEqual(etapas(saga), ["INICIAR_CANCELAMENTO", "CANCELAR_AUTORIZACAO", "LIBERAR_ALOCACAO", "FINALIZAR_CANCELAMENTO"])
            self.assertEqual(a.saldo(self.item), (10, 0))
            self.assertEqual(a.autorizacao(reserva).json()["status"], "CANCELADA")
            caminho = respostas[0].headers["location"]
            self.assertEqual(a.chamar("orquestrador", "GET", caminho, token).json()["estadoExecucao"], "CANCELADA")
            outro = "profissional" if token == "cidadao" else "cidadao"
            self.assertEqual(a.chamar("orquestrador", "GET", caminho, outro).status_code, 403)
            self.assertEqual(a.cancelar_saga(reserva, token).json()["codigo"], "ESTADO_INCOMPATIVEL")
            self.assertEqual(a.cancelar_saga(reserva, token, chave).status_code, 202)
        justificativas = a.consultar("reservas", "SELECT justificativa FROM historico_reserva WHERE reserva_id = %s AND status_posterior = 'CANCELAMENTO_EM_ANDAMENTO'", reserva)
        self.assertEqual(justificativas[0]["justificativa"], "item avariado")

    def test_admissao(self):
        reserva = a.criar_reserva(1, self.item)
        self.assertEqual(a.cancelar_saga(reserva).json()["codigo"], "ESTADO_INCOMPATIVEL")
        self.assertEqual(a.cancelar_saga(str(uuid4())).status_code, 404)
        self.assertEqual(a.cancelar_saga(reserva, "profissional", json={}).status_code, 400)
        self.assertEqual(a.cancelar_saga(reserva, "profissional", json={"justificativa": "   a   "}).status_code, 400)
        self.assertEqual(a.cancelar_saga(reserva, json={"justificativa": "não cabe"}).status_code, 400)
        self.assertEqual(a.cancelar_saga(reserva, "w" * 40).status_code, 401)
        a.proxies["reservas"].recusar["/permissao-cancelamento"] = 1
        self.assertEqual(a.cancelar_saga(reserva).status_code, 503)
        a.consultar("reservas", "UPDATE reservas SET unidade_id = %s, status = 'CONFIRMADA' WHERE reserva_id = %s", str(uuid4()), reserva)
        self.assertEqual(a.cancelar_saga(reserva, "profissional").status_code, 403)

    def test_falhas_em_todas_as_etapas_sao_retomadas(self):
        reserva = a.confirmada(2, self.item)
        a.proxies["reservas"].perder |= {"/iniciar-cancelamento": 1, "/finalizar-cancelamento": 1}
        a.proxies["retiradas"].perder["/cancelar"] = 1
        a.proxies["estoque"].recusar["/alocacoes"] = 2
        a.cancelar_saga(reserva)
        a.esperar(lambda: (s := a.saga_do_tipo(reserva, "CANCELAMENTO")) and s["estado"] == "CANCELAMENTO_PENDENTE")
        a.esperar_estado(reserva, "CANCELADA")
        encerrada(reserva, "CANCELAMENTO", "CANCELADA")
        self.assertEqual(a.saldo(self.item), (10, 0))

    def test_reinicio_do_orquestrador(self):
        reserva = a.confirmada(2, self.item)
        a.proxies["retiradas"].recusar["/cancelar"] = 100
        a.cancelar_saga(reserva)
        a.esperar_estado(reserva, "CANCELAMENTO_EM_ANDAMENTO")
        a.matar("orquestrador")
        a.proxies["retiradas"].limpar()
        a.subir("orquestrador")
        a.esperar_estado(reserva, "CANCELADA")
        self.assertEqual(a.saldo(self.item), (10, 0))

    def interromper_em(self, servico, trecho, esperadas, saldo_parcial):
        portao, emitido = self.segurar(servico, trecho)
        reserva = a.criar_reserva(2, self.item)
        a.aceitar(reserva)
        emitido()
        a.esperar_estado(reserva, "EM_CONFIRMACAO")
        resposta = a.cancelar_saga(reserva)
        self.assertEqual(resposta.status_code, 202)
        situacao = a.chamar("orquestrador", "GET", resposta.headers["location"], "cidadao").json()
        self.assertEqual((situacao["tipo"], situacao.get("estadoExecucao")), ("CANCELAMENTO", None))
        self.assertEqual(a.cancelar_saga(reserva).json()["codigo"], "EXECUCAO_CONCORRENTE")
        self.assertEqual(a.saldo(self.item), saldo_parcial)
        portao.set()
        a.esperar_estado(reserva, "CANCELADA")
        encerrada(reserva, "CONFIRMACAO", "INTERROMPIDA", "CANCELAMENTO_SOLICITADO")
        saga = encerrada(reserva, "CANCELAMENTO", "CANCELADA")
        self.assertEqual((etapas(saga), str(saga["saga_id"])), (esperadas, resposta.json()["sagaId"]))
        self.assertEqual(a.saldo(self.item), (10, 0))

    def test_durante_o_aceite_sem_efeitos(self):
        self.interromper_em("reservas", "/aceite", ["FINALIZAR_CANCELAMENTO"], (10, 0))

    def test_durante_a_alocacao(self):
        self.interromper_em("estoque", "/alocacoes", ["LIBERAR_ALOCACAO", "FINALIZAR_CANCELAMENTO"], (10, 2))

    def test_durante_a_preparacao(self):
        self.interromper_em("retiradas", "/autorizacoes", ["CANCELAR_AUTORIZACAO", "LIBERAR_ALOCACAO", "FINALIZAR_CANCELAMENTO"], (10, 2))

    def test_transicao_interposta_perdida(self):
        a.proxies["reservas"].perder["/iniciar-cancelamento"] = 2
        self.interromper_em("estoque", "/alocacoes", ["LIBERAR_ALOCACAO", "FINALIZAR_CANCELAMENTO"], (10, 2))

    def test_finalizacao_em_voo_conclui_e_depois_cancela(self):
        portao, emitido = self.segurar("reservas", "/confirmar")
        reserva = a.criar_reserva(2, self.item)
        a.aceitar(reserva)
        emitido()
        a.esperar_estado(reserva, "CONFIRMADA")
        self.assertEqual(a.cancelar_saga(reserva).status_code, 202)
        portao.set()
        a.esperar_estado(reserva, "CANCELADA")
        encerrada(reserva, "CONFIRMACAO", "CONCLUIDA")
        encerrada(reserva, "CANCELAMENTO", "CANCELADA")
        self.assertEqual(a.saldo(self.item), (10, 0))

    def test_recusa_da_transicao_retoma_a_confirmacao(self):
        portao, emitido = self.segurar("estoque", "/alocacoes")
        reserva = a.criar_reserva(2, self.item)
        a.aceitar(reserva)
        emitido()
        resposta = a.cancelar_saga(reserva)
        # A propriedade muda entre a admissão e a transição: Reservas revalida e recusa.
        a.consultar("reservas", "UPDATE reservas SET cidadao_id = 'outro' WHERE reserva_id = %s", reserva)
        portao.set()
        a.esperar_estado(reserva, "CONFIRMADA")
        encerrada(reserva, "CONFIRMACAO", "CONCLUIDA")
        situacao = a.chamar("orquestrador", "GET", resposta.headers["location"], "cidadao").json()
        self.assertEqual((situacao.get("estadoExecucao"), situacao["motivoEncerramento"]), (None, "HTTP_404"))
        self.assertEqual(a.saldo(self.item), (10, 2))

    def test_pedido_durante_falha_da_confirmacao(self):
        portao, emitido = self.segurar("estoque", "/alocacoes")
        reserva = a.criar_reserva(11, self.item)
        a.aceitar(reserva)
        emitido()
        self.assertEqual(a.cancelar_saga(reserva).status_code, 202)
        portao.set()
        a.esperar_estado(reserva, "FALHA_CONFIRMACAO")
        encerrada(reserva, "CONFIRMACAO", "COMPENSADA")
        encerrada(reserva, "CANCELAMENTO", "INTERROMPIDA", "ESTADO_INCOMPATIVEL")


class DisputaComRetirada(Base):
    def test_entrega_vence_por_resposta_da_revogacao(self):
        reserva = a.confirmada(2, self.item)
        autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
        proxy = a.proxies["reservas"]
        proxy.portoes["/estado"] = portao = threading.Event()
        a.proxies["retiradas"].recusar["/cancelar"] = 1000
        with ThreadPoolExecutor(1) as pool:
            entrega = pool.submit(a.entregar, autorizacao)
            a.esperar(lambda: any("/estado" in v[1] for v in proxy.vistos))
            a.cancelar_saga(reserva)
            a.esperar_estado(reserva, "CANCELAMENTO_EM_ANDAMENTO")
            portao.set()
        self.assertEqual(entrega.result().status_code, 201)
        a.proxies["retiradas"].recusar.clear()
        a.esperar_estado(reserva, "RETIRADA")
        saga = encerrada(reserva, "CANCELAMENTO", "INTERROMPIDA", "ENTREGA_JA_REGISTRADA")
        self.assertEqual(str(saga["retirada_id"]), entrega.result().json()["retiradaId"])
        a.esperar(lambda: a.saldo(self.item) == (8, 0))
        self.assertIsNone(a.alocacao(reserva)["liberada_em"])
        self.assertEqual(a.cancelar_saga(reserva).status_code, 409)

    def test_disputa_real_preserva_invariantes(self):
        fisico = 10
        for _ in range(6):
            reserva = a.confirmada(1, self.item)
            autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
            with ThreadPoolExecutor(2) as pool:
                entrega, cancela = pool.submit(a.entregar, autorizacao), pool.submit(a.cancelar_saga, reserva)
            final = a.esperar_estado(reserva, "RETIRADA", "CANCELADA")
            self.assertEqual(final == "RETIRADA", entrega.result().status_code == 201, (final, entrega.result().text))
            fisico -= final == "RETIRADA"
            a.esperar(lambda: a.saldo(self.item) == (fisico, 0))
            a.esperar(lambda: not a.sagas(reserva, "encerrada_em IS NULL"))
            self.assertIn(cancela.result().status_code, (202, 409))

    def test_inbox_encerra_cancelamento_e_deduplica(self):
        reserva = a.confirmada(1, self.item)
        a.proxies["retiradas"].recusar["/cancelar"] = 1000
        a.cancelar_saga(reserva)
        a.esperar_estado(reserva, "CANCELAMENTO_EM_ANDAMENTO")
        corpo = json.dumps({"eventId": str(uuid4()), "eventType": "retirada.concluida.v1", "eventVersion": 1,
                            "occurredAt": "2026-11-24T12:00:00Z", "correlationId": str(uuid4()), "payload": {
                                "retiradaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": self.item, "quantidade": 1}}).encode()
        with ThreadPoolExecutor(3) as pool:
            self.assertEqual(sorted(pool.map(lambda _: cancelamento.processar_retirada(corpo), range(3))), [False, False, True])
        saga = encerrada(reserva, "CANCELAMENTO", "INTERROMPIDA", "ENTREGA_JA_REGISTRADA")
        self.assertIsNotNone(saga["event_id"])
        self.assertEqual(a.consultar("orquestrador", "SELECT 1 FROM saga_etapas WHERE saga_id = %s AND estado_tecnico = 'PENDENTE'", saga["saga_id"]), [])
        self.assertIsNone(a.alocacao(reserva)["liberada_em"])


class Mensageria(Base):
    def publicar(self, reserva, item, quantidade):
        conexao = pika.BlockingConnection(pika.URLParameters(os.environ["RABBITMQ_URL"]))
        canal = conexao.channel()
        mensageria.declarar(canal)
        corpo = json.dumps({"eventId": str(uuid4()), "eventType": "retirada.concluida.v1", "eventVersion": 1,
                            "occurredAt": "2026-11-24T12:00:00Z", "correlationId": str(uuid4()), "payload": {
                                "retiradaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": item, "quantidade": quantidade}})
        canal.basic_publish("", mensageria.FILA_RETIRADA_ESTOQUE, corpo.encode())
        conexao.close()

    def test_divergencia_vai_a_fila_de_erros_e_e_reprocessada(self):
        reserva = str(uuid4())
        self.publicar(reserva, self.item, 2)
        ocorrencia = lambda: a.consultar("estoque", "SELECT * FROM ocorrencias_retirada WHERE reserva_id = %s", reserva)
        a.esperar(ocorrencia)
        a.chamar("estoque", "POST", "/internal/v1/alocacoes", "orquestrador", a.nova_chave(), json={
            "sagaId": str(uuid4()), "reservaId": reserva, "unidadeId": a.UNIDADE, "itemId": self.item, "quantidade": 2})
        a.esperar(lambda: reprocessar.reprocessar(mensageria.FILA_RETIRADA_ESTOQUE) >= 1)
        a.esperar(lambda: a.saldo(self.item) == (8, 0))
        self.assertIsNotNone(ocorrencia()[0]["resolvida_em"])

    def test_consumidores_fora_do_ar_recebem_depois(self):
        reserva = a.confirmada(2, self.item)
        autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
        for nome in ("estoque", "orquestrador"):
            a.matar(nome)
        try:
            self.assertEqual(a.entregar(autorizacao).status_code, 201)
            a.esperar_estado(reserva, "RETIRADA")
            self.assertEqual(a.saldo(self.item), (10, 2))
        finally:
            for nome in ("estoque", "orquestrador"):
                a.subir(nome)
        a.esperar(lambda: a.saldo(self.item) == (8, 0))

    def test_broker_inacessivel_mantem_evento_pendente(self):
        reserva = a.confirmada(1, self.item)
        autorizacao = a.autorizacao(reserva).json()["autorizacaoId"]
        a.matar("retiradas")
        a.subir("retiradas", RABBITMQ_URL="amqp://guest:guest@127.0.0.1:1/%2F")
        try:
            self.assertEqual(a.entregar(autorizacao).status_code, 201)
            pendente = a.consultar("retiradas", "SELECT status FROM outbox WHERE payload->>'reservaId' = %s", reserva)
            self.assertEqual(pendente[0]["status"], "PENDENTE")
            self.assertEqual(a.estado(reserva), "CONFIRMADA")
        finally:
            a.matar("retiradas")
            a.subir("retiradas")
        a.esperar_estado(reserva, "RETIRADA")


class RegressaoBorda(Base):
    def test_jornada_existente_pelo_gateway(self):
        self.assertEqual(a.chamar("gateway", "GET", "/api/cidadao/v1/itens").status_code, 200)
        explorar = a.chamar("gateway", "GET", f"/api/cidadao/v1/explorar?itemId={a.ITEM}").json()
        self.assertEqual(explorar[0]["unidadeId"], a.UNIDADE)
        reserva, chave = a.criar_reserva(1, self.item), a.nova_chave()
        painel = a.chamar("gateway", "GET", "/api/unidade/v1/painel/reservas", "profissional").json()
        self.assertIn(reserva, [r["reservaId"] for r in painel])
        self.assertEqual([a.aceitar(reserva, chave).status_code for _ in range(2)], [202, 202])
        a.esperar_estado(reserva, "CONFIRMADA")
        publica = a.chamar("gateway", "GET", f"/api/cidadao/v1/reservas/{reserva}", "cidadao").json()
        self.assertEqual((publica["status"], "cidadaoId" in publica), ("CONFIRMADA", False))
        rejeitada = a.criar_reserva(1, self.item)
        r = a.chamar("gateway", "POST", f"/api/unidade/v1/reservas/{rejeitada}/decisao", "profissional", a.nova_chave(), json={"decisao": "REJEITAR"})
        self.assertEqual((r.status_code, a.estado(rejeitada)), (200, "REJEITADA"))
        self.assertEqual(a.chamar("gateway", "GET", "/api/unidade/v1/painel/estoque", "profissional").status_code, 200)
        self.assertEqual(a.chamar("gateway", "POST", "/internal/v1/autorizacoes", "orquestrador", "k").status_code, 404)
