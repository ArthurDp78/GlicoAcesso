"""Ambiente de integração: um banco por serviço, RabbitMQ real e cada serviço em seu próprio processo.

Requer GLICO_TESTE_PG (DSN administrativo de um PostgreSQL descartável) e GLICO_TESTE_RABBIT (URL AMQP
de um broker descartável). Os bancos `teste_*` são apagados e recriados. Sem as variáveis, os testes são pulados.
"""
import atexit
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from servicos.migracoes import SERVICOS, migrar


RAIZ = Path(__file__).resolve().parents[1]
UNIDADE = "10000000-0000-4000-8000-000000000001"
ITEM = "20000000-0000-4000-8000-000000000001"
TOKENS = {nome: f"token-de-teste-{nome}".ljust(40, "x") for nome in
          ("cidadao", "profissional", "reservas", "orquestrador", "retiradas", "admin")}
APPS = {"unidades": "unidades", "estoque": "estoque", "reservas": "reservas", "orquestrador": "orquestrador",
        "retiradas": "retiradas", "bff-cidadao": "bff_cidadao", "bff-unidade": "bff_unidade", "gateway": "gateway"}
processos: dict[str, subprocess.Popen] = {}
portas: dict[str, int] = {}
logs = Path(tempfile.mkdtemp(prefix="glico-testes-"))
cliente = httpx.Client(timeout=15, trust_env=False)
_preparado = False


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preparar() -> None:
    """Idempotente: o ambiente é compartilhado por todos os módulos da mesma execução."""
    global _preparado
    if _preparado:
        return
    admin, broker = os.environ.get("GLICO_TESTE_PG"), os.environ.get("GLICO_TESTE_RABBIT")
    if not admin or not broker:
        raise unittest.SkipTest("Defina GLICO_TESTE_PG e GLICO_TESTE_RABBIT para os testes de integração.")
    with psycopg.connect(admin, autocommit=True) as conexao:
        for servico in SERVICOS:
            nome = sql.Identifier(f"teste_{servico}")
            conexao.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(nome))
            conexao.execute(sql.SQL("CREATE DATABASE {}").format(nome))
    for servico, variavel in SERVICOS.items():
        os.environ[variavel] = psycopg.conninfo.make_conninfo(admin, dbname=f"teste_{servico}")
        migrar(servico, servico in ("unidades", "estoque"))
    for nome in APPS:
        portas[nome] = porta_livre()
        os.environ[nome.upper().replace("-", "_") + "_URL"] = url(nome)
    os.environ |= {
        "RABBITMQ_URL": broker, "GLICO_PROFISSIONAL_UNIDADE_ID": UNIDADE, "GLICO_FALHA_PREPARAR_AUTORIZACAO": "",
        "GLICO_EXPIRACAO_INTERVALO": "0.3",
        "GLICO_CIDADAO_TOKEN": TOKENS["cidadao"], "GLICO_PROFISSIONAL_TOKEN": TOKENS["profissional"],
        **{f"GLICO_{nome.upper()}_SERVICE_TOKEN": TOKENS[nome] for nome in ("reservas", "orquestrador", "retiradas", "admin")},
    }
    limpar_filas()
    for nome in ("reservas", "estoque", "retiradas"):
        proxies[nome] = Proxy(nome)
    for nome in APPS:
        subir(nome)
    _preparado = True


def limpar_filas() -> None:
    import pika
    from servicos import mensageria
    conexao = pika.BlockingConnection(pika.URLParameters(os.environ["RABBITMQ_URL"]))
    canal = conexao.channel()
    mensageria.declarar(canal)
    for fila in mensageria.todas_as_filas():
        canal.queue_purge(fila)
    conexao.close()


