"""Confere a tabela de decisão do executor da SAGA sem banco nem rede.

Execute na raiz: uv run --locked python -m tests.decisao_saga
"""
from servicos.orquestrador.executor import avancar


class ConexaoFalsa:
    def __init__(self):
        self.comandos = []

    def execute(self, consulta, parametros=None):
        self.comandos.append((" ".join(consulta.split()), parametros))
        return self


def decidir(etapa_id, status, corpo, comando=None):
    conexao = ConexaoFalsa()
    etapa = {"saga_id": "S", "reserva_id": "R", "etapa_id": etapa_id, "dados_comando": comando or {}}
    tratado = avancar(conexao, etapa, status, corpo)
    novas = [p[2] for c, p in conexao.comandos if c.startswith("INSERT INTO saga_etapas")]
    estados = [p[0] for c, p in conexao.comandos if c.startswith("UPDATE saga_execucoes SET estado")]
    return tratado, novas, estados


CASOS = [
    # (etapa, status, corpo, esperado: (tratado, novas etapas, estados da execução))
    ("ACEITAR_RESERVA", 200, {"unidadeId": "U", "itemId": "I", "quantidade": 2}, (True, ["ALOCAR_ESTOQUE"], [])),
    ("ACEITAR_RESERVA", 409, {"codigo": "ESTADO_INCOMPATIVEL"}, (True, [], ["INTERROMPIDA"])),
    ("ACEITAR_RESERVA", 403, {}, (True, [], ["INTERROMPIDA"])),
    ("ACEITAR_RESERVA", 409, {"codigo": "CHAVE_IDEMPOTENTE_CONFLITANTE"}, (False, [], [])),
    ("ALOCAR_ESTOQUE", 409, {"codigo": "SALDO_INSUFICIENTE"}, (True, ["FALHAR_CONFIRMACAO"], ["COMPENSANDO"])),
    ("ALOCAR_ESTOQUE", 409, {"codigo": "ALOCACAO_INCOMPATIVEL"}, (False, [], [])),
    ("PREPARAR_AUTORIZACAO", 201, {}, (True, ["CONFIRMAR_RESERVA"], [])),
    ("PREPARAR_AUTORIZACAO", 422, {"codigo": "AUTORIZACAO_NAO_CRIADA"}, (True, ["LIBERAR_ALOCACAO"], ["COMPENSANDO"])),
    ("PREPARAR_AUTORIZACAO", 422, {"detail": "validação"}, (False, [], [])),
    ("PREPARAR_AUTORIZACAO", 409, {"codigo": "AUTORIZACAO_INCOMPATIVEL"}, (True, ["CANCELAR_AUTORIZACAO"], ["COMPENSANDO"])),
    ("CONFIRMAR_RESERVA", 200, {}, (True, [], ["CONCLUIDA"])),
    ("CONFIRMAR_RESERVA", 409, {"codigo": "ESTADO_INCOMPATIVEL"}, (True, ["CANCELAR_AUTORIZACAO"], ["COMPENSANDO"])),
    ("CANCELAR_AUTORIZACAO", 404, {"codigo": "AUTORIZACAO_NAO_ENCONTRADA"}, (True, ["LIBERAR_ALOCACAO"], [])),
    ("CANCELAR_AUTORIZACAO", 409, {"codigo": "ENTREGA_JA_REGISTRADA",
                                   "retiradaId": "209bce60-dd8b-4d27-ae48-5f343cf39e80"}, (True, [], ["INTERROMPIDA"])),
    ("CANCELAR_AUTORIZACAO", 409, {"codigo": "ENTREGA_JA_REGISTRADA"}, (False, [], [])),
    ("INICIAR_CANCELAMENTO", 200, {}, (True, ["REVOGAR_PARA_CANCELAR"], [])),
    ("INICIAR_CANCELAMENTO", 409, {"codigo": "ESTADO_INCOMPATIVEL"}, (True, [], ["INTERROMPIDA"])),
    ("REVOGAR_PARA_CANCELAR", 200, {}, (True, ["LIBERAR_PARA_CANCELAR"], [])),
    ("REVOGAR_PARA_CANCELAR", 409, {"codigo": "ENTREGA_JA_REGISTRADA", "retiradaId": "R"},
     (True, [], ["INTERROMPIDA"])),
    ("LIBERAR_PARA_CANCELAR", 204, {}, (True, ["FINALIZAR_CANCELAMENTO"], [])),
    ("FINALIZAR_CANCELAMENTO", 200, {}, (True, [], ["CANCELADA"])),
    ("LIBERAR_ALOCACAO", 204, {}, (True, ["FALHAR_CONFIRMACAO"], [])),
    ("LIBERAR_ALOCACAO", 409, {"codigo": "ALOCACAO_CONSUMIDA"}, (False, [], [])),
    ("FALHAR_CONFIRMACAO", 200, {}, (True, [], ["COMPENSADA"])),
]

for etapa_id, status, corpo, esperado in CASOS:
    obtido = decidir(etapa_id, status, corpo)
    assert obtido == esperado, f"{etapa_id} {status} {corpo}: {obtido} != {esperado}"
assert decidir("ALOCAR_ESTOQUE", 201, {}, {"corpo": {"x": 1}}) == (True, ["PREPARAR_AUTORIZACAO"], [])
print(f"{len(CASOS) + 1} casos da tabela de decisão conferidos.")
