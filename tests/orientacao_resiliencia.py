import asyncio
import unittest
from unittest.mock import patch
from uuid import UUID

import httpx
from google.genai.errors import APIError
from langchain_core.runnables import RunnableLambda
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError, GoogleRateLimitError

from servicos.orientacao.rag import PerguntaSobreItem, criar_chain_com_disponibilidade
from servicos.orientacao.resiliencia import chamar_provedor

ITEM = UUID("20000000-0000-4000-8000-000000000001")
UNIDADE = "10000000-0000-4000-8000-000000000001"


def erro_http(status, *, mensagem="erro simulado", retry_after=None):
    headers = {} if retry_after is None else {"Retry-After": retry_after}
    resposta = httpx.Response(status, request=httpx.Request("POST", "http://provedor"), headers=headers)
    return APIError(status, {"message": mensagem}, response=resposta)


class TestResilienciaOrientacao(unittest.IsolatedAsyncioTestCase):
    async def test_retry_com_backoff_e_recuperacao(self):
        resultados = iter([erro_http(503), erro_http(429, retry_after="0.4"), "ok"])

        async def chamar():
            resultado = next(resultados)
            if isinstance(resultado, APIError):
                raise resultado
            return resultado

        with patch("servicos.orientacao.resiliencia.asyncio.sleep") as dormir:
            self.assertEqual(await chamar_provedor(chamar, timeout=2), "ok")
        self.assertEqual([c.args[0] for c in dormir.await_args_list], [0.25, 0.5])

    async def test_retry_para_rate_limit_classificado_pelo_chat_gemini(self):
        resultados = iter([GoogleRateLimitError("limite temporário"), "ok"])

        async def chamar():
            resultado = next(resultados)
            if isinstance(resultado, ChatGoogleGenerativeAIError):
                raise resultado
            return resultado

        with patch("servicos.orientacao.resiliencia.asyncio.sleep") as dormir:
            self.assertEqual(await chamar_provedor(chamar, timeout=2), "ok")
        dormir.assert_awaited_once_with(0.25)

    async def test_sem_retry_para_credencial_quota_ou_espera_acima_do_prazo(self):
        for erro in (erro_http(401), erro_http(429, mensagem="quota excedida"),
                     erro_http(429, retry_after="60")):
            with self.subTest(erro=erro), patch("servicos.orientacao.resiliencia.asyncio.sleep") as dormir:
                async def chamar():
                    raise erro

                with self.assertRaises(APIError):
                    await chamar_provedor(chamar, timeout=1)
                dormir.assert_not_awaited()

    async def test_timeout_por_tentativa(self):
        iniciadas = 0
        canceladas = 0

        async def chamar():
            nonlocal iniciadas, canceladas
            iniciadas += 1
            try:
                await asyncio.Event().wait()
            finally:
                canceladas += 1

        with patch("servicos.orientacao.resiliencia.BACKOFF", (0, 0)), self.assertRaises(TimeoutError):
            await chamar_provedor(chamar, timeout=0.01)
        self.assertEqual((iniciadas, canceladas), (3, 3))

    async def test_fallback_preserva_disponibilidade_quando_provedor_falha_ou_excede_prazo(self):
        chamadas_bff = []

        def responder_bff(request):
            chamadas_bff.append(request)
            return httpx.Response(200, json=[{
                "unidadeId": UNIDADE, "nomeUnidade": "Unidade de teste", "disponivel": True,
                "permiteReserva": True, "atualizadoEm": "2026-11-25T12:00:00Z",
            }])

        async def falhar(_):
            raise erro_http(503)

        async def demorar(_):
            await asyncio.Event().wait()

        async with httpx.AsyncClient(transport=httpx.MockTransport(responder_bff)) as cliente:
            for gerar in (falhar, demorar):
                with self.subTest(gerar=gerar), patch("servicos.orientacao.rag.PRAZO_ORIENTACAO", 0.2):
                    chain = criar_chain_com_disponibilidade(cliente, "http://bff", RunnableLambda(gerar))
                    resultado = await chain.ainvoke(PerguntaSobreItem("Posso reservar?", ITEM))
                self.assertEqual(resultado.modo, "orientacao_basica")
                self.assertEqual(resultado.fontes, ())
                self.assertEqual(resultado.consulta.status, "consultada")
                self.assertTrue(resultado.consulta.unidades[0].disponivel)
            with patch.dict("os.environ", {"GOOGLE_API_KEY": ""}):
                chain = criar_chain_com_disponibilidade(cliente, "http://bff")
                resultado = await chain.ainvoke(PerguntaSobreItem("Posso reservar?", ITEM))
            self.assertEqual(resultado.modo, "orientacao_basica")
            self.assertEqual(resultado.consulta.status, "consultada")
        self.assertEqual(len(chamadas_bff), 3)