class Proxy:
    """Fica entre o Orquestrador (ou Retiradas) e um participante e injeta falhas por trecho de caminho."""

    def __init__(self, alvo: str):
        self.alvo, self.porta = alvo, porta_livre()
        self.perder: dict[str, int] = {}  # Executa no destino, mas perde a resposta.
        self.recusar: dict[str, int] = {}  # Responde 503 sem chegar ao destino.
        self.portoes: dict[str, threading.Event] = {}  # Segura a resposta já produzida até liberar.
        self.vistos: list[tuple[str, str, str | None]] = []
        proxy = self

        class Tratador(BaseHTTPRequestHandler):
            def atender(self):
                corpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                proxy.vistos.append((self.command, self.path, self.headers.get("Idempotency-Key")))
                if proxy.consumir(proxy.recusar, self.path):
                    return self.enviar(503, b"{}", "application/json")
                cabecalhos = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}
                try:
                    r = httpx.request(self.command, url(proxy.alvo) + self.path, headers=cabecalhos, content=corpo,
                                      timeout=10, trust_env=False)
                except httpx.HTTPError:
                    return self.enviar(502, b"{}", "application/json")
                for trecho, portao in list(proxy.portoes.items()):
                    if trecho in self.path:
                        portao.wait(15)
                if proxy.consumir(proxy.perder, self.path):
                    self.close_connection = True
                    return self.connection.close()
                self.enviar(r.status_code, r.content, r.headers.get("content-type", "application/json"))

            def enviar(self, status, conteudo, tipo):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", tipo)
                    if status != 204:
                        self.send_header("Content-Length", str(len(conteudo)))
                    self.end_headers()
                    if status != 204:
                        self.wfile.write(conteudo)
                except OSError:
                    pass

            do_GET = do_POST = do_DELETE = atender

            def log_message(self, *_):
                pass

        self.servidor = ThreadingHTTPServer(("127.0.0.1", self.porta), Tratador)
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def consumir(self, regras: dict[str, int], caminho: str) -> bool:
        for trecho, restantes in regras.items():
            if trecho in caminho and restantes > 0:
                regras[trecho] -= 1
                return True
        return False

    def limpar(self):
        self.perder.clear()
        self.recusar.clear()
        for portao in self.portoes.values():
            portao.set()
        self.portoes.clear()
        self.vistos.clear()


proxies: dict[str, Proxy] = {}


def desvios(nome: str) -> dict[str, str]:
    alvos = {"orquestrador": ("reservas", "estoque", "retiradas"), "retiradas": ("reservas",)}.get(nome, ())
    return {f"{alvo.upper()}_URL": f"http://127.0.0.1:{proxies[alvo].porta}" for alvo in alvos}


def url(nome: str) -> str:
    return f"http://127.0.0.1:{portas[nome]}"


def subir(nome: str, **ambiente: str) -> None:
    saida = open(logs / f"{nome}.log", "ab")
    processos[nome] = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"servicos.{APPS[nome]}.main:app", "--host", "127.0.0.1",
         "--port", str(portas[nome])], cwd=RAIZ, env={**os.environ, **desvios(nome), **ambiente}, stdout=saida, stderr=saida)
    esperar(lambda: saudavel(nome), 20, f"{nome} não subiu; veja {logs}")


def saudavel(nome: str) -> bool:
    try:
        return cliente.get(url(nome) + "/health").status_code == 200
    except httpx.HTTPError:
        return False


def matar(nome: str) -> None:
    processos[nome].kill()
    processos[nome].wait()


def encerrar() -> None:
    for processo in processos.values():
        processo.kill()
        processo.wait()


def esperar(condicao, limite: float = 20, mensagem: str = "condição não atingida"):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if (valor := condicao()):
            return valor
        time.sleep(0.1)
    raise AssertionError(mensagem)


def chamar(nome: str, metodo: str, caminho: str, token: str | None = None, chave: str | None = None, **opcoes):
    cabecalhos = dict(opcoes.pop("cabecalhos", {}))
    if token:
        cabecalhos["Authorization"] = f"Bearer {TOKENS.get(token, token)}"
    if chave:
        cabecalhos["Idempotency-Key"] = chave
    return cliente.request(metodo, url(nome) + caminho, headers=cabecalhos, **opcoes)


