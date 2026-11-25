import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import psycopg
from google.genai.errors import APIError
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from servicos.banco import BancoIndisponivel, conectar
from servicos.migracoes import migrar
from servicos.orientacao.embeddings import cliente_embeddings, modelo_embeddings, validar_vetor

BANCO = "ORIENTACAO_DATABASE_URL"
RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "docs/parte-4/base-conhecimento"
SECAO = re.compile(r'^<a id="([a-z0-9-]+)"></a>\n\n## (.+)$', re.MULTILINE)
FONTE = re.compile(r"- \[([^\]]+)\]\(([^)]+)\)")


@dataclass(frozen=True)
class Trecho:
    id: str
    versao: int
    caminho: str
    titulo: str
    secao: str
    conteudo: str
    fontes: list[dict[str, str]]

    @property
    def texto_embedding(self) -> str:
        return f"{self.titulo}\n{self.secao}\n\n{self.conteudo}"

    @property
    def resumo(self) -> str:
        return hashlib.sha256(self.texto_embedding.encode("utf-8")).hexdigest()


def ler_guia(arquivo: Path, pasta: Path) -> list[Trecho]:
    texto = arquivo.read_text(encoding="utf-8-sig")
    corpo, separador, rodape = texto.partition("\n### Fontes\n")
    cabecalho = re.match(r"^# (.+)\n\nVersão: ([1-9][0-9]*)\n", corpo)
    secoes = list(SECAO.finditer(corpo))
    if not (cabecalho and separador and secoes) or len(secoes) != len(re.findall(r"^## ", corpo, re.M)):
        raise ValueError(f"Guia sem título, versão, fontes ou seções identificadas: {arquivo.name}")
    if corpo[cabecalho.end():secoes[0].start()].strip():
        raise ValueError(f"Inclua o conteúdo em uma seção identificada: {arquivo.name}")

    fontes = []
    for linha in rodape.splitlines():
        if not linha.strip():
            continue
        fonte = FONTE.fullmatch(linha.strip())
        if fonte is None:
            raise ValueError(f"Fonte inválida em {arquivo.name}")
        fontes.append({"titulo": fonte[1], "referencia": fonte[2]})
    if not fontes:
        raise ValueError(f"Nenhuma fonte em {arquivo.name}")

    trechos = []
    for i, secao in enumerate(secoes):
        fim = secoes[i + 1].start() if i + 1 < len(secoes) else len(corpo)
        conteudo = corpo[secao.end():fim].strip()
        if not conteudo:
            raise ValueError(f"Seção vazia em {arquivo.name}: {secao[1]}")
        trechos.append(Trecho(f"{arquivo.stem}#{secao[1]}", int(cabecalho[2]),
                              arquivo.relative_to(pasta).as_posix(), cabecalho[1],
                              secao[2], conteudo, fontes))
    return trechos


def ler_base(pasta: Path) -> dict[str, Trecho]:
    if not pasta.is_dir():
        raise ValueError(f"Pasta da base inexistente: {pasta}")
    trechos = {}
    for arquivo in sorted(pasta.glob("*.md")):
        for trecho in ler_guia(arquivo, pasta):
            if trecho.id in trechos:
                raise ValueError(f"Identificador duplicado: {trecho.id}")
            trechos[trecho.id] = trecho
    return trechos


def gerar_embeddings(trechos: list[Trecho], modelo: str) -> dict[str, list[float]]:
    cliente = cliente_embeddings(modelo)
    return dict(zip((trecho.id for trecho in trechos),
                    cliente.embed_documents([trecho.texto_embedding for trecho in trechos]),
                    strict=True))


def indexar(pasta: Path, modelo: str, gerar=gerar_embeddings) -> tuple[int, int, int]:
    with conectar(BANCO) as conexao:
        # Coordena reindexações sem bloquear as leituras do índice publicado.
        conexao.execute("SELECT pg_advisory_xact_lock(6122027)")
        trechos = ler_base(pasta)
        register_vector(conexao)
        existentes = {
            linha["id"]: linha for linha in conexao.execute(
                "SELECT id, modelo, resumo, versao, caminho, fontes FROM trechos_conhecimento"
            )
        }
        alterados = [
            trecho for trecho in trechos.values()
            if trecho.id not in existentes
            or (existentes[trecho.id]["modelo"], existentes[trecho.id]["resumo"]) != (modelo, trecho.resumo)
        ]
        vetores = gerar(alterados, modelo) if alterados else {}
        if vetores.keys() != {trecho.id for trecho in alterados}:
            raise ValueError("A resposta de embeddings não corresponde aos trechos enviados.")
        for vetor in vetores.values():
            validar_vetor(vetor)

        for trecho in alterados:
            conexao.execute("""
                INSERT INTO trechos_conhecimento
                    (id, versao, caminho, titulo, secao, conteudo, fontes, modelo, resumo, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    versao = EXCLUDED.versao, caminho = EXCLUDED.caminho, titulo = EXCLUDED.titulo,
                    secao = EXCLUDED.secao, conteudo = EXCLUDED.conteudo, fontes = EXCLUDED.fontes,
                    modelo = EXCLUDED.modelo, resumo = EXCLUDED.resumo, embedding = EXCLUDED.embedding
            """, (trecho.id, trecho.versao, trecho.caminho, trecho.titulo, trecho.secao,
                  trecho.conteudo, Jsonb(trecho.fontes), modelo, trecho.resumo, Vector(vetores[trecho.id])), prepare=False)

        for trecho in trechos.values():
            if trecho.id in vetores:
                continue
            anterior = existentes[trecho.id]
            metadados = (trecho.versao, trecho.caminho, trecho.fontes)
            if metadados != (anterior["versao"], anterior["caminho"], anterior["fontes"]):
                conexao.execute("""
                    UPDATE trechos_conhecimento SET versao = %s, caminho = %s, fontes = %s WHERE id = %s
                """, (trecho.versao, trecho.caminho, Jsonb(trecho.fontes), trecho.id), prepare=False)
        removidos = existentes.keys() - trechos.keys()
        if removidos:
            conexao.execute("DELETE FROM trechos_conhecimento WHERE id = ANY(%s)", (sorted(removidos),))
        return len(trechos), len(vetores), len(removidos)


def descricao_erro_provedor(erro: APIError) -> str:
    status = f"HTTP {erro.code}"
    if erro.status:
        status += f" ({erro.status})"
    if erro.message:
        status += f": {erro.message}"
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza a base versionada de orientação com o pgvector.")
    parser.add_argument("--pasta", type=Path, default=BASE, help="Pasta que contém os guias Markdown.")
    args = parser.parse_args()
    try:
        modelo = modelo_embeddings()
        migrar("orientacao", carregar_demo=False)
        total, gerados, removidos = indexar(args.pasta, modelo)
    except APIError as erro:
        parser.exit(1, f"Falha no provedor de embeddings: {descricao_erro_provedor(erro)}.\n")
    except httpx.TransportError as erro:
        parser.exit(1, f"Falha no provedor de embeddings: {type(erro).__name__}.\n")
    except (OSError, ValueError, BancoIndisponivel, psycopg.Error) as erro:
        parser.exit(1, f"Falha na indexação: {erro}\n")
    print(f"Índice sincronizado. Trechos: {total}, embeddings gerados: {gerados}, removidos: {removidos}.")


if __name__ == "__main__":
    main()
