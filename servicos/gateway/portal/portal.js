const api = "/api/cidadao/v1";
const formulario = document.querySelector("#consulta");
const seletor = document.querySelector("#item");
const buscar = document.querySelector("#buscar");
const recarregar = document.querySelector("#recarregar");
const mensagemStatus = document.querySelector("#status");
const lista = document.querySelector("#lista");
const formatoData = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short", timeStyle: "short",
});

async function consultar(recurso) {
  const resposta = await fetch(api + recurso, {headers: {"Accept": "application/json"}});
  if (!resposta.ok) throw new Error("Consulta indisponível");
  return await resposta.json();
}

function informar(mensagem, erro = false) {
  mensagemStatus.textContent = mensagem;
  mensagemStatus.classList.toggle("erro", erro);
}

function texto(tag, conteudo) {
  const elemento = document.createElement(tag);
  elemento.textContent = conteudo;
  return elemento;
}

function cartao(unidade) {
  const artigo = document.createElement("article");
  artigo.className = "cartao";
  const cabecalho = document.createElement("header");
  const indicador = texto("span", unidade.disponivel ? "Disponível" : "Sem saldo disponível");
  indicador.className = unidade.disponivel ? "indicador" : "indicador neutro";
  cabecalho.append(texto("h3", unidade.nomeUnidade), indicador);
  const dados = document.createElement("dl");
  const instante = new Date(unidade.atualizadoEm);
  const atualizado = Number.isNaN(instante.getTime()) ? unidade.atualizadoEm : formatoData.format(instante);
  for (const [rotulo, valor] of [
    ["Endereço", unidade.endereco],
    ["Horário", unidade.horarioAtendimento],
    ["Orientações de retirada", unidade.orientacoesRetirada],
    ["Reserva pela unidade", unidade.permiteReserva ? "Permitida" : "Indisponível"],
    ["Disponibilidade atualizada em", atualizado],
  ]) {
    const campo = document.createElement("div");
    campo.append(texto("dt", rotulo), texto("dd", valor));
    dados.append(campo);
  }
  artigo.append(cabecalho, dados);
  return artigo;
}

async function carregarCatalogo() {
  recarregar.hidden = true;
  seletor.replaceChildren(new Option("Carregando itens…", ""));
  seletor.disabled = true;
  buscar.disabled = true;
  try {
    const itens = await consultar("/itens");
    seletor.replaceChildren(new Option("Selecione um item", ""));
    for (const item of itens) seletor.add(new Option(item.nome, item.itemId));
    seletor.disabled = itens.length === 0;
    buscar.disabled = itens.length === 0;
    informar(itens.length === 0 ? "Ainda não há itens no catálogo." : "Selecione um item para ver as unidades.");
  } catch {
    seletor.replaceChildren(new Option("Catálogo indisponível", ""));
    informar("Não foi possível carregar o catálogo. Tente novamente.", true);
    recarregar.hidden = false;
  }
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const itemId = seletor.value;
  if (!itemId) return;
  buscar.disabled = true;
  seletor.disabled = true;
  lista.replaceChildren();
  informar("Consultando disponibilidade…");
  try {
    const unidades = await consultar("/explorar?" + new URLSearchParams({itemId}));
    lista.replaceChildren(...unidades.map(cartao));
    const quantidade = unidades.length;
    informar(quantidade === 0 ? "Nenhuma unidade informou disponibilidade para este item."
      : quantidade === 1 ? "1 unidade com informação de estoque."
      : quantidade + " unidades com informação de estoque.");
  } catch {
    informar("Não foi possível consultar a disponibilidade. Tente novamente.", true);
  } finally {
    seletor.disabled = false;
    buscar.disabled = false;
  }
});

recarregar.addEventListener("click", carregarCatalogo);
carregarCatalogo();