def nova_chave() -> str:
    return str(uuid4())


def consultar(servico: str, consulta: str, *parametros) -> list[dict]:
    with psycopg.connect(os.environ[SERVICOS[servico]], row_factory=dict_row, autocommit=True) as conexao:
        cursor = conexao.execute(consulta, parametros)
        return cursor.fetchall() if cursor.description else []






atexit.register(encerrar)


# --- Jornada comum ---

def criar_reserva(quantidade: int = 1, item: str = ITEM) -> str:
    resposta = chamar("gateway", "POST", "/api/cidadao/v1/reservas", "cidadao", nova_chave(),
                      json={"unidadeId": UNIDADE, "itemId": item, "quantidade": quantidade})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["reservaId"]


def aceitar(reserva: str, chave: str | None = None):
    return chamar("gateway", "POST", f"/api/unidade/v1/reservas/{reserva}/decisao", "profissional", chave or nova_chave(),
                  json={"decisao": "ACEITAR"})


def estado(reserva: str) -> str:
    return consultar("reservas", "SELECT status FROM reservas WHERE reserva_id = %s", reserva)[0]["status"]


def esperar_estado(reserva: str, *estados: str) -> str:
    return esperar(lambda: (atual := estado(reserva)) in estados and atual, 30, f"{reserva} não chegou a {estados}: {estado(reserva)}")


def confirmada(quantidade: int = 1, item: str = ITEM) -> str:
    reserva = criar_reserva(quantidade, item)
    assert aceitar(reserva).status_code == 202
    esperar_estado(reserva, "CONFIRMADA")
    esperar(lambda: not sagas(reserva, "encerrada_em IS NULL"))
    return reserva


def sagas(reserva: str, filtro: str = "true") -> list[dict]:
    return consultar("orquestrador", f"SELECT * FROM saga_execucoes WHERE reserva_id = %s AND {filtro} ORDER BY criada_em", reserva)


def saga_do_tipo(reserva: str, tipo: str) -> dict | None:
    linhas = [s for s in sagas(reserva) if s["tipo"] == tipo]
    return linhas[-1] if linhas else None


def cancelar_saga(reserva: str, token: str = "cidadao", chave: str | None = None, **opcoes):
    if token == "profissional":
        opcoes.setdefault("json", {"justificativa": "item avariado"})
    return chamar("orquestrador", "POST", f"/internal/v1/reservas/{reserva}/cancelamentos", token, chave or nova_chave(), **opcoes)


def autorizacao(reserva: str):
    return chamar("retiradas", "GET", f"/internal/v1/autorizacoes/{reserva}", "profissional")


def entregar(autorizacao_id: str, chave: str | None = None, token: str = "profissional"):
    return chamar("retiradas", "POST", "/api/unidade/v1/retiradas", token, chave or nova_chave(), json={"autorizacaoId": autorizacao_id})


def alocacao(reserva: str) -> dict | None:
    linhas = consultar("estoque", "SELECT * FROM alocacoes WHERE reserva_id = %s", reserva)
    return linhas[0] if linhas else None


def item_com_saldo(quantidade: int) -> str:
    item = chamar("estoque", "POST", "/internal/v1/itens", "admin", nova_chave(), json={"nome": "Item", "tipo": "INSUMO"}).json()["itemId"]
    base = f"/api/unidade/v1/estoque/{UNIDADE}/itens/{item}"
    chamar("estoque", "PUT", base + "/permissao", "profissional", nova_chave(), json={"permiteReserva": True})
    chamar("estoque", "POST", base + "/entradas", "profissional", nova_chave(), json={"quantidade": quantidade, "motivo": "teste"})
    return item


def saldo(item: str) -> tuple[int, int]:
    linha = consultar("estoque", "SELECT * FROM saldos WHERE item_id = %s", item)[0]
    return linha["estoque_fisico_atual"], linha["quantidade_alocada"]
