import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, TypeAdapter, ValidationError

from servicos.bff import INDISPONIVEL, RespostaRecusada, Servicos, criar_app, encaminhar
from servicos.comandos import Chave
from servicos.contratos_reserva import CANCELAVEIS, DadosReserva, LinkReserva, PedidoReserva, ReservaPublica
from servicos.erros import entrada_invalida_400
from servicos.identidade_demo import TOKEN_BFF_CIDADAO, TOKEN_CIDADAO, Ator, ator_autenticado


app = criar_app("GlicoAcesso — BFF Cidadão", TOKEN_CIDADAO, TOKEN_BFF_CIDADAO)
API = "/api/cidadao/v1"
entrada_invalida_400(app, API + "/reservas/{reservaId}/cancelar")


def cidadao(ator: Annotated[Ator, Depends(ator_autenticado)]) -> Ator:
    if ator.papel != "CIDADAO":
        raise HTTPException(403, "Operação exclusiva do cidadão.")
    return ator


Cidadao = Annotated[Ator, Depends(cidadao)]


class Unidade(BaseModel):
    unidadeId: UUID
    nome: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str


class Item(BaseModel):
    itemId: UUID
    nome: str
    tipo: Literal["MEDICAMENTO", "INSUMO"]


class Disponibilidade(BaseModel):
    quantidadeDisponivel: int
    permiteReserva: bool
    atualizadoEm: str


class UnidadeDisponivel(BaseModel):
    unidadeId: UUID
    nomeUnidade: str
    endereco: str
    horarioAtendimento: str
    orientacoesRetirada: str
    disponivel: bool
    permiteReserva: bool
    atualizadoEm: str


ITENS = TypeAdapter(list[Item])
UNIDADES = TypeAdapter(list[Unidade])
UNIDADE = TypeAdapter(Unidade)
DISPONIBILIDADE = TypeAdapter(Disponibilidade)


def servicos_do_bff(request: Request) -> Servicos:
    return Servicos(request, TOKEN_BFF_CIDADAO)


DoBff = Annotated[Servicos, Depends(servicos_do_bff)]


@app.get("/health")
def verificar_saude() -> dict[str, str]:
    return {"servico": "bff-cidadao", "status": "ok"}


@app.get(API + "/itens", response_model=list[Item])
async def listar_itens(servicos: DoBff):
    return await servicos.obter("estoque", API + "/estoque/itens", ITENS, publico=True)


@app.get(API + "/unidades", response_model=list[Unidade])
async def listar_unidades(servicos: DoBff):
    return await servicos.obter("unidades", API + "/unidades", UNIDADES, publico=True)


@app.get(API + "/explorar", response_model=list[UnidadeDisponivel])
async def explorar(servicos: DoBff, itemId: UUID):
    unidades = await listar_unidades(servicos)
    limite = asyncio.Semaphore(12)

    async def combinar(unidade: Unidade) -> UnidadeDisponivel | None:
        try:
            async with limite:
                dado = await servicos.obter("estoque", API + "/estoque/disponibilidade", DISPONIBILIDADE, publico=True,
                                            params={"unidadeId": str(unidade.unidadeId), "itemId": str(itemId)})
        except RespostaRecusada as erro:
            if erro.resposta.status_code == 404:  # Combinação sem projeção: omitida do resultado.
                return None
            raise
        return UnidadeDisponivel(
            unidadeId=unidade.unidadeId,
            nomeUnidade=unidade.nome,
            endereco=unidade.endereco,
            horarioAtendimento=unidade.horarioAtendimento,
            orientacoesRetirada=unidade.orientacoesRetirada,
            disponivel=dado.quantidadeDisponivel > 0,
            permiteReserva=dado.permiteReserva,
            atualizadoEm=dado.atualizadoEm,
        )

    resultados = await asyncio.gather(*(combinar(unidade) for unidade in unidades))
    return [resultado for resultado in resultados if resultado is not None]


# --- Reservas do cidadão ---

DADOS_RESERVA = TypeAdapter(DadosReserva)


def apresentar(conteudo: bytes, **complementos) -> ReservaPublica:
    try:
        dados = DADOS_RESERVA.validate_json(conteudo, extra="ignore")
    except ValidationError as erro:
        raise HTTPException(503, INDISPONIVEL) from erro
    href = f"{API}/reservas/{dados.reservaId}"
    links = {"self": LinkReserva(href=href, method="GET")}
    if dados.status in CANCELAVEIS:
        links["cancelar"] = LinkReserva(href=href + "/cancelar", method="POST")
    return ReservaPublica(**dados.model_dump(), **complementos, links=links)


async def dados_da_reserva(servicos: Servicos, metodo: str, caminho: str, esperado: int, corpo: bytes | None = None) -> bytes:
    resposta = await servicos.chamar("reservas", metodo, caminho, corpo=corpo)
    if resposta.status_code != esperado:
        raise RespostaRecusada(resposta)
    return resposta.content


@app.post(API + "/reservas", status_code=201, response_model=ReservaPublica, response_model_exclude_none=True)
async def criar_reserva(request: Request, response: Response, pedido: PedidoReserva, cidadao: Cidadao, chave: Chave):
    servicos = Servicos(request, TOKEN_BFF_CIDADAO, cidadao, chave)
    reserva = apresentar(await dados_da_reserva(servicos, "POST", API + "/reservas", 201, pedido.model_dump_json().encode()))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Location"] = reserva.links["self"].href
    return reserva


@app.get(API + "/reservas/{reservaId}", response_model=ReservaPublica, response_model_exclude_none=True)
async def consultar_reserva(request: Request, response: Response, reservaId: UUID, cidadao: Cidadao, do_bff: DoBff):
    response.headers["Cache-Control"] = "no-store"
    servicos = Servicos(request, TOKEN_BFF_CIDADAO, cidadao)
    # Reservas verifica a propriedade antes de qualquer dado complementar ser consultado.
    conteudo = await dados_da_reserva(servicos, "GET", f"/internal/v1/reservas/{reservaId}", 200)
    dados = apresentar(conteudo)
    # A credencial própria alcança também unidades inativas; Unidades devolve só os campos públicos.
    unidade, itens = await asyncio.gather(
        do_bff.complementar("unidades", f"/internal/v1/unidades/{dados.unidadeId}", UNIDADE),
        do_bff.complementar("estoque", API + "/estoque/itens", ITENS, publico=True),
    )
    complementos = {"itemNome": next((item.nome for item in itens or [] if item.itemId == dados.itemId), None)}
    if unidade is not None:
        complementos |= {"unidadeNome": unidade.nome, "enderecoLocal": unidade.endereco,
                         "orientacoesRetirada": unidade.orientacoesRetirada}
    return apresentar(conteudo, **complementos)


@app.post(API + "/reservas/{reservaId}/cancelar")
async def cancelar_reserva(request: Request, reservaId: UUID, cidadao: Cidadao, chave: Chave):
    return await encaminhar(
        Servicos(request, TOKEN_BFF_CIDADAO, cidadao, chave), reservaId, f"{API}/reservas/{reservaId}/cancelar",
        "CANCELAMENTO_DISTRIBUIDO", "cancelamentos", f"{API}/reservas/{reservaId}",
    )
