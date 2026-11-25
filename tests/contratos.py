"""Valida contra os OpenAPI as trocas HTTP gravadas pelos testes de integração.

GLICO_TESTE_TROCAS=/tmp/trocas.jsonl uv run --locked python -m unittest ...
uv run --no-project --with pyyaml --with jsonschema python -m tests.contratos /tmp/trocas.jsonl
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ARQUIVOS = {"unidades": "unidade", "estoque": "estoque", "reservas": "reserva", "retiradas": "retirada", "orquestrador": "orquestrador",
            "bff-cidadao": "bff-cidadao", "bff-unidade": "bff-unidade"}

FORMATOS = FormatChecker(["uuid"])


@FORMATOS.checks("date-time", raises=ValueError)
def instante(valor) -> bool:
    return datetime.fromisoformat(valor).tzinfo is not None


def resolver(contrato, objeto):
    while "$ref" in objeto:
        alvo = contrato
        for parte in objeto["$ref"][2:].split("/"):
            alvo = alvo[parte]
        objeto = alvo
    return objeto


def erros(contrato, conteudo, texto):
    if conteudo is None:
        return []
    schema = resolver(contrato, conteudo)["content"]["application/json"]["schema"]
    try:
        valor = json.loads(texto)
    except ValueError:
        return ["corpo não é JSON"]
    validador = Draft202012Validator({**schema, "components": contrato["components"]}, format_checker=FORMATOS)
    return [f"{e.json_path}: {e.message[:80]}" for e in validador.iter_errors(valor)]


def main(caminho):
    operacoes, cobertas, problemas = [], set(), Counter()
    for servico, arquivo in ARQUIVOS.items():
        contrato = yaml.safe_load(open(f"docs/parte-2/api/{arquivo}.yaml", encoding="utf-8"))
        # O Gateway responde pelos mesmos contratos dos BFFs.
        donos = (servico, "gateway") if servico.startswith("bff-") else (servico,)
        base = contrato["servers"][0]["url"].rstrip("/")
        for rota, metodos in contrato["paths"].items():
            rota = base + rota
            for dono, (metodo, operacao) in ((d, item) for d in donos for item in metodos.items()):
                if metodo == "parameters":
                    continue
                operacoes.append((dono, metodo.upper(), rota, re.compile(re.sub(r"\{\w+\}", "[^/]+", rota) + "$"), contrato, operacao))
    operacoes.sort(key=lambda o: o[2].count("{"))  # Caminhos literais antes dos parametrizados.
    extras = set()
    for linha in open(caminho, encoding="utf-8"):
        t = json.loads(linha)
        achada = next((o for o in operacoes if o[0] == t["servico"] and o[1] == t["metodo"] and o[3].match(t["caminho"])), None)
        if achada is None:
            if t["status"] < 400 and t["caminho"] != "/health":
                extras.add(f'{t["servico"]} {t["metodo"]} {t["caminho"]}')
            continue
        servico, metodo, rota, _, contrato, operacao = achada
        nome, status = f"{servico} {metodo} {rota}", str(t["status"])
        resposta = operacao["responses"].get(status)
        if resposta is None:
            problemas[f"{nome}: status {status} não documentado"] += 1
            continue
        cobertas.add((nome, status))
        corpo = resolver(contrato, resposta)
        if "content" in corpo:
            for erro in erros(contrato, corpo, t["saida"]):
                problemas[f"{nome} {status} saída {erro}"] += 1
        for cabecalho in corpo.get("headers", {}):
            if cabecalho.lower() not in t["cabecalhos"]:
                problemas[f"{nome} {status} sem cabeçalho {cabecalho}"] += 1
        if status[0] == "2" and "requestBody" in operacao and t["entrada"]:
            for erro in erros(contrato, operacao["requestBody"], t["entrada"]):
                problemas[f"{nome} {status} aceitou entrada inválida: {erro}"] += 1
        obrigatoria = any(resolver(contrato, p)["name"] == "Idempotency-Key" for p in operacao.get("parameters", []))
        if obrigatoria and not t["chave"] and status[0] == "2":
            problemas[f"{nome} aceitou comando sem chave"] += 1
    for extra in sorted(extras):
        print(f"[fora do contrato] {extra}")
    for problema, vezes in sorted(problemas.items()):
        print(f"[{vezes}x] {problema}")
    faltam = [f"{o[0]} {o[1]} {o[2]}: {s}" for o in operacoes for s in o[5]["responses"] if (f"{o[0]} {o[1]} {o[2]}", s) not in cobertas]
    print(f"-- respostas documentadas não exercitadas ({len(faltam)}):", *faltam, sep="\n   ")
    # Falha somente em violações observadas nas trocas; cobertura ausente continua informativa.
    return 1 if extras or problemas else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python -m tests.contratos CAMINHO_TROCAS.jsonl")
    raise SystemExit(main(sys.argv[1]))
