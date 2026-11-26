"""Invariantes dos períodos de atendimento de uma unidade."""
from datetime import time
from itertools import pairwise


def validar_periodo(inicial: time, final: time) -> None:
    # Recusa também duração nula e períodos que atravessariam (ou terminariam à) meia-noite.
    if inicial >= final:
        raise ValueError("o horário inicial deve ser anterior ao final, no mesmo dia")


def validar_sobreposicoes(horarios: list) -> None:
    """Períodos semiabertos: o fim de um pode coincidir com o início do seguinte."""
    ordenados = sorted(horarios, key=lambda h: (h.diaSemana, h.horarioInicial, h.horarioFinal))
    for anterior, seguinte in pairwise(ordenados):
        if anterior.diaSemana == seguinte.diaSemana and seguinte.horarioInicial < anterior.horarioFinal:
            raise ValueError(f"há períodos sobrepostos no dia {anterior.diaSemana}")
