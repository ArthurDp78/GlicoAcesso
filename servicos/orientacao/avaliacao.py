"""Avaliação pareada dos guias de orientação do GlicoAcesso."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID

import httpx
from langchain_core.runnables import RunnableLambda
from langchain_core.callbacks import UsageMetadataCallbackHandler

from servicos.banco import conectar
from servicos.orientacao.disponibilidade import criar_ferramenta_disponibilidade
from servicos.orientacao.embeddings import DIMENSOES, cliente_embeddings, modelo_embeddings
from servicos.orientacao.ingestao import BANCO, BASE, indexar, ler_base
from servicos.orientacao.rag import (
    DISTANCIA_MAXIMA, LIMITE_TRECHOS, MODELO_GERACAO, PRAZO_EMBEDDING, PRAZO_GERACAO,
    PROMPT, EntradaRag, RespostaModelo, buscar_trechos, criar_gerador, montar_prompt,
)
from servicos.orientacao.resiliencia import chamar_provedor

ITEM_DEMO = UUID("20000000-0000-4000-8000-000000000001")


@dataclass(frozen=True)
class Caso:
    id: str
    pergunta: str
    criterio: str
    fontes: tuple[str, ...]


CASOS = (
    Caso("solicitacao", "Como envio uma solicitação de reserva e onde encontro o código?",
         "Indicar Solicitar reserva, credencial e quantidade, envio e código gerado.", ("solicitacao#enviar",)),
    Caso("confirmacao", "Meu pedido está EM_CONFIRMACAO. Já posso ir ao balcão?",
         "Orientar a aguardar CONFIRMADA e consultar o pedido pelo código.", ("confirmacao#acompanhar",)),
    Caso("retirada", "Como retirar uma reserva confirmada no balcão?",
         "Indicar levar o código e seguir as orientações de retirada da unidade.", ("retirada#balcao",)),
    Caso("cancelamento", "Como cancelar uma reserva e o que faço se ficar em processamento?",
         "Indicar Cancelar reserva quando disponível e consultar de novo pelo código.", ("solicitacao#cancelar",)),
    Caso("disponibilidade", "Onde posso solicitar reserva para o item selecionado e como conferir se posso reservar?",
         "Identificar as unidades conforme a consulta e distinguir disponibilidade de permissão.",
         ("disponibilidade#reserva-permitida",)),
    Caso("fora_da_base", "Como consigo a segunda via do meu cartão de transporte?",
         "Indicar informação insuficiente ou tema fora do escopo sem inventar instruções.", ()),
)


def vetores_ollama(origem: str, modelo: str, textos: list[str], registrar=None) -> list[list[float]]:
    resposta = httpx.post(origem + "/api/embed", json={"model": modelo, "input": textos, "truncate": False},
                          timeout=120, trust_env=False)
    resposta.raise_for_status()
    dados = resposta.json()
    if registrar is not None:
        registrar(dados)
    vetores = dados["embeddings"]
    if len(vetores) != len(textos) or any(not 0 < len(vetor) <= DIMENSOES for vetor in vetores):
        raise ValueError("Dimensão ou quantidade de vetores inválida para a avaliação local.")
    # Coordenadas iguais a zero preservam a distância de cosseno.
    return [vetor + [0.0] * (DIMENSOES - len(vetor)) for vetor in vetores]


def gerador_ollama(cliente: httpx.AsyncClient, origem: str, modelo: str, registrar=None) -> RunnableLambda:
    async def gerar(campos: dict[str, str]) -> RespostaModelo:
        mensagens = PROMPT.format_messages(**campos)
        resposta = await cliente.post(origem + "/api/chat", timeout=120, json={
            "model": modelo, "stream": False, "format": RespostaModelo.model_json_schema(),
            "options": {"temperature": 0, "num_predict": 300, "seed": 42},
            "messages": [
                {"role": "system" if mensagem.type == "system" else "user", "content": mensagem.content}
                for mensagem in mensagens
            ],
        })
        resposta.raise_for_status()
        dados = resposta.json()
        if registrar is not None:
            registrar(dados)
        return RespostaModelo.model_validate_json(dados["message"]["content"])
    return RunnableLambda(gerar)


async def avaliar(args) -> dict:
    base = ler_base(BASE)
    async with httpx.AsyncClient(timeout=4, trust_env=False) as http:
        consulta = await criar_ferramenta_disponibilidade(http, args.bff_url).ainvoke({"itemId": args.item_id})
        if consulta.status != "consultada":
            raise RuntimeError("O BFF precisa responder antes de iniciar a avaliação.")

        if args.ollama_url:
            origem = args.ollama_url.rstrip("/")
            modelo_embedding = f"ollama/{args.ollama_embedding}"
            modelo_chat = args.ollama_chat

            def gerar_vetores(trechos, _modelo):
                vetores = vetores_ollama(origem, args.ollama_embedding, [trecho.texto_embedding for trecho in trechos])
                return dict(zip((trecho.id for trecho in trechos), vetores, strict=True))

            with conectar(BANCO) as conexao:
                existente = conexao.execute(
                    "SELECT 1 FROM trechos_conhecimento WHERE modelo <> %s LIMIT 1", (modelo_embedding,),
                ).fetchone()
            if existente is not None:
                raise RuntimeError("Use um banco vetorial descartável e vazio para avaliar o Ollama.")
            await asyncio.to_thread(indexar, BASE, modelo_embedding, gerar_vetores)
            gerador = gerador_ollama(http, origem, modelo_chat)
            vetores = await asyncio.to_thread(
                vetores_ollama, origem, args.ollama_embedding, [caso.pergunta for caso in CASOS],
            )
            prazo_geracao = 120
        else:
            modelo_embedding = modelo_embeddings()
            modelo_chat = os.getenv("ORIENTACAO_MODELO_GERACAO", MODELO_GERACAO).strip()
            embeddings = cliente_embeddings(modelo_embedding, timeout=PRAZO_EMBEDDING, tentativas=0)
            gerador = criar_gerador()
            vetores = [
                await chamar_provedor(lambda: embeddings.aembed_query(caso.pergunta), timeout=PRAZO_EMBEDDING)
                for caso in CASOS
            ]
            prazo_geracao = PRAZO_GERACAO

        with conectar(BANCO) as conexao:
            indexados = {
                linha["id"]: linha["resumo"] for linha in conexao.execute(
                    "SELECT id, resumo FROM trechos_conhecimento WHERE modelo = %s", (modelo_embedding,),
                )
            }
        if indexados != {trecho.id: trecho.resumo for trecho in base.values()}:
            raise RuntimeError("Sincronize o índice com os guias antes da avaliação.")

        resultados = []
        for caso, vetor in zip(CASOS, vetores, strict=True):
            trechos = await asyncio.to_thread(buscar_trechos, vetor, modelo_embedding)
            entrada = EntradaRag(caso.pergunta, consulta)
            resultados_caso = {}
            for modo, evidencias in (("sem_recuperacao", []), ("com_recuperacao", trechos)):
                campos = montar_prompt(entrada, evidencias)
                uso = UsageMetadataCallbackHandler()
                inicio = perf_counter()
                saida = await chamar_provedor(
                    lambda: gerador.ainvoke(campos, config={"callbacks": [uso]}), timeout=prazo_geracao,
                )
                segundos = perf_counter() - inicio
                if saida is None:
                    raise RuntimeError(f"O provedor não devolveu uma resposta estruturada em {caso.id}/{modo}.")
                fontes_disponiveis = {trecho.fonte.id for trecho in evidencias}
                resultados_caso[modo] = {
                    **saida.model_dump(),
                    "geracao_segundos": round(segundos, 3),
                    "uso_geracao": uso.usage_metadata,
                    "citacoes_validas": set(saida.fontes) <= fontes_disponiveis,
                    "fontes_recuperadas": [trecho.fonte.id for trecho in evidencias],
                }
            resultados.append({"caso": asdict(caso), **resultados_caso})
            print(f"Avaliado: {caso.id}", file=sys.stderr)

    return {
        "executado_em": datetime.now(UTC).isoformat(),
        "provedor": "Ollama local" if args.ollama_url else "Google AI Studio",
        "modelo_geracao": modelo_chat, "modelo_embedding": modelo_embedding,
        "temperatura": 0 if args.ollama_url else "padrao_do_provedor",
        "limite_trechos": LIMITE_TRECHOS, "distancia_maxima": DISTANCIA_MAXIMA,
        "base": {t.id: {"versao": t.versao, "sha256": t.resumo} for t in base.values()},
        "prompt_sha256": hashlib.sha256(repr(PROMPT.messages).encode()).hexdigest(),
        "item_id": str(args.item_id), "consulta_compartilhada": consulta.model_dump(mode="json"),
        "resultados": resultados,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bff-url", default=os.getenv("BFF_CIDADAO_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--item-id", type=UUID, default=ITEM_DEMO)
    parser.add_argument("--saida", type=Path, help="Grava as evidências JSON neste arquivo.")
    parser.add_argument("--ollama-url", help="Usa Ollama e reindexa na instância vetorial descartável.")
    parser.add_argument("--ollama-chat", default="qwen2.5:3b")
    parser.add_argument("--ollama-embedding", default="qwen3-embedding:0.6b")
    args = parser.parse_args()
    resultado = asyncio.run(avaliar(args))
    evidencia = json.dumps(resultado, indent=2, ensure_ascii=False)
    if args.saida:
        args.saida.write_text(evidencia + "\n", encoding="utf-8")
    else:
        print(evidencia)


if __name__ == "__main__":
    main()
