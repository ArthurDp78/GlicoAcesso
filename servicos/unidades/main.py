from datetime import time
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from servicos.banco import BancoIndisponivel, conectar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import gestor_rede_autenticado, servico_reservas_autenticado


app = FastAPI(title="GlicoAcesso — Unidades")
BANCO = "UNIDADES_DATABASE_URL"
CADASTRAR_UNIDADE = "cadastrar-unidade"
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\x00]+$")]
TextoEndereco = Annotated[Texto, Field(max_length=120)]
TextoEnderecoCurto = Annotated[Texto, Field(max_length=40)]


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
    prazoAnaliseHoras: Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]

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


class UnidadeResumo(BaseModel):
    unidadeId: UUID
    nome: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str


@app.exception_handler(BancoIndisponivel)
async def responder_indisponibilidade(_request, _erro):
    return JSONResponse(status_code=503, content={"detail": "Banco de Unidades indisponível."})


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "unidades", "status": "ok"}


CONSULTA_UNIDADES = """
            SELECT u.unidade_id AS "unidadeId", u.nome,
                   concat(u.logradouro, ', ', u.numero, ' - ', u.bairro,
                          ', ', u.cidade, '/', u.estado, ' - CEP ', u.cep) AS endereco,
                   coalesce(agenda.horario, 'Horário não informado') AS "horarioAtendimento",
                   u.orientacoes_retirada AS "orientacoesRetirada", u.ativa,
                   u.prazo_analise_horas AS "prazoAnaliseHoras"
            FROM unidades AS u
            LEFT JOIN LATERAL (
                SELECT string_agg(
                    (ARRAY['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'])[h.dia_semana]
                    || ' ' || to_char(h.horario_inicial::interval, 'HH24:MI')
                    || '–' || to_char(h.horario_final::interval, 'HH24:MI'),
                    '; ' ORDER BY h.dia_semana, h.horario_inicial, h.horario_final
                ) AS horario
                FROM horarios_unidade AS h
                WHERE h.unidade_id = u.unidade_id
            ) AS agenda ON true
"""


class UnidadeCadastro(UnidadeResumo):
    ativa: bool
    prazoAnaliseHoras: int
    contatos: list[dict[str, str]]
    horarios: list[dict[str, int | str]]


@app.get("/api/cidadao/v1/unidades", response_model=list[UnidadeResumo])
def listar_unidades():
    with conectar(BANCO) as conexao:
        return conexao.execute(CONSULTA_UNIDADES + " WHERE u.ativa ORDER BY u.nome, u.unidade_id").fetchall()


@app.get(
    "/internal/v1/unidades/{unidadeId}", response_model=UnidadeCadastro,
    dependencies=[Depends(servico_reservas_autenticado)],
)
def consultar_unidade(unidadeId: UUID):
    with conectar(BANCO) as conexao:
        dados = carregar_cadastro(conexao, unidadeId)
        if dados is None:
            raise HTTPException(404, "Unidade não encontrada.")
        return dados


def carregar_cadastro(conexao, unidade_id: UUID):
    dados = conexao.execute(CONSULTA_UNIDADES + " WHERE u.unidade_id = %s", (unidade_id,)).fetchone()
    if dados is None:
        return None
    dados["contatos"] = conexao.execute("""
        SELECT tipo, valor FROM contatos_unidade WHERE unidade_id = %s ORDER BY tipo, valor
    """, (unidade_id,)).fetchall()
    dados["horarios"] = conexao.execute("""
        SELECT dia_semana AS "diaSemana", horario_inicial::text AS "horarioInicial",
               horario_final::text AS "horarioFinal"
        FROM horarios_unidade WHERE unidade_id = %s
        ORDER BY dia_semana, horario_inicial, horario_final
    """, (unidade_id,)).fetchall()
    return dados


def persistir_cadastro(pedido: UnidadeInput, gestor: str, chave: str):
    resumo = sha256(pedido.model_dump_json().encode()).hexdigest()
    with conectar(BANCO) as conexao:
        anterior = resultado_anterior(conexao, CADASTRAR_UNIDADE, gestor, chave, resumo)
        if anterior is not None:
            return anterior
        unidade_id = uuid4()
        try:
            with conexao.transaction():
                conexao.execute("""
                    INSERT INTO unidades (unidade_id, nome, logradouro, numero, bairro, cidade, estado, cep,
                                          orientacoes_retirada, prazo_analise_horas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (unidade_id, pedido.nome, pedido.logradouro, pedido.numero, pedido.bairro, pedido.cidade,
                      pedido.estado, pedido.cep, pedido.orientacoesRetirada, pedido.prazoAnaliseHoras))
        except UniqueViolation as erro:
            if erro.diag.constraint_name != "unidades_cadastro_unico":
                raise
            resultado = 409, {"codigo": "CADASTRO_DUPLICADO", "mensagem": "Já existe uma unidade com esse nome e endereço."}
        else:
            with conexao.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO contatos_unidade (unidade_id, tipo, valor) VALUES (%s, %s, %s)
                """, [(unidade_id, c.tipo, c.valor) for c in pedido.contatos])
                cursor.executemany("""
                    INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final)
                    VALUES (%s, %s, %s, %s)
                """, [(unidade_id, h.diaSemana, h.horarioInicial, h.horarioFinal) for h in pedido.horarios])
            cadastro = UnidadeCadastro.model_validate(carregar_cadastro(conexao, unidade_id))
            resultado = 201, cadastro.model_dump(mode="json")
        return gravar_resultado(conexao, CADASTRAR_UNIDADE, gestor, chave, resumo, resultado)


@app.post("/internal/v1/unidades", status_code=201, response_model=UnidadeCadastro)
def cadastrar_unidade(
    pedido: UnidadeInput,
    gestor: Annotated[str, Depends(gestor_rede_autenticado)],
    chave: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
):
    if not chave.strip() or "\x00" in chave:
        raise HTTPException(422, "Chave idempotente inválida.")
    status, corpo = persistir_cadastro(pedido, gestor, chave)
    return JSONResponse(status_code=status, content=corpo, headers={"Cache-Control": "no-store"})
