"""Persistência do cadastro de unidades e de seus detalhes."""
from uuid import UUID, uuid4

from servicos.unidades.esquemas import Contato, Horario, UnidadeCadastro, UnidadeInput


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


def listar_ativas(conexao):
    return conexao.execute(CONSULTA_UNIDADES + " WHERE u.ativa ORDER BY u.nome, u.unidade_id").fetchall()


def buscar_cadastro(conexao, unidade_id: UUID) -> dict | None:
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


def cadastro_json(conexao, unidade_id: UUID) -> dict:
    return UnidadeCadastro.model_validate(buscar_cadastro(conexao, unidade_id)).model_dump(mode="json")


def buscar_prazo_de_ativa(conexao, unidade_id: UUID):
    return conexao.execute("""
        SELECT prazo_analise_horas AS "prazoAnaliseHoras"
        FROM unidades WHERE unidade_id = %s AND ativa
    """, (unidade_id,)).fetchone()


def travar(conexao, unidade_id: UUID) -> bool:
    """Serializa alterações da mesma unidade; False se ela não existir."""
    return conexao.execute("SELECT 1 FROM unidades WHERE unidade_id = %s FOR UPDATE", (unidade_id,)).fetchone() is not None


def _substituir_contatos(conexao, unidade_id: UUID, contatos: list[Contato]) -> None:
    conexao.execute("DELETE FROM contatos_unidade WHERE unidade_id = %s", (unidade_id,))
    for contato in contatos:
        conexao.execute("INSERT INTO contatos_unidade (unidade_id, tipo, valor) VALUES (%s, %s, %s)",
                        (unidade_id, contato.tipo, contato.valor))


def _gravar_horarios(conexao, unidade_id: UUID, horarios: list[Horario]) -> None:
    conexao.execute("DELETE FROM horarios_unidade WHERE unidade_id = %s", (unidade_id,))
    for horario in horarios:
        conexao.execute("""
            INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final)
            VALUES (%s, %s, %s, %s)
        """, (unidade_id, horario.diaSemana, horario.horarioInicial, horario.horarioFinal))


def _valores(dados: UnidadeInput) -> tuple:
    return (dados.nome, dados.logradouro, dados.numero, dados.bairro, dados.cidade, dados.estado, dados.cep,
            dados.orientacoesRetirada, dados.prazoAnaliseHoras)


def inserir(conexao, dados: UnidadeInput) -> UUID:
    unidade_id = uuid4()
    conexao.execute("""
        INSERT INTO unidades (nome, logradouro, numero, bairro, cidade, estado, cep,
            orientacoes_retirada, prazo_analise_horas, unidade_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (*_valores(dados), unidade_id))
    _substituir_contatos(conexao, unidade_id, dados.contatos)
    _gravar_horarios(conexao, unidade_id, dados.horarios)
    return unidade_id


def atualizar(conexao, unidade_id: UUID, dados: UnidadeInput) -> None:
    conexao.execute("""
        UPDATE unidades SET nome = %s, logradouro = %s, numero = %s, bairro = %s, cidade = %s, estado = %s,
            cep = %s, orientacoes_retirada = %s, prazo_analise_horas = %s, prazo_legado = false, updated_at = now(),
            duplicidade_legada = duplicidade_legada
                AND identidade = identidade_unidade(%s, %s, %s, %s, %s, %s, %s)
        WHERE unidade_id = %s
    """, (*_valores(dados), *_valores(dados)[:7], unidade_id))
    _substituir_contatos(conexao, unidade_id, dados.contatos)
    _gravar_horarios(conexao, unidade_id, dados.horarios)


def substituir_horarios(conexao, unidade_id: UUID, horarios: list[Horario]) -> None:
    _gravar_horarios(conexao, unidade_id, horarios)
    conexao.execute("UPDATE unidades SET updated_at = now() WHERE unidade_id = %s", (unidade_id,))


def definir_status(conexao, unidade_id: UUID, ativa: bool) -> None:
    conexao.execute("UPDATE unidades SET ativa = %s, updated_at = now() WHERE unidade_id = %s", (ativa, unidade_id))


def definir_prazo(conexao, unidade_id: UUID, horas: int) -> None:
    conexao.execute("UPDATE unidades SET prazo_analise_horas = %s, prazo_legado = false, updated_at = now() WHERE unidade_id = %s",
                    (horas, unidade_id))
