from datetime import time
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, StringConstraints, field_validator, model_validator


Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\x00]+$")]
TextoEndereco = Annotated[Texto, Field(max_length=120)]
TextoEnderecoCurto = Annotated[Texto, Field(max_length=40)]


PRAZO_MAXIMO_HORAS = 720
PrazoAnalise = Annotated[int, Field(strict=True, ge=1, le=PRAZO_MAXIMO_HORAS)]


class ContatoInput(BaseModel):
    tipo: TextoEnderecoCurto
    valor: Annotated[Texto, Field(max_length=400)]


class HorarioInput(BaseModel):
    diaSemana: Annotated[int, Field(strict=True, ge=1, le=7)]
    horarioInicial: time
    horarioFinal: time

    @field_validator("horarioInicial", "horarioFinal", mode="before")
    @classmethod
    def exigir_texto(cls, valor):
        if not isinstance(valor, str):
            raise ValueError("Informe o horário como texto.")
        return valor

    @model_validator(mode="after")
    def validar_intervalo(self):
        if self.horarioInicial.tzinfo or self.horarioFinal.tzinfo or self.horarioInicial >= self.horarioFinal:
            raise ValueError("O horário deve terminar depois de começar no mesmo dia, sem fuso.")
        return self


class UnidadeInput(BaseModel):
    nome: TextoEndereco
    logradouro: TextoEndereco
    numero: TextoEnderecoCurto
    bairro: TextoEndereco
    cidade: TextoEndereco
    estado: TextoEnderecoCurto
    cep: Annotated[str, StringConstraints(pattern=r"^[0-9]{5}-?[0-9]{3}$")]
    orientacoesRetirada: Texto
    contatos: list[ContatoInput]
    horarios: list[HorarioInput]
    prazoAnaliseHoras: PrazoAnalise

    @field_validator("cep")
    @classmethod
    def formatar_cep(cls, valor: str) -> str:
        digitos = valor.replace("-", "")
        return f"{digitos[:5]}-{digitos[5:]}"

    @model_validator(mode="after")
    def ordenar_e_validar_listas(self):
        contatos = {(contato.tipo, contato.valor): contato for contato in self.contatos}
        horarios = {(h.diaSemana, h.horarioInicial, h.horarioFinal): h for h in self.horarios}
        if len(contatos) != len(self.contatos) or len(horarios) != len(self.horarios):
            raise ValueError("Contatos e horários não podem se repetir no cadastro.")
        self.contatos = [contatos[chave] for chave in sorted(contatos)]
        self.horarios = [horarios[chave] for chave in sorted(horarios)]
        return self


class HorariosUnidade(BaseModel):
    horarios: list[HorarioInput]

    @field_validator("horarios")
    @classmethod
    def ordenar_horarios(cls, horarios: list[HorarioInput]) -> list[HorarioInput]:
        por_intervalo = {(h.diaSemana, h.horarioInicial, h.horarioFinal): h for h in horarios}
        if len(por_intervalo) != len(horarios):
            raise ValueError("Os horários não podem se repetir.")
        return [por_intervalo[chave] for chave in sorted(por_intervalo)]


class SituacaoUnidade(BaseModel):
    ativa: StrictBool


class PrazoUnidade(BaseModel):
    prazoAnaliseHoras: PrazoAnalise
