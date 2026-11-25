"""Executor das etapas da SAGA de confirmação e de cancelamento.

Cada etapa é uma intenção durável (método, caminho, corpo e chave) gravada antes da chamada.
O executor trava a etapa e a execução (FOR UPDATE SKIP LOCKED), chama o participante e grava o
resultado e a próxima etapa na mesma transação. Resposta incerta repete o mesmo comando com backoff.
"""
import logging
import os
import threading

import httpx
from servicos.banco import conectar
from servicos.http import falha_de_configuracao
from servicos.orquestrador.cancelamento import (
    INICIAR, ativar_pedido, avancar_cancelamento, interpor, pedido_pendente, resolver_interposta,
)
from servicos.orquestrador.registro import BANCO, concluir_etapa, mudar_estado, nova_etapa


SERVICOS = {
    "reservas": ("RESERVAS_URL", "http://127.0.0.1:8004"),
    "estoque": ("ESTOQUE_URL", "http://127.0.0.1:8003"),
    "retiradas": ("RETIRADAS_URL", "http://127.0.0.1:8007"),
}
BACKOFF_MAXIMO = 30
log = logging.getLogger("uvicorn.error")


def emitir(conexao, etapa, pedido, etapa_id, destino, caminho, corpo):
    """Grava o próximo passo da confirmação, salvo se um cancelamento aguardar sua vez."""
    if pedido is not None:
        interpor(conexao, etapa["saga_id"], pedido)
    else:
        nova_etapa(conexao, etapa["saga_id"], etapa_id, destino, "POST", caminho, corpo)


def retomar_confirmacao(conexao, etapa):
    """Cancelamento recusado: emite o passo que havia sido pausado, a partir dos resultados já gravados."""
    saga = etapa["saga_id"]
    feitas = {linha["etapa_id"]: linha for linha in conexao.execute("""
        SELECT etapa_id, dados_comando, resultado FROM saga_etapas WHERE saga_id = %s AND estado_tecnico = 'CONCLUIDA'
    """, (saga,)).fetchall()}
    if "PREPARAR_AUTORIZACAO" in feitas:
        ultima = {**etapa, "etapa_id": "PREPARAR_AUTORIZACAO"}
    elif "ALOCAR_ESTOQUE" in feitas:
        ultima = {**etapa, "etapa_id": "ALOCAR_ESTOQUE"}
    else:
        ultima = {**etapa, "etapa_id": "ACEITAR_RESERVA"}
    registro = feitas[ultima["etapa_id"]]
    ultima["dados_comando"] = registro["dados_comando"]
    avancar(conexao, ultima, registro["resultado"]["status"], registro["resultado"]["corpo"])


