import json
import unittest
from uuid import UUID

import httpx
from langchain_core.runnables import RunnableLambda

from servicos.orientacao.rag import (
    Evidencia, Fonte, PerguntaSobreItem, RespostaModelo, criar_chain, criar_chain_com_disponibilidade,
)

ITEM = UUID("20000000-0000-4000-8000-000000000001")
UNIDADE = "10000000-0000-4000-8000-000000000001"
FONTE = Fonte("disponibilidade#consulta", "Disponibilidade", "Consultar um item")


class TestDisponibilidadeRag(unittest.IsolatedAsyncioTestCase):
    async def test_busca_dados_a_cada_pergunta_e_envia_contexto_ao_modelo(self):
        chamadas = []
        contexto = []

        def bff(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/api/cidadao/v1/explorar")
            self.assertEqual(request.url.params["itemId"], str(ITEM))
            self.assertNotIn("Authorization", request.headers)
            chamadas.append(request)
            return httpx.Response(200, json=[{
                "unidadeId": UNIDADE, "nomeUnidade": "Demo",
                "disponivel": len(chamadas) == 2, "permiteReserva": True,
                "atualizadoEm": "2026-11-25T12:00:00Z", "endereco": "Dado fora do contrato",
            }])

        def gerar(entrada):
            contexto.append(json.loads(entrada["consulta"]))
            return RespostaModelo(estado="respondida", resposta="Consulte o portal.", fontes=[FONTE.id])

        base = criar_chain(lambda _: [Evidencia(FONTE, "Consulte o portal.")], RunnableLambda(gerar))
        async with httpx.AsyncClient(transport=httpx.MockTransport(bff)) as cliente:
            chain = criar_chain_com_disponibilidade(cliente, "http://bff", base)
            pergunta = PerguntaSobreItem("Posso solicitar este item?", ITEM)
            antes = await chain.ainvoke(pergunta)
            depois = await chain.ainvoke(pergunta)

        self.assertFalse(antes.consulta.unidades[0].disponivel)
        self.assertTrue(depois.consulta.unidades[0].disponivel)
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(len(contexto), 2)
        self.assertFalse(contexto[0]["unidades"][0]["disponivel"])
        self.assertTrue(contexto[1]["unidades"][0]["disponivel"])
        self.assertNotIn("endereco", contexto[1]["unidades"][0])

    async def test_separa_lista_vazia_de_erro_preservando_o_estado_no_fallback(self):
        for resposta, estado in [
            (httpx.Response(200, json=[]), "consultada"),
            (httpx.Response(503), "indisponivel"),
            (httpx.Response(200, json=[{"disponivel": True}]), "indisponivel"),
        ]:
            with self.subTest(estado=estado, resposta=resposta):
                base = criar_chain(lambda _: [], RunnableLambda(lambda _: None))
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resposta)) as cliente:
                    chain = criar_chain_com_disponibilidade(cliente, "http://bff", base)
                    resultado = await chain.ainvoke(PerguntaSobreItem("Posso solicitar?", ITEM))
                self.assertEqual(resultado.modo, "orientacao_basica")
                self.assertEqual(resultado.consulta.status, estado)
                self.assertEqual(resultado.consulta.unidades, ())
