"""Devolve à fila de origem os eventos parados na fila de erros, depois de corrigida a causa.

uv run --locked python -m servicos.reprocessar estoque.baixa-retirada
O eventId e o corpo são preservados; a Inbox de cada consumidor continua deduplicando.
"""
import argparse
import os

import pika

from servicos import mensageria


def reprocessar(fila: str) -> int:
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@127.0.0.1:5672/%2F")
    conexao = pika.BlockingConnection(pika.URLParameters(url))
    try:
        canal = conexao.channel()
        mensageria.declarar(canal)
        canal.confirm_delivery()
        erros = mensageria.fila_de_erros(fila)
        # Só o total inicial: um evento que volte a falhar não é reprocessado em laço.
        total = canal.queue_declare(erros, passive=True).method.message_count
        movidos = 0
        for _ in range(total):
            metodo, propriedades, corpo = canal.basic_get(erros)
            if metodo is None:
                break
            canal.basic_publish("", fila, corpo, pika.BasicProperties(
                content_type=propriedades.content_type, delivery_mode=2, message_id=propriedades.message_id), mandatory=True)
            canal.basic_ack(metodo.delivery_tag)
            movidos += 1
        return movidos
    finally:
        conexao.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocessa os eventos da fila de erros de um consumidor.")
    parser.add_argument("fila", choices=[
        mensageria.FILA_PROJECAO, *mensageria.FILAS_RETIRADA, mensageria.FILA_RETIRADA_ESTOQUE_MAIN,
    ])
    print(f"Eventos devolvidos à fila: {reprocessar(parser.parse_args().fila)}.")


if __name__ == "__main__":
    main()