def avancar(conexao, etapa, status: int, corpo: dict, pedido=None) -> bool:
    """Decide a próxima etapa a partir de um resultado conclusivo. False = resultado não tratado (repetir)."""
    if etapa.get("tipo") == "CANCELAMENTO":
        return avancar_cancelamento(conexao, etapa, status, corpo)
    if etapa["etapa_id"].startswith(f"{INICIAR}:"):
        return resolver_interposta(conexao, etapa, status, corpo, lambda: retomar_confirmacao(conexao, etapa))
    saga, reserva = etapa["saga_id"], etapa["reserva_id"]
    codigo = corpo.get("codigo")
    comando_saga = {"sagaId": str(saga)}
    cabecalho_saga = {"X-Saga-Id": str(saga)}

    def compensar(primeira: str):
        mudar_estado(conexao, saga, "COMPENSANDO", codigo)
        etapas[primeira]()

    etapas = {
        "FALHAR_CONFIRMACAO": lambda: nova_etapa(conexao, saga, "FALHAR_CONFIRMACAO", "reservas", "POST",
                                                 f"/internal/v1/reservas/{reserva}/falhar-confirmacao", comando_saga),
        "LIBERAR_ALOCACAO": lambda: nova_etapa(conexao, saga, "LIBERAR_ALOCACAO", "estoque", "DELETE",
                                               f"/internal/v1/alocacoes/{reserva}", None, cabecalho_saga),
        "CANCELAR_AUTORIZACAO": lambda: nova_etapa(conexao, saga, "CANCELAR_AUTORIZACAO", "retiradas", "POST",
                                                   f"/internal/v1/autorizacoes/{reserva}/cancelar", None, cabecalho_saga),
    }
    match etapa["etapa_id"], status, codigo:
        case "ACEITAR_RESERVA", 200, _:
            dados = {"sagaId": str(saga), "reservaId": str(reserva), "unidadeId": corpo["unidadeId"],
                     "itemId": corpo["itemId"], "quantidade": corpo["quantidade"]}
            emitir(conexao, etapa, pedido, "ALOCAR_ESTOQUE", "estoque", "/internal/v1/alocacoes", dados)
        case ("ACEITAR_RESERVA", 403 | 404, _) | ("ACEITAR_RESERVA", 409, "ESTADO_INCOMPATIVEL"):
            # Aceite recusado sem efeitos distribuídos: nada a compensar.
            mudar_estado(conexao, saga, "INTERROMPIDA", codigo or f"HTTP_{status}", encerrar=True)
        case "ALOCAR_ESTOQUE", 201, _:
            emitir(conexao, etapa, pedido, "PREPARAR_AUTORIZACAO", "retiradas", "/internal/v1/autorizacoes",
                   etapa["dados_comando"]["corpo"])
        case ("ALOCAR_ESTOQUE", 404, _) | ("ALOCAR_ESTOQUE", 409, "SALDO_INSUFICIENTE" | "RESERVA_NAO_PERMITIDA"):
            compensar("FALHAR_CONFIRMACAO")  # Nada foi alocado.
        case "PREPARAR_AUTORIZACAO", 201, _:
            emitir(conexao, etapa, pedido, "CONFIRMAR_RESERVA", "reservas",
                   f"/internal/v1/reservas/{reserva}/confirmar", comando_saga)
        case "PREPARAR_AUTORIZACAO", 422, "AUTORIZACAO_NAO_CRIADA":
            compensar("LIBERAR_ALOCACAO")  # Prova de que não há autorização: só liberar.
        case ("PREPARAR_AUTORIZACAO", 409, "AUTORIZACAO_INCOMPATIVEL") | ("CONFIRMAR_RESERVA", 409, "ESTADO_INCOMPATIVEL"):
            compensar("CANCELAR_AUTORIZACAO")  # A autorização pode existir: revogar antes de liberar.
        case "CONFIRMAR_RESERVA", 200, _:
            mudar_estado(conexao, saga, "CONCLUIDA", encerrar=True)
        case "CANCELAR_AUTORIZACAO", 200, _:
            etapas["LIBERAR_ALOCACAO"]()
        case "CANCELAR_AUTORIZACAO", 404, "AUTORIZACAO_NAO_ENCONTRADA" if not etapa.get("autorizacao_criada"):
            # Só prova que nunca existiu quando a preparação já reconciliada também não a criou.
            etapas["LIBERAR_ALOCACAO"]()
        case "LIBERAR_ALOCACAO", 204, _:
            etapas["FALHAR_CONFIRMACAO"]()
        case "FALHAR_CONFIRMACAO", 200, _:
            mudar_estado(conexao, saga, "COMPENSADA", encerrar=True)
        case _:
            return False
    return True


def chamar(cliente: httpx.Client, etapa) -> tuple[int | None, dict, str | None]:
    comando = etapa["dados_comando"]
    variavel, padrao = SERVICOS[etapa["destino"]]
    cabecalhos = {
        "Authorization": "Bearer " + os.environ.get("GLICO_ORQUESTRADOR_SERVICE_TOKEN", ""),
        "Idempotency-Key": etapa["idempotency_key"],
        "X-Correlation-Id": str(etapa["correlation_id"]),
        **comando["cabecalhos"],
    }
    try:
        resposta = cliente.request(comando["metodo"], os.environ.get(variavel, padrao).rstrip("/") + comando["caminho"],
                                   json=comando["corpo"], headers=cabecalhos)
    except httpx.HTTPError as erro:
        return None, {}, f"{type(erro).__name__}: resultado incerto"
    if resposta.status_code >= 500 or falha_de_configuracao(resposta):
        return None, {}, f"HTTP {resposta.status_code}"
    try:
        corpo = resposta.json() if resposta.content else {}
    except ValueError:
        corpo = {}
    return resposta.status_code, corpo if isinstance(corpo, dict) else {}, None


