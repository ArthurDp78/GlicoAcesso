import math
import os

from google import genai
from google.genai.types import EmbedContentConfig, EmbedContentResponse, HttpOptions, HttpRetryOptions
from langchain_core.embeddings import Embeddings

MODELO_PADRAO = "gemini-embedding-2"
DIMENSOES = 1536


def modelo_embeddings() -> str:
    modelo = os.getenv("ORIENTACAO_MODELO_EMBEDDING", MODELO_PADRAO).strip()
    if not modelo:
        raise ValueError("Informe um modelo de embeddings válido.")
    return modelo


class ClienteEmbeddingsGoogle(Embeddings):
    def __init__(self, modelo: str, *, timeout: float, tentativas: int) -> None:
        chave = os.getenv("GOOGLE_API_KEY", "").strip()
        if not chave:
            raise ValueError("Configure GOOGLE_API_KEY para gerar os embeddings.")
        if tentativas < 0:
            raise ValueError("O número de tentativas de embeddings não pode ser negativo.")
        self.modelo = modelo
        self.cliente = genai.Client(
            api_key=chave,
            vertexai=False,
            http_options=HttpOptions(
                api_version="v1beta",
                timeout=int(timeout * 1000),
                retry_options=HttpRetryOptions(attempts=tentativas + 1),
            ),
        )

    def _texto(self, texto: str, *, documento: bool) -> str:
        if self.modelo.removeprefix("models/") == "gemini-embedding-001":
            return texto
        if documento:
            return f"title: none | text: {texto}"
        return f"task: question answering | query: {texto}"

    def _config(self, tarefa: str) -> EmbedContentConfig:
        if self.modelo.removeprefix("models/") == "gemini-embedding-001":
            return EmbedContentConfig(task_type=tarefa, output_dimensionality=DIMENSOES)
        return EmbedContentConfig(output_dimensionality=DIMENSOES)

    @staticmethod
    def _vetores(resposta: EmbedContentResponse) -> list[list[float]]:
        if not resposta.embeddings:
            raise ValueError("O Google AI Studio não retornou embeddings.")
        return [list(embedding.values or []) for embedding in resposta.embeddings]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        vetores: list[list[float]] = []
        for inicio in range(0, len(textos), 100):
            lote_textos = textos[inicio:inicio + 100]
            resposta = self.cliente.models.embed_content(
                model=self.modelo,
                contents=[
                    {"parts": [{"text": self._texto(texto, documento=True)}]}
                    for texto in lote_textos
                ],
                config=self._config("RETRIEVAL_DOCUMENT"),
            )
            lote = self._vetores(resposta)
            if len(lote) != len(lote_textos):
                raise ValueError(
                    f"O provedor retornou {len(lote)} embeddings para {len(lote_textos)} textos."
                )
            vetores.extend(lote)
        return vetores

    def embed_query(self, texto: str) -> list[float]:
        resposta = self.cliente.models.embed_content(
            model=self.modelo,
            contents=self._texto(texto, documento=False),
            config=self._config("RETRIEVAL_QUERY"),
        )
        vetores = self._vetores(resposta)
        if len(vetores) != 1:
            raise ValueError(f"O provedor retornou {len(vetores)} embeddings para uma pergunta.")
        return vetores[0]

    async def aembed_query(self, texto: str) -> list[float]:
        resposta = await self.cliente.aio.models.embed_content(
            model=self.modelo,
            contents=self._texto(texto, documento=False),
            config=self._config("RETRIEVAL_QUERY"),
        )
        vetores = self._vetores(resposta)
        if len(vetores) != 1:
            raise ValueError(f"O provedor retornou {len(vetores)} embeddings para uma pergunta.")
        return vetores[0]


def cliente_embeddings(
    modelo: str, *, timeout: float = 30, tentativas: int = 2,
) -> ClienteEmbeddingsGoogle:
    return ClienteEmbeddingsGoogle(modelo, timeout=timeout, tentativas=tentativas)


def validar_vetor(vetor: list[float]) -> None:
    if len(vetor) != DIMENSOES or not all(math.isfinite(valor) for valor in vetor) or not any(vetor):
        raise ValueError("O provedor retornou um vetor inválido para busca por cosseno.")
