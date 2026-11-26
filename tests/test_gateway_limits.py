"""Regressões dos limites de corpo aplicados pela borda."""
import asyncio
import unittest

from fastapi import HTTPException
from starlette.requests import Request

from servicos.gateway.rotas import LIMITE_CORPO_BYTES, ler_corpo_limitado


def request_with_chunks(chunks, content_length=None):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/teste", "raw_path": b"/api/teste",
        "query_string": b"", "headers": [] if content_length is None else
        [(b"content-length", str(content_length).encode())], "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
    }
    mensagens = iter([{"type": "http.request", "body": chunk, "more_body": True} for chunk in chunks]
                    + [{"type": "http.request", "body": b"", "more_body": False}])
    async def receive():
        return next(mensagens)
    return Request(scope, receive)


class LimiteCorpo(unittest.TestCase):
    def test_aceita_corpo_no_limite_em_chunks(self):
        corpo = b"x" * LIMITE_CORPO_BYTES
        recebido = asyncio.run(ler_corpo_limitado(request_with_chunks([corpo[:300_000], corpo[300_000:]])))
        self.assertEqual(recebido, corpo)

    def test_rejeita_content_length_grande_sem_consumir_corpo(self):
        with self.assertRaises(HTTPException) as erro:
            asyncio.run(ler_corpo_limitado(request_with_chunks([], LIMITE_CORPO_BYTES + 1)))
        self.assertEqual(erro.exception.status_code, 413)

    def test_rejeita_corpo_chunked_maior_que_limite(self):
        with self.assertRaises(HTTPException) as erro:
            asyncio.run(ler_corpo_limitado(request_with_chunks([b"x" * LIMITE_CORPO_BYTES, b"x"])))
        self.assertEqual(erro.exception.status_code, 413)