def executar_uma(cliente: httpx.Client) -> bool:
    with conectar(BANCO) as conexao:
        etapa = conexao.execute("""
            SELECT e.saga_id, e.etapa_id, e.destino, e.idempotency_key, e.dados_comando, e.tentativas,
                   s.reserva_id, s.correlation_id, s.estado, s.tipo, s.resultado AS dados_execucao,
                   EXISTS (SELECT 1 FROM saga_etapas p WHERE p.saga_id = s.saga_id AND p.etapa_id = 'PREPARAR_AUTORIZACAO'
                           AND p.estado_tecnico = 'CONCLUIDA') AS autorizacao_criada
            FROM saga_etapas e JOIN saga_execucoes s USING (saga_id)
            WHERE e.estado_tecnico = 'PENDENTE' AND e.proximo_retry_em <= now() AND s.encerrada_em IS NULL
            ORDER BY e.proximo_retry_em
            LIMIT 1
            FOR NO KEY UPDATE OF e, s SKIP LOCKED
        """).fetchone()
        if etapa is None:
            return False
        # A chamada ocorre com a etapa travada: só este trabalhador decide o passo seguinte.
        try:
            status, corpo, erro = chamar(cliente, etapa)
            with conexao.transaction():  # Decisão parcial é desfeita; a etapa só recebe backoff.
                # Lido depois da chamada: um pedido feito durante ela já pausa o passo seguinte.
                pedido = pedido_pendente(conexao, etapa["reserva_id"])
                tratado = status is not None and avancar(conexao, etapa, status, corpo, pedido)
        except Exception as falha:
            log.exception("SAGA %s: erro ao processar %s", etapa["saga_id"], etapa["etapa_id"])
            status, corpo, erro, tratado = None, {}, f"{type(falha).__name__} ao processar o resultado", False
        if tratado:
            concluir_etapa(conexao, etapa["saga_id"], etapa["etapa_id"], status, corpo)
            conexao.execute("""
                UPDATE saga_execucoes SET atualizada_em = now(), estado = CASE estado
                    WHEN 'COMPENSACAO_PENDENTE' THEN 'COMPENSANDO' ELSE 'CANCELANDO' END
                WHERE saga_id = %s AND estado IN ('COMPENSACAO_PENDENTE', 'CANCELAMENTO_PENDENTE')
            """, (etapa["saga_id"],))
            log.info("SAGA %s: %s -> HTTP %s", etapa["saga_id"], etapa["etapa_id"], status)
            return True
        espera = min(2 ** min(etapa["tentativas"], 5), BACKOFF_MAXIMO)
        erro = erro or f"HTTP {status} {corpo.get('codigo', '')} sem tratamento conclusivo".strip()
        conexao.execute("""
            UPDATE saga_etapas SET tentativas = tentativas + 1, ultima_tentativa_em = now(),
                proximo_retry_em = now() + make_interval(secs => %s), erro_tecnico = %s, atualizada_em = now()
            WHERE saga_id = %s AND etapa_id = %s
        """, (espera, erro[:500], etapa["saga_id"], etapa["etapa_id"]))
        if etapa["estado"] == "COMPENSANDO":
            mudar_estado(conexao, etapa["saga_id"], "COMPENSACAO_PENDENTE")
        elif etapa["estado"] == "CANCELANDO":
            mudar_estado(conexao, etapa["saga_id"], "CANCELAMENTO_PENDENTE")
        log.warning("SAGA %s: %s nova tentativa em %ss (%s)", etapa["saga_id"], etapa["etapa_id"], espera, erro)
        return True


def laco(parar: threading.Event) -> None:
    with httpx.Client(timeout=4.0, trust_env=False) as cliente:
        while not parar.is_set():
            try:
                etapa, pedido = executar_uma(cliente), ativar_pedido()
                trabalhou = etapa or pedido
            except Exception:  # O laço não pode morrer: a etapa continua pendente e será retomada.
                log.exception("Falha no executor da SAGA")
                trabalhou = False
            if not trabalhou:
                parar.wait(0.5)
