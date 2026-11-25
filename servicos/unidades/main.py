import os
from hashlib import sha256
from hmac import compare_digest
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from psycopg.errors import UniqueViolation
from pydantic import BaseModel

from servicos.contratos_unidade import HorariosUnidade, PrazoUnidade, SituacaoUnidade, UnidadeInput

from servicos.banco import BancoIndisponivel, conectar
from servicos.idempotencia import gravar_resultado, resultado_anterior
from servicos.identidade_demo import (
    Ator, Credencial, ator_autenticado, gestor_rede_autenticado, profissional_autenticado, servico_reservas_autenticado,
)


app = FastAPI(title="GlicoAcesso — Unidades")
BANCO = "UNIDADES_DATABASE_URL"
CADASTRAR_UNIDADE = "cadastrar-unidade"
Chave = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
Profissional = Annotated[Ator, Depends(profissional_autenticado)]


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


def autorizar_consulta(unidadeId: UUID, credencial: Credencial):
    token_servico = os.getenv("GLICO_RESERVAS_SERVICE_TOKEN", "")
    if credencial and len(token_servico) >= 32 and compare_digest(
        token_servico.encode(), credencial.credentials.encode(),
    ):
        servico_reservas_autenticado(credencial)
        return
    if profissional_autenticado(ator_autenticado(credencial)).unidadeId != unidadeId:
        raise HTTPException(403, "Ator sem acesso à unidade.")


@app.get(
    "/internal/v1/unidades/{unidadeId}", response_model=UnidadeCadastro,
    dependencies=[Depends(autorizar_consulta)],
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
            substituir_horarios(conexao, unidade_id, pedido.horarios)
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


def substituir_horarios(conexao, unidade_id, horarios):
    conexao.execute("DELETE FROM horarios_unidade WHERE unidade_id = %s", (unidade_id,))
    with conexao.cursor() as cursor:
        cursor.executemany("""
            INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final)
            VALUES (%s, %s, %s, %s)
        """, [(unidade_id, h.diaSemana, h.horarioInicial, h.horarioFinal) for h in horarios])


def aplicar_manutencao(conexao, unidade_id, pedido):
    if isinstance(pedido, UnidadeInput):
        conexao.execute("""
            UPDATE unidades SET nome = %s, logradouro = %s, numero = %s, bairro = %s, cidade = %s,
                                estado = %s, cep = %s, orientacoes_retirada = %s, prazo_analise_horas = %s,
                                updated_at = clock_timestamp()
            WHERE unidade_id = %s
        """, (pedido.nome, pedido.logradouro, pedido.numero, pedido.bairro, pedido.cidade, pedido.estado,
              pedido.cep, pedido.orientacoesRetirada, pedido.prazoAnaliseHoras, unidade_id))
        conexao.execute("DELETE FROM contatos_unidade WHERE unidade_id = %s", (unidade_id,))
        with conexao.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO contatos_unidade (unidade_id, tipo, valor) VALUES (%s, %s, %s)
            """, [(unidade_id, c.tipo, c.valor) for c in pedido.contatos])
        substituir_horarios(conexao, unidade_id, pedido.horarios)
    elif isinstance(pedido, HorariosUnidade):
        substituir_horarios(conexao, unidade_id, pedido.horarios)
        conexao.execute("UPDATE unidades SET updated_at = clock_timestamp() WHERE unidade_id = %s", (unidade_id,))
    elif isinstance(pedido, SituacaoUnidade):
        conexao.execute("UPDATE unidades SET ativa = %s, updated_at = clock_timestamp() WHERE unidade_id = %s",
                        (pedido.ativa, unidade_id))
    else:
        conexao.execute("""
            UPDATE unidades SET prazo_analise_horas = %s, updated_at = clock_timestamp() WHERE unidade_id = %s
        """, (pedido.prazoAnaliseHoras, unidade_id))


def manter_unidade(unidade_id, pedido, profissional, chave, operacao):
    if profissional.unidadeId != unidade_id:
        raise HTTPException(403, "Ator sem acesso à unidade.")
    if not chave.strip() or "\x00" in chave:
        raise HTTPException(422, "Chave idempotente inválida.")
    resumo = sha256(f"{unidade_id}:{pedido.model_dump_json()}".encode()).hexdigest()
    with conectar(BANCO) as conexao:
        resultado = resultado_anterior(conexao, operacao, profissional.id, chave, resumo)
        if resultado is None:
            existente = conexao.execute(
                "SELECT 1 FROM unidades WHERE unidade_id = %s FOR UPDATE", (unidade_id,),
            ).fetchone()
            if existente is None:
                raise HTTPException(404, "Unidade não encontrada.")
            try:
                with conexao.transaction():
                    aplicar_manutencao(conexao, unidade_id, pedido)
            except UniqueViolation as erro:
                if erro.diag.constraint_name != "unidades_cadastro_unico":
                    raise
                resultado = 409, {"codigo": "CADASTRO_DUPLICADO", "mensagem": "Já existe uma unidade com esse nome e endereço."}
            else:
                cadastro = UnidadeCadastro.model_validate(carregar_cadastro(conexao, unidade_id))
                resultado = 200, cadastro.model_dump(mode="json")
            gravar_resultado(conexao, operacao, profissional.id, chave, resumo, resultado)
    return JSONResponse(resultado[1], status_code=resultado[0], headers={"Cache-Control": "no-store"})


@app.put("/internal/v1/unidades/{unidadeId}", response_model=UnidadeCadastro)
def atualizar_unidade(unidadeId: UUID, pedido: UnidadeInput, profissional: Profissional, chave: Chave):
    return manter_unidade(unidadeId, pedido, profissional, chave, "atualizar-cadastro")


@app.put("/internal/v1/unidades/{unidadeId}/horarios", response_model=UnidadeCadastro)
def atualizar_horarios(unidadeId: UUID, pedido: HorariosUnidade, profissional: Profissional, chave: Chave):
    return manter_unidade(unidadeId, pedido, profissional, chave, "atualizar-horarios")


@app.patch("/internal/v1/unidades/{unidadeId}/status", response_model=UnidadeCadastro)
def atualizar_situacao(unidadeId: UUID, pedido: SituacaoUnidade, profissional: Profissional, chave: Chave):
    return manter_unidade(unidadeId, pedido, profissional, chave, "atualizar-situacao")


@app.get("/internal/v1/unidades/{unidadeId}/prazo-analise", response_model=PrazoUnidade,
         dependencies=[Depends(servico_reservas_autenticado)])
def consultar_prazo(unidadeId: UUID):
    with conectar(BANCO) as conexao:
        prazo = conexao.execute("""
            SELECT prazo_analise_horas AS "prazoAnaliseHoras" FROM unidades WHERE unidade_id = %s AND ativa
        """, (unidadeId,)).fetchone()
    if prazo is None:
        raise HTTPException(404, "Unidade ativa não encontrada.")
    return prazo


@app.put("/internal/v1/unidades/{unidadeId}/prazo-analise", response_model=UnidadeCadastro)
def atualizar_prazo(unidadeId: UUID, pedido: PrazoUnidade, profissional: Profissional, chave: Chave):
    return manter_unidade(unidadeId, pedido, profissional, chave, "atualizar-prazo")
