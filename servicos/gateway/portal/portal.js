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
const acoesReserva = document.querySelector("#acoes-reserva");
let selecaoReserva;
let ultimaTentativa;

async function hashNavegador(valor) {
  const entrada = new TextEncoder().encode(valor);
  const resumo = await crypto.subtle.digest("SHA-256", entrada);
  return Array.from(new Uint8Array(resumo), byte => byte.toString(16).padStart(2, "0")).join("");
}

async function tentativaPersistida(body) {
  const ator = await hashNavegador(credencial.value.trim());
  const fingerprint = await hashNavegador(body);
  const storageKey = "glico:reserva:" + ator + ":" + fingerprint;
  const anterior = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
  if (anterior?.body === body && anterior.chave) return {...anterior, storageKey};
  const tentativa = {body, chave: crypto.randomUUID(), storageKey};
  sessionStorage.setItem(storageKey, JSON.stringify({body, chave: tentativa.chave}));
  return tentativa;
}

function erroHttp(mensagem, status) {
  const erro = new Error(mensagem);
  erro.httpStatus = status;
  return erro;
}

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
  if (resposta.status === 401) throw erroHttp("Token do cidadão inválido.", resposta.status);
  if (resposta.status === 404) throw erroHttp("Reserva não encontrada para este cidadão.", resposta.status);
  if (resposta.status === 422) throw erroHttp("Confira os dados. A unidade ou o item pode não aceitar reservas.", resposta.status);
  if (resposta.status === 409) throw erroHttp("A chave deste pedido já foi usada com outros dados.", resposta.status);
  if (!resposta.ok) throw erroHttp("Não foi possível concluir. Tente novamente.", resposta.status);
  return resposta.json();
}

formularioReserva.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (!selecaoReserva) return;
  const botao = evento.submitter;
  const body = JSON.stringify({...selecaoReserva, quantidade: Number(document.querySelector("#quantidade").value)});
  if (!credencial.value.trim()) {
    credencial.focus();
    informarReserva("Informe o token do cidadão de demonstração.", true);
    return;
  }
  if (ultimaTentativa?.body !== body) ultimaTentativa = undefined;
  botao.disabled = true;
  informarReserva("Enviando solicitação…");
  try {
    ultimaTentativa = await tentativaPersistida(body);
    const reserva = await requisitarReserva("/reservas", {
      method: "POST", body,
      headers: {"Content-Type": "application/json", "Idempotency-Key": ultimaTentativa.chave},
    });
    codigoReserva.value = reserva.reservaId;
    sessionStorage.removeItem(ultimaTentativa.storageKey);
    ultimaTentativa = undefined;
    informarReserva("Solicitação registrada. Estado: " + reserva.status + ".");
    mostrarCancelamento(reserva);
    formularioReserva.hidden = true;
    codigoReserva.focus();
  } catch (erro) {
    if (Number.isInteger(erro.httpStatus) && erro.httpStatus < 500 && ultimaTentativa) {
      sessionStorage.removeItem(ultimaTentativa.storageKey);
      ultimaTentativa = undefined;
    }
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
    mostrarCancelamento(reserva);
  } catch (erro) {
    informarReserva(erro instanceof TypeError ? "Falha de conexão. Tente consultar novamente." : erro.message, true);
  } finally {
    botao.disabled = false;
  }
});

function mostrarCancelamento(reserva) {
  acoesReserva.replaceChildren();
  const link = reserva._links?.cancelar;
  if (!link) return;
  const botao = document.createElement("button");
  botao.type = "button";
  botao.textContent = "Cancelar reserva";
  botao.addEventListener("click", async () => {
    if (!window.confirm("Cancelar esta reserva?")) return;
    let tentativa;
    botao.disabled = true;
    try {
      tentativa = await tentativaPersistida("cancelar:" + reserva.reservaId);
      const resultado = await requisitarReserva(link.href.slice(api.length), {
        method: link.method, headers: {"Idempotency-Key": tentativa.chave},
      });
      if (resultado.status === "CANCELADA") {
        sessionStorage.removeItem(tentativa.storageKey);
        informarReserva("Reserva cancelada.");
      } else {
        informarReserva("Cancelamento em processamento. Consulte pelo código da reserva.");
      }
      acoesReserva.replaceChildren();
    } catch (erro) {
      if (Number.isInteger(erro.httpStatus) && erro.httpStatus < 500 && tentativa) {
        sessionStorage.removeItem(tentativa.storageKey);
      }
      informarReserva(erro instanceof TypeError ? "Falha de conexão. Repita o cancelamento." : erro.message, true);
      botao.disabled = false;
    }
  });
  acoesReserva.append(botao);
}

