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

function cartao(unidade, itemId) {
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
  if (unidade.permiteReserva && unidade.disponivel) {
    const solicitar = texto("button", "Solicitar reserva");
    solicitar.type = "button";
    solicitar.className = "solicitar";
    solicitar.addEventListener("click", () => selecionarUnidade(unidade, itemId));
    artigo.append(solicitar);
  }
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
  formularioReserva.hidden = true;
  selecaoReserva = undefined;
  informar("Consultando disponibilidade…");
  try {
    const unidades = await consultar("/explorar?" + new URLSearchParams({itemId}));
    lista.replaceChildren(...unidades.map(unidade => cartao(unidade, itemId)));
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

const formularioReserva = document.querySelector("#criar-reserva");
const formularioAcompanhamento = document.querySelector("#acompanhar-reserva");
const credencial = document.querySelector("#credencial");
const codigoReserva = document.querySelector("#codigo-reserva");
const mensagemReserva = document.querySelector("#status-reserva");
let selecaoReserva;
let ultimaTentativa;

function informarReserva(mensagem, erro = false) {
  mensagemReserva.textContent = mensagem;
  mensagemReserva.classList.toggle("erro", erro);
}

function selecionarUnidade(unidade, itemId) {
  selecaoReserva = {unidadeId: unidade.unidadeId, itemId};
  document.querySelector("#unidade-reserva").textContent = unidade.nomeUnidade;
  formularioReserva.hidden = false;
  informarReserva("");
  (credencial.value ? document.querySelector("#quantidade") : credencial).focus();
}

async function requisitarReserva(recurso, opcoes = {}) {
  const token = credencial.value.trim();
  if (!token) {
    credencial.focus();
    throw new Error("Informe o token do cidadão de demonstração.");
  }
  const resposta = await fetch(api + recurso, {
    ...opcoes,
    headers: {...opcoes.headers, Authorization: "Bearer " + token},
  });
  if (resposta.status === 401) throw new Error("Token do cidadão inválido.");
  if (resposta.status === 404) throw new Error("Reserva não encontrada para este cidadão.");
  if (resposta.status === 422) throw new Error("Confira os dados. A unidade ou o item pode não aceitar reservas.");
  if (resposta.status === 409) throw new Error("A chave deste pedido já foi usada com outros dados.");
  if (!resposta.ok) throw new Error("Não foi possível concluir. Tente novamente.");
  return resposta.json();
}

formularioReserva.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (!selecaoReserva) return;
  const botao = evento.submitter;
  const body = JSON.stringify({...selecaoReserva, quantidade: Number(document.querySelector("#quantidade").value)});
  if (ultimaTentativa?.body !== body) ultimaTentativa = {body, chave: crypto.randomUUID()};
  botao.disabled = true;
  informarReserva("Enviando solicitação…");
  try {
    const reserva = await requisitarReserva("/reservas", {
      method: "POST", body,
      headers: {"Content-Type": "application/json", "Idempotency-Key": ultimaTentativa.chave},
    });
    codigoReserva.value = reserva.reservaId;
    ultimaTentativa = undefined;
    informarReserva("Solicitação registrada. Estado: " + reserva.status + ".");
    formularioReserva.hidden = true;
    codigoReserva.focus();
  } catch (erro) {
    informarReserva(erro instanceof TypeError ? "Falha de conexão. Tente enviar novamente." : erro.message, true);
  } finally {
    botao.disabled = false;
  }
});

formularioAcompanhamento.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const botao = evento.submitter;
  botao.disabled = true;
  informarReserva("Consultando reserva…");
  try {
    const reserva = await requisitarReserva("/reservas/" + encodeURIComponent(codigoReserva.value.trim()));
    informarReserva("Estado: " + reserva.status + ". Quantidade: " + reserva.quantidade + ".");
  } catch (erro) {
    informarReserva(erro instanceof TypeError ? "Falha de conexão. Tente consultar novamente." : erro.message, true);
  } finally {
    botao.disabled = false;
  }
});
carregarCatalogo();
