from uuid import UUID

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from servicos.banco import BancoIndisponivel, conectar


app = FastAPI(title="GlicoAcesso — Unidades")


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


@app.get("/api/cidadao/v1/unidades", response_model=list[UnidadeResumo])
def listar_unidades():
    with conectar("UNIDADES_DATABASE_URL") as conexao:
        return conexao.execute("""
            SELECT u.unidade_id AS "unidadeId", u.nome,
                   concat(u.logradouro, ', ', u.numero, ' - ', u.bairro,
                          ', ', u.cidade, '/', u.estado, ' - CEP ', u.cep) AS endereco,
                   coalesce(agenda.horario, 'Horário não informado') AS "horarioAtendimento",
                   u.orientacoes_retirada AS "orientacoesRetirada"
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
            WHERE u.ativa
            ORDER BY u.nome, u.unidade_id
        """).fetchall()