codigoReserva.addEventListener("input", () => acoesReserva.replaceChildren());
credencial.addEventListener("input", () => acoesReserva.replaceChildren());

const secaoOrientacao = document.querySelector("#orientacao");
const formularioOrientacao = document.querySelector("#perguntar-orientacao");
const perguntaOrientacao = document.querySelector("#pergunta-orientacao");
const statusOrientacao = document.querySelector("#status-orientacao");
const resultadoOrientacao = document.querySelector("#resultado-orientacao");
let revisaoOrientacao = 0;

seletor.addEventListener("change", () => {
  revisaoOrientacao++;
  secaoOrientacao.hidden = !seletor.value;
  resultadoOrientacao.replaceChildren();
  statusOrientacao.textContent = "";
});

function mostrarOrientacao(dados) {
  const cartaoResposta = document.createElement("article");
  cartaoResposta.className = "cartao";
  cartaoResposta.append(texto("p", dados.resposta));

  if (dados.fontes.length) {
    const fontes = document.createElement("ul");
    for (const fonte of dados.fontes) {
      fontes.append(texto("li", fonte.titulo + " — " + fonte.secao));
    }
    cartaoResposta.append(texto("h3", "Fontes do GlicoAcesso"), fontes);
  }

  const consulta = dados.consulta;
  if (consulta.status === "consultada") {
    cartaoResposta.append(texto("h3", "Disponibilidade consultada"));
    if (consulta.unidades.length) {
      const unidades = document.createElement("ul");
      for (const unidade of consulta.unidades) {
        const saldo = unidade.disponivel ? "Disponível" : "Sem saldo disponível";
        const permissao = unidade.permiteReserva ? "Reserva permitida" : "Reserva indisponível";
        const atualizado = formatoData.format(new Date(unidade.atualizadoEm));
        unidades.append(texto("li", unidade.nomeUnidade + " · " + saldo + " · " + permissao +
          " · Atualizado em " + atualizado));
      }
      cartaoResposta.append(unidades);
    } else {
      cartaoResposta.append(texto("p", "Nenhuma unidade informou disponibilidade para este item."));
    }
  } else if (consulta.status === "indisponivel") {
    cartaoResposta.append(texto("p", "Não foi possível consultar a disponibilidade agora."));
  }
  resultadoOrientacao.replaceChildren(cartaoResposta);
}

formularioOrientacao.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const itemId = seletor.value;
  const pergunta = perguntaOrientacao.value.trim();
  if (!itemId || !pergunta) return;

  const token = credencial.value.trim();
  if (!token) {
    statusOrientacao.textContent = "Informe o token do cidadão em Minhas reservas.";
    credencial.focus();
    return;
  }

  const botao = evento.submitter;
  const revisao = revisaoOrientacao;
  botao.disabled = true;
  resultadoOrientacao.replaceChildren();
  statusOrientacao.textContent = "Consultando os guias e a disponibilidade…";

  try {
    const resposta = await fetch(api + "/orientacoes", {
      method: "POST",
      headers: {"Content-Type": "application/json", Authorization: "Bearer " + token},
      body: JSON.stringify({itemId, pergunta}),
    });
    if (revisao !== revisaoOrientacao) return;
    if (resposta.status === 401 || resposta.status === 403) {
      throw new Error("Confira o token do cidadão.");
    }
    if (resposta.status === 429) throw new Error("Aguarde um momento e tente novamente.");
    if (resposta.status === 404) throw new Error("Selecione um item disponível no catálogo.");
    if (!resposta.ok) throw new Error("Orientação indisponível. Use Consultar disponibilidade ou Minhas reservas.");
    const dados = await resposta.json();
    if (revisao !== revisaoOrientacao) return;
    mostrarOrientacao(dados);
    statusOrientacao.textContent = dados.modo === "orientacao_basica" ? "Orientação básica exibida." : "Resposta exibida.";
  } catch (erro) {
    if (revisao === revisaoOrientacao) {
      statusOrientacao.textContent = erro instanceof TypeError
        ? "Falha de conexão. Tente novamente." : erro.message;
    }
  } finally {
    botao.disabled = false;
  }
});
carregarCatalogo();
