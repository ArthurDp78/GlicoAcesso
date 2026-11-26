from datetime import time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from servicos.comandos import PRAZO_MAXIMO_HORAS, Texto
from servicos.unidades.regras_horarios import validar_periodo, validar_sobreposicoes


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnidadeResumo(BaseModel):
    unidadeId: UUID
    nome: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str


class UnidadeCadastro(UnidadeResumo):
    ativa: bool
    prazoAnaliseHoras: int
    contatos: list[dict[str, str]]
    horarios: list[dict[str, int | str]]


class Contato(Entrada):
    tipo: Texto
    valor: Texto


class Horario(Entrada):
    diaSemana: Annotated[int, Field(strict=True, ge=1, le=7)]
    horarioInicial: time
    horarioFinal: time

    @field_validator("horarioInicial", "horarioFinal", mode="before")
    @classmethod
    def em_texto(cls, valor):
        # O Pydantic aceitaria números como segundos; o contrato só admite texto.
        if not isinstance(valor, str):
            raise ValueError("horário deve ser texto")
        return valor

    @field_validator("horarioInicial", "horarioFinal")
    @classmethod
    def sem_fuso(cls, valor: time) -> time:
        if valor.tzinfo is not None:
            raise ValueError("horário de atendimento é local, sem fuso")
        return valor

    @model_validator(mode="after")
    def periodo_valido(self):
        validar_periodo(self.horarioInicial, self.horarioFinal)
        return self


def sem_repetidos(itens: list) -> list:
    # A chave primária dos detalhes não admite contatos exatamente duplicados.
    if len({item.model_dump_json() for item in itens}) < len(itens):
        raise ValueError("itens repetidos")
    return itens


class HorariosUnidade(Entrada):
    horarios: list[Horario]

    @field_validator("horarios")
    @classmethod
    def horarios_sem_sobreposicao(cls, valor):
        validar_sobreposicoes(valor)
        return valor


class PrazoAnalise(Entrada):
    prazoAnaliseHoras: Annotated[int, Field(strict=True, ge=1, le=PRAZO_MAXIMO_HORAS)]


class PrazoVigente(BaseModel):
    prazoAnaliseHoras: int


class StatusUnidade(Entrada):
    ativa: Annotated[bool, Field(strict=True)]


class UnidadeInput(HorariosUnidade, PrazoAnalise):
    nome: Texto
    logradouro: Texto
    numero: Texto
    bairro: Texto
    cidade: Texto
    estado: Texto
    cep: Annotated[str, StringConstraints(pattern=r"^[0-9]{5}-?[0-9]{3}$")]
    orientacoesRetirada: Texto
    contatos: list[Contato]

    @field_validator("cep")
    @classmethod
    def formatar_cep(cls, valor):
        digitos = valor.replace("-", "")
        return f"{digitos[:5]}-{digitos[5:]}"

    @field_validator("contatos")
    @classmethod
    def contatos_unicos(cls, valor):
        return sorted(sem_repetidos(valor), key=lambda contato: (contato.tipo, contato.valor))

    @field_validator("horarios")
    @classmethod
    def ordenar_horarios(cls, valor):
        return sorted(valor, key=lambda horario: (horario.diaSemana, horario.horarioInicial, horario.horarioFinal))
