import os
import json
import unittest
from unittest.mock import patch

from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableLambda

from servicos.orientacao.rag import Evidencia, Fonte, RespostaModelo, criar_chain, criar_gerador

FONTE = Fonte("retirada#balcao", "Retirada no balcão", "Como retirar")
EVIDENCIA = Evidencia(FONTE, "Confira a confirmação no portal e leve o código ao balcão.")


class TestOrientacaoRag(unittest.TestCase):
    def test_configura_prazo_minimo_aceito_pelo_gemini(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "servicos.orientacao.rag.ChatGoogleGenerativeAI",
        ) as modelo:
            modelo.return_value.with_structured_output.return_value = RunnableLambda(
                lambda resultado: {"parsed": None},
            )
            criar_gerador()

        self.assertEqual(modelo.call_args.kwargs["timeout"], 10)

    def test_responde_com_fonte_dos_guias(self):
        def gerar(entrada):
            self.assertEqual(entrada["pergunta"], "Como retirar?")
            self.assertEqual(json.loads(entrada["trechos"])[0]["conteudo"], EVIDENCIA.conteudo)
            return RespostaModelo(estado="respondida", resposta=EVIDENCIA.conteudo,
                                 fontes=[FONTE.id, FONTE.id])

        resultado = criar_chain(lambda _: [EVIDENCIA], RunnableLambda(gerar)).invoke("  Como retirar? ")
        self.assertEqual(resultado.modo, "rag")
        self.assertEqual(resultado.fontes, (FONTE,))

    def test_sem_trechos_pula_geracao(self):
        def gerar(_):
            self.fail("O modelo foi chamado sem contexto.")

        resultado = criar_chain(lambda _: [], RunnableLambda(gerar)).invoke("Como rastrear uma encomenda?")
        self.assertEqual(resultado.modo, "orientacao_basica")
        self.assertIn("informação suficiente", resultado.resposta)
        self.assertEqual(resultado.fontes, ())

    def test_rejeita_fonte_inventada_e_resposta_sem_evidencia(self):
        for dados in [
            {"estado": "respondida", "resposta": "Texto", "fontes": [FONTE.id, "guia#inventado"]},
            {"estado": "respondida", "resposta": "Texto", "fontes": []},
            {"estado": "sem_evidencia", "resposta": "", "fontes": []},
        ]:
            with self.subTest(dados=dados):
                gerador = RunnableLambda(lambda _: RespostaModelo(**dados))
                resposta = criar_chain(lambda _: [EVIDENCIA], gerador).invoke("Como retirar?")
                self.assertEqual(resposta.modo, "orientacao_basica")
                self.assertEqual(resposta.fontes, ())

    def test_falha_de_parse_vira_orientacao_basica(self):
        def gerar(_):
            raise OutputParserException("Resposta fora do esquema.")

        resposta = criar_chain(lambda _: [EVIDENCIA], RunnableLambda(gerar)).invoke("Como retirar?")
        self.assertEqual(resposta.modo, "orientacao_basica")

    def test_fora_do_escopo_descarta_texto_do_modelo(self):
        gerador = RunnableLambda(lambda _: RespostaModelo(
            estado="fora_do_escopo", resposta="Texto que deve ser descartado", fontes=[FONTE.id],
        ))
        resposta = criar_chain(lambda _: [EVIDENCIA], gerador).invoke("Que dose devo tomar?")
        self.assertEqual(resposta.modo, "fora_do_escopo")
        self.assertEqual(resposta.fontes, ())
        self.assertNotIn("Texto que deve ser descartado", resposta.resposta)


if __name__ == "__main__":
    unittest.main()
