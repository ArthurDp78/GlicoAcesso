"""Envia um cadastro à API interna de Unidades e imprime o identificador."""
import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import httpx


def falhar(mensagem: str, codigo: int = 1) -> int:
    print(mensagem, file=sys.stderr)
    return codigo


def descrever_erro(resposta: httpx.Response) -> str:
    try:
        dados = resposta.json()
    except ValueError:
        dados = None
    if not isinstance(dados, dict):
        return "Não foi possível cadastrar a unidade."
    codigo = dados.get("codigo")
    mensagem = dados.get("mensagem", dados.get("detail"))
    if isinstance(mensagem, str):
        return f"{codigo} — {mensagem}" if isinstance(codigo, str) else mensagem
    if resposta.status_code == 422:
        return "Confira os campos obrigatórios e seus formatos no JSON de cadastro."
    return "Não foi possível cadastrar a unidade."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cadastra uma unidade de saúde pela API interna.")
    parser.add_argument("--arquivo", type=Path, required=True, help="Caminho para o JSON de cadastro.")
    parser.add_argument("--chave", required=True, help="Chave idempotente. Reutilize em uma nova tentativa.")
    args = parser.parse_args(argv)

    chave = args.chave
    if not 1 <= len(chave) <= 128 or not chave.isascii() or not chave.isprintable() or chave.strip() != chave:
        return falhar("Informe uma chave de 1 a 128 caracteres ASCII imprimíveis, sem espaços nas bordas.", 2)
    token = os.environ.get("GLICO_GESTOR_REDE_TOKEN", "")
    if len(token) < 32 or not token.isascii() or not token.isprintable() or " " in token:
        return falhar("Configure uma credencial válida em GLICO_GESTOR_REDE_TOKEN.", 2)
    try:
        dados = json.loads(args.arquivo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return falhar("Não foi possível ler o arquivo como JSON UTF-8.", 2)
    if not isinstance(dados, dict):
        return falhar("O arquivo deve conter um objeto JSON de cadastro.", 2)

    destino = os.environ.get("UNIDADES_URL", "http://127.0.0.1:8002").rstrip("/")
    try:
        resposta = httpx.post(
            f"{destino}/internal/v1/unidades",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": chave},
            json=dados, timeout=5.0, trust_env=False,
        )
    except (httpx.RequestError, httpx.InvalidURL):
        return falhar("Não foi possível confirmar o cadastro. Tente novamente com o mesmo JSON e a mesma chave.")
    except ValueError:
        return falhar("O arquivo contém valores incompatíveis com JSON.", 2)
    if resposta.status_code != 201:
        return falhar(f"HTTP {resposta.status_code}: {descrever_erro(resposta)}")
    try:
        dados = resposta.json()
        identificador = UUID(dados["unidadeId"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return falhar("Unidades retornou um identificador inválido. Tente novamente com a mesma chave.")

    print(identificador)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
