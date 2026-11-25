import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai.errors import APIError

from servicos.orientacao.embeddings import DIMENSOES, cliente_embeddings
from servicos.orientacao.ingestao import descricao_erro_provedor


class TestEmbeddingsGoogle(unittest.IsolatedAsyncioTestCase):
    def test_exige_chave_google(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "GOOGLE_API_KEY"):
                cliente_embeddings("gemini-embedding-2")

    def test_preserva_formato_do_modelo_001_quando_configurado(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "servicos.orientacao.embeddings.genai.Client",
        ) as criar:
            api = criar.return_value.models.embed_content
            api.return_value = SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0] * DIMENSOES)])
            cliente = cliente_embeddings("gemini-embedding-001")
            cliente.embed_query("Como retirar?")
            self.assertEqual(api.call_args.kwargs["contents"], "Como retirar?")
            self.assertEqual(api.call_args.kwargs["config"].task_type, "RETRIEVAL_QUERY")

    def test_inclui_detalhe_http_do_provedor_sem_detalhes_internos(self):
        erro = APIError(403, {
            "status": "PERMISSION_DENIED",
            "message": "A chave não tem acesso ao modelo.",
        })
        self.assertEqual(
            descricao_erro_provedor(erro),
            "HTTP 403 (PERMISSION_DENIED): A chave não tem acesso ao modelo.",
        )

    async def test_configura_dimensao_retries_timeout_e_tarefas_de_busca(self):
        resposta = SimpleNamespace(embeddings=[SimpleNamespace(values=[0.25] * DIMENSOES)])
        cliente = MagicMock()
        cliente.models.embed_content.return_value = resposta
        cliente.aio.models.embed_content = AsyncMock(return_value=resposta)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}), patch(
            "servicos.orientacao.embeddings.genai.Client", return_value=cliente,
        ) as criar_cliente:
            embeddings = cliente_embeddings("gemini-embedding-2", timeout=2.5, tentativas=0)

            opcoes = criar_cliente.call_args.kwargs["http_options"]
            self.assertEqual(opcoes.api_version, "v1beta")
            self.assertEqual(opcoes.timeout, 2500)
            self.assertEqual(opcoes.retry_options.attempts, 1)

            vetor = embeddings.embed_query("Como retirar?")
            config_sync = cliente.models.embed_content.call_args.kwargs["config"]
            self.assertEqual(len(vetor), DIMENSOES)
            self.assertIsNone(config_sync.task_type)
            self.assertEqual(cliente.models.embed_content.call_args.kwargs["contents"], "task: question answering | query: Como retirar?")
            self.assertEqual(config_sync.output_dimensionality, DIMENSOES)

            documentos = embeddings.embed_documents(["Guia de retirada"])
            chamada_documentos = cliente.models.embed_content.call_args.kwargs
            config_documentos = chamada_documentos["config"]
            self.assertEqual(len(documentos), 1)
            self.assertEqual(chamada_documentos["contents"], [{"parts": [{"text": "title: none | text: Guia de retirada"}]}])
            self.assertIsNone(config_documentos.task_type)
            self.assertEqual(config_documentos.output_dimensionality, DIMENSOES)

            vetor_async = await embeddings.aembed_query("Como retirar?")
            config_async = cliente.aio.models.embed_content.call_args.kwargs["config"]
            self.assertEqual(len(vetor_async), DIMENSOES)
            self.assertIsNone(config_async.task_type)
            self.assertEqual(cliente.aio.models.embed_content.call_args.kwargs["contents"], "task: question answering | query: Como retirar?")
            self.assertEqual(config_async.output_dimensionality, DIMENSOES)


if __name__ == "__main__":
    unittest.main()
