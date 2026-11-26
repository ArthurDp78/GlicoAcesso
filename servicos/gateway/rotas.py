"""Encaminhamento das rotas públicas aos BFFs. Só o que está na tabela é alcançável pelo cliente."""
import os
import re

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from servicos.correlacao import CABECALHO, UUID_CANONICO
from servicos.http import requisitar


CIDADAO, UNIDADE = "/api/cidadao/v1", "/api/unidade/v1"
BFFS = {CIDADAO: ("BFF_CIDADAO_URL", "http://127.0.0.1:8001"), UNIDADE: ("BFF_UNIDADE_URL", "http://127.0.0.1:8005")}
PUBLICAS = ("/itens", "/unidades", "/explorar")
OPERACOES = {
    CIDADAO: (
        *(("GET", caminho) for caminho in PUBLICAS),
        ("POST", "/reservas"), ("GET", "/reservas/{reservaId}"), ("POST", "/reservas/{reservaId}/cancelar"),
        ("POST", "/orientacoes"),
    ),
    UNIDADE: (
        ("GET", "/unidade"), ("PUT", "/unidade"), ("PUT", "/unidade/horarios"), ("PUT", "/unidade/prazo-analise"),
        ("PATCH", "/unidade/status"),
        ("GET", "/painel/estoque"), ("GET", "/painel/estoque/catalogo"),
        ("GET", "/painel/reservas"), ("GET", "/painel/reservas/{reservaId}"),
        ("PUT", "/painel/estoque/{unidadeId}/itens/{itemId}/permissao"),
        ("POST", "/painel/estoque/{unidadeId}/itens/{itemId}/entradas"),
        ("POST", "/painel/estoque/{unidadeId}/itens/{itemId}/ajustes"),
        ("POST", "/reservas/{reservaId}/decisao"), ("POST", "/reservas/{reservaId}/cancelar"), ("POST", "/retiradas"),
    ),
}
# Operações cujo contrato documenta 400 para entrada inválida; as demais usam 422.
COM_400 = ("/reservas/{reservaId}/decisao", "/reservas/{reservaId}/cancelar")
# Listas fechadas: cabeçalhos de identidade delegada (X-Ator-*) e quaisquer outros não atravessam a borda.
CABECALHOS_DE_IDA = ("authorization", "idempotency-key", "content-type")
CABECALHOS_DE_VOLTA = ("content-type", "cache-control", "location", "www-authenticate", "retry-after")
# Consultas por POST: não criam recurso e dispensam Idempotency-Key.
SEM_CHAVE = ("/orientacoes",)
LIMITE_CORPO_BYTES = 1_048_576


async def ler_corpo_limitado(request: Request) -> bytes:
    """Limita o corpo antes de agregá-lo em memória; Content-Length pode faltar ou mentir."""
    tamanho = request.headers.get("content-length")
    if tamanho is not None:
        try:
            if int(tamanho) > LIMITE_CORPO_BYTES:
                raise HTTPException(413, "Corpo da requisição excede o limite permitido.")
        except ValueError:
            raise HTTPException(400, "Content-Length inválido.") from None
    partes, total = [], 0
    async for parte in request.stream():
        total += len(parte)
        if total > LIMITE_CORPO_BYTES:
            raise HTTPException(413, "Corpo da requisição excede o limite permitido.")
        partes.append(parte)
    return b"".join(partes)


async def repassar(request: Request, prefixo: str) -> Response:
    variavel, padrao = BFFS[prefixo]
    cabecalhos = {nome: request.headers[nome] for nome in CABECALHOS_DE_IDA if nome in request.headers}
    cabecalhos[CABECALHO] = request.state.correlacao
    corpo = await ler_corpo_limitado(request) if request.method in ("POST", "PUT", "PATCH") else None
    try:
        resposta = await requisitar(
            request.app.state.http, request.method, os.environ.get(variavel, padrao).rstrip("/") + request.url.path,
            params=request.query_params.multi_items(), headers=cabecalhos, content=corpo,
        )
    except HTTPException as erro:
        raise HTTPException(503, "Serviço temporariamente indisponível. Em comandos, repita com a mesma chave e conteúdo.") from erro
    return Response(
        content=resposta.content, status_code=resposta.status_code,
        headers={nome: resposta.headers[nome] for nome in CABECALHOS_DE_VOLTA if nome in resposta.headers},
    )


def criar_encaminhamento(prefixo: str, caminho: str):
    async def encaminhar(request: Request) -> Response:
        autenticada = prefixo == UNIDADE or caminho not in PUBLICAS
        esquema, _, credencial = request.headers.get("authorization", "").partition(" ")
        if autenticada and (esquema.lower() != "bearer" or not credencial.strip()):
            # A borda recusa a ausência de credencial; o BFF valida o token.
            raise HTTPException(401, "Credencial Bearer obrigatória.", headers={"WWW-Authenticate": "Bearer"})
        if not all(UUID_CANONICO.fullmatch(valor) for valor in request.path_params.values()):
            status = 400 if caminho in COM_400 else 422
            return JSONResponse({"codigo": "ENTRADA_INVALIDA", "mensagem": "Identificador inválido no caminho."}, status_code=status)
        return await repassar(request, prefixo)
    return encaminhar


def instalar(app: FastAPI) -> None:
    rotas = APIRouter()
    for prefixo, operacoes in OPERACOES.items():
        for metodo, caminho in operacoes:
            rota = prefixo + caminho
            parametros = [
                {"name": nome, "in": "path", "required": True,
                 "schema": {"type": "string", "format": "uuid"}}
                for nome in re.findall(r"\{(\w+)\}", caminho)
            ]
            parametros.append({
                "name": "X-Correlation-Id", "in": "header", "required": False,
                "schema": {"type": "string", "format": "uuid"},
            })
            if metodo in ("POST", "PUT", "PATCH") and caminho not in SEM_CHAVE:
                parametros.append({
                    "name": "Idempotency-Key", "in": "header", "required": True,
                    "schema": {"type": "string", "minLength": 1, "maxLength": 128},
                })
            documentacao = {
                "parameters": parametros,
                "responses": {"503": {"description": "Serviço temporariamente indisponível."}},
            }
            if prefixo == UNIDADE or caminho not in PUBLICAS:
                documentacao["security"] = [{"bearerAuth": []}]
            if caminho == "/explorar":
                documentacao["parameters"].append({
                    "name": "itemId", "in": "query", "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                })
            rotas.add_api_route(rota, criar_encaminhamento(prefixo, caminho), methods=[metodo],
                                name=f"{metodo} {rota}", openapi_extra=documentacao)
    app.include_router(rotas)
