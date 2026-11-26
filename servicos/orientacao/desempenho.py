"""Mede localmente o percurso da orientação e estima tokens da configuração OpenAI."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import httpx
import tiktoken
from langchain_core.runnables import RunnableLambda

from servicos.orientacao.avaliacao import CASOS, ITEM_DEMO, gerador_ollama, vetores_ollama
from servicos.orientacao.disponibilidade import criar_ferramenta_disponibilidade
from servicos.orientacao.ingestao import BASE, ler_base
from servicos.orientacao.rag import (
    PRAZO_GERACAO, PRAZO_ORIENTACAO, PROMPT, EntradaRag, RespostaModelo, buscar_trechos, criar_chain,
)

# Standard, em USD por milhão de tokens. Valores consultados em 25/11/2026.
PRECO = {"embedding": 0.02, "entrada": 0.40, "saida": 1.60}
VOLUMES = (1_000, 10_000, 100_000)
MODELO_EMBEDDING_LOCAL = "qwen3-embedding:0.6b"
MODELO_CHAT_LOCAL = "qwen2.5:3b"


def custo(tokens: dict[str, int]) -> float:
    return sum(tokens[etapa] * preco for etapa, preco in PRECO.items()) / 1_000_000


async def medir(bff: str, ollama: str, rodadas: int, prazo_local: float | None) -> dict:
    prazo_total = PRAZO_ORIENTACAO if prazo_local is None else prazo_local
    prazo_tentativa = PRAZO_GERACAO if prazo_local is None else prazo_local
    tokenizer_chat = tiktoken.get_encoding("o200k_base")
    tokenizer_embedding = tiktoken.get_encoding("cl100k_base")
    base = ler_base(BASE)
    tokens_indexacao = sum(len(tokenizer_embedding.encode(t.texto_embedding)) for t in base.values())
    modelo_indexado = "ollama/" + MODELO_EMBEDDING_LOCAL
    amostras = []
    async with httpx.AsyncClient(timeout=4, trust_env=False) as cliente:
        ferramenta = criar_ferramenta_disponibilidade(cliente, bff)

        for rodada in range(1, rodadas + 1):
            for caso in CASOS:
                etapas = dict.fromkeys(("bff", "embedding", "busca_vetorial", "geracao"), 0.0)
                tokens_local = {"embedding": 0, "entrada": 0, "saida": 0}
                tokens_estimados = {
                    "embedding": len(tokenizer_embedding.encode(caso.pergunta)), "entrada": 0, "saida": 0,
                }
                chamadas_geracao = 0

                def registrar(dados):
                    tokens_local["entrada"] += dados.get("prompt_eval_count", 0)
                    tokens_local["saida"] += dados.get("eval_count", 0)

                def registrar_embedding(dados):
                    tokens_local["embedding"] = dados.get("prompt_eval_count")

                async def recuperar(pergunta):
                    inicio = perf_counter()
                    vetor, = await asyncio.to_thread(
                        vetores_ollama, ollama, MODELO_EMBEDDING_LOCAL, [pergunta], registrar_embedding,
                    )
                    etapas["embedding"] = perf_counter() - inicio
                    inicio = perf_counter()
                    trechos = await asyncio.to_thread(buscar_trechos, vetor, modelo_indexado)
                    etapas["busca_vetorial"] = perf_counter() - inicio
                    return trechos

                gerador = gerador_ollama(cliente, ollama, MODELO_CHAT_LOCAL, registrar)

                async def gerar(campos):
                    nonlocal chamadas_geracao
                    chamadas_geracao += 1
                    mensagens = [
                        {"role": m.type, "content": m.content} for m in PROMPT.format_messages(**campos)
                    ]
                    payload = {"messages": mensagens, "schema": RespostaModelo.model_json_schema()}
                    tokens_estimados["entrada"] += len(tokenizer_chat.encode(json.dumps(payload, ensure_ascii=False)))
                    inicio = perf_counter()
                    try:
                        resposta = await gerador.ainvoke(campos)
                    finally:
                        etapas["geracao"] += perf_counter() - inicio
                    tokens_estimados["saida"] += len(tokenizer_chat.encode(resposta.model_dump_json()))
                    return resposta

                chain = criar_chain(lambda _: [], RunnableLambda(gerar), recuperar, prazo_geracao=prazo_tentativa)
                inicio_total = perf_counter()
                consulta = await ferramenta.ainvoke({"itemId": ITEM_DEMO})
                etapas["bff"] = perf_counter() - inicio_total
                if consulta.status != "consultada":
                    raise RuntimeError("BFF indisponível durante a medição.")
                interrupcao = None
                try:
                    async with asyncio.timeout(max(prazo_total - etapas["bff"], 0)):
                        resultado = await chain.ainvoke(EntradaRag(caso.pergunta, consulta))
                    modo = resultado.modo
                except (TimeoutError, httpx.HTTPError) as erro:
                    interrupcao = type(erro).__name__
                    modo = "orientacao_basica"
                    # Uma geração interrompida pode ter consumido tokens sem devolver metadados.
                total = perf_counter() - inicio_total
                etapas["chain_e_validacao"] = max(total - sum(etapas.values()), 0)
                amostras.append({
                    "rodada": rodada, "caso": caso.id, "modo": modo, "interrupcao": interrupcao,
                    "chamadas_geracao": chamadas_geracao,
                    "ms_total": round(1000 * total, 3),
                    "ms_etapas": {etapa: round(1000 * tempo, 3) for etapa, tempo in etapas.items()},
                    "tokens_ollama": tokens_local,
                    "tokens_estimados_openai": tokens_estimados,
                    "custo_estimado_openai_usd": custo(tokens_estimados),
                })

    custo_medio = sum(a["custo_estimado_openai_usd"] for a in amostras) / len(amostras)
    return {
        "executado_em": datetime.now(UTC).isoformat(),
        "prazo_total_s": prazo_total, "prazo_por_tentativa_geracao_s": prazo_tentativa,
        "modelos_locais": {"embedding": MODELO_EMBEDDING_LOCAL, "geracao": MODELO_CHAT_LOCAL},
        "tarifas_openai": {"data": "2026-11-25", "usd_por_milhao": PRECO},
        "amostras": amostras,
        "estimativa_indexacao": {
            "trechos": len(base), "tokens": tokens_indexacao,
            "usd": custo({"embedding": tokens_indexacao, "entrada": 0, "saida": 0}),
        },
        "projecao_usd": {
            "por_consulta": custo_medio,
            "por_volume": {str(volume): volume * custo_medio for volume in VOLUMES},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bff-url", default=os.getenv("BFF_CIDADAO_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--rodadas", type=int, default=2)
    parser.add_argument("--prazo-local", type=float, help="Aumenta o prazo, em segundos, só para a medição local.")
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()
    if args.rodadas < 1:
        parser.error("--rodadas deve ser positivo")
    if args.prazo_local is not None and not 0 < args.prazo_local <= 120:
        parser.error("--prazo-local deve estar entre 0 e 120 segundos")
    resultado = asyncio.run(medir(args.bff_url, args.ollama_url.rstrip("/"), args.rodadas, args.prazo_local))
    args.saida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
