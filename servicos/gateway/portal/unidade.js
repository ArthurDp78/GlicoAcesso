const formulario = document.querySelector("#carregar");
const credencial = document.querySelector("#credencial");
const mensagem = document.querySelector("#status");
const lista = document.querySelector("#lista");
const formatoData = new Intl.DateTimeFormat("pt-BR", {dateStyle: "short", timeStyle: "short"});
// Uma chave por reserva e decisão: repetir após falha de rede reaproveita a mesma chave.
const chaves = new Map();

function informar(texto, erro = false) {
  mensagem.textContent = texto;
  mensagem.classList.toggle("erro", erro);
}

function texto(tag, conteudo) {
  const elemento = document.createElement(tag);
  elemento.textContent = conteudo;
  return elemento;
}

function data(valor) {
  const instante = new Date(valor);
  return Number.isNaN(instante.getTime()) ? valor : formatoData.format(instante);
}

async function chamar(href, opcoes = {}) {
  const token = credencial.value.trim();
  if (!token) {
    credencial.focus();
    throw new Error("Informe o token do profissional de demonstração.");
  }
  const resposta = await fetch(href, {...opcoes, headers: {...opcoes.headers, Authorization: "Bearer " + token}});
  const corpo = await resposta.json().catch(() => ({}));
  if (resposta.status === 401) throw new Error("Token do profissional inválido.");
  if (resposta.status === 403) throw new Error("Sem acesso: o profissional precisa estar vinculado a uma unidade ativa.");
  if (resposta.status === 404) throw new Error(corpo.mensagem ?? corpo.detail ?? "Recurso não encontrado.");
  if (resposta.status === 409) {
    const motivos = {
      ESTADO_INCOMPATIVEL: "A reserva não aguarda mais decisão ou o prazo terminou.",
      EXECUCAO_CONCORRENTE: "Já existe uma confirmação em andamento para esta reserva.",
      CHAVE_IDEMPOTENTE_CONFLITANTE: "Esta ação já foi enviada com outros dados.",
      ENTREGA_JA_REGISTRADA: "A entrega já foi registrada.",
      CANCELAMENTO_EM_ANDAMENTO: "Já existe um cancelamento em andamento.",
      AUTORIZACAO_CANCELADA: "A autorização foi revogada.",
      RESERVA_NAO_CONFIRMADA: "A reserva precisa estar confirmada.",
      LIMITE_ESTOQUE_EXCEDIDO: "A quantidade recebida excede o limite do saldo.",
    };
    throw Object.assign(new Error(motivos[corpo.codigo] ?? "A operação conflita com o estado atual."), {conflito: true});
  }
  if (!resposta.ok) throw new Error("Não foi possível concluir. Tente novamente.");
  return {status: resposta.status, corpo};
}

function cartao(reserva) {
  const artigo = document.createElement("article");
  artigo.className = "cartao";
  const cabecalho = document.createElement("header");
  const indicador = texto("span", reserva.status === "SOLICITADA" ? "Aguardando decisão" : reserva.status);
  indicador.className = "indicador";
  cabecalho.append(texto("h3", reserva.itemNome ?? reserva.itemId), indicador);
  const dados = document.createElement("dl");
  for (const [rotulo, valor] of [
    ["Quantidade", String(reserva.quantidade)],
    ["Código da reserva", reserva.reservaId],
    ["Solicitada em", data(reserva.criadaEm)],
    ["Decidir até", data(reserva.decisaoAte)],
  ]) {
    const campo = document.createElement("div");
    campo.append(texto("dt", rotulo), texto("dd", valor));
    dados.append(campo);
  }
  artigo.append(cabecalho, dados);
  const acoes = document.createElement("div");
  acoes.className = "acoes";
  for (const [nome, rotulo] of [["aceitar", "Aceitar"], ["rejeitar", "Rejeitar"]]) {
    const link = reserva._links?.[nome];
    if (!link) continue;
    const botao = texto("button", rotulo);
    botao.type = "button";
    if (nome === "rejeitar") botao.className = "perigo";
    botao.addEventListener("click", () => decidir(reserva, link, acoes, indicador));
    acoes.append(botao);
  }
  if (acoes.childElementCount) artigo.append(acoes);
  adicionarCancelamento(reserva, artigo, informar);
  return artigo;
}

async function decidir(reserva, link, acoes, indicador) {
  const identificador = reserva.reservaId + ":" + link.body.decisao;
  if (!chaves.has(identificador)) chaves.set(identificador, crypto.randomUUID());
  const botoes = acoes.querySelectorAll("button");
  botoes.forEach(botao => { botao.disabled = true; });
  informar("Registrando decisão…");
  try {
    const {status} = await chamar(link.href, {
      method: link.method,
      body: JSON.stringify(link.body),
      headers: {"Content-Type": "application/json", "Idempotency-Key": chaves.get(identificador)},
    });
    if (status === 202) {
      indicador.textContent = "Confirmação em processamento";
      informar("Aceite registrado. A confirmação da reserva foi iniciada.");
      // A projeção é eventual: consulta de novo depois que a SAGA e o evento tiveram tempo de passar.
      setTimeout(carregarEstoque, 3000);
    } else {
      indicador.textContent = "Rejeitada";
      indicador.classList.add("neutro");
      informar("Solicitação rejeitada.");
    }
    acoes.remove();
  } catch (erro) {
    botoes.forEach(botao => { botao.disabled = false; });
    informar(erro instanceof TypeError ? "Falha de conexão. Tente novamente." : erro.message, true);
  }
}

const estoque = document.querySelector("#estoque");
const mensagemEstoque = document.querySelector("#status-estoque");
const formularioEntrada = document.querySelector("#entrada-estoque");
const itemEntrada = document.querySelector("#item-entrada");
const quantidadeEntrada = document.querySelector("#quantidade-entrada");
const mensagemEntrada = document.querySelector("#status-entrada");
let unidadeEntrada = null;

function informarEntrada(texto, erro = false) {
  mensagemEntrada.textContent = texto;
  mensagemEntrada.classList.toggle("erro", erro);
}

async function carregarCatalogo() {
  const token = credencial.value.trim();
  formularioEntrada.hidden = true;
  try {
    const {corpo} = await chamar("/api/unidade/v1/painel/estoque/catalogo");
    if (credencial.value.trim() !== token) return;
    unidadeEntrada = corpo.unidadeId;
    itemEntrada.replaceChildren(new Option("Selecione um item", ""));
    for (const item of corpo.itens) itemEntrada.add(new Option(item.nome, item.itemId));
    if (corpo.itens.length === 0) {
      informarEntrada("Nenhum item no catálogo.");
      return;
    }
    informarEntrada("");
    formularioEntrada.hidden = false;
  } catch (erro) {
    if (credencial.value.trim() !== token) return;
    informarEntrada(erro instanceof TypeError ? "Falha de conexão ao consultar o catálogo." : erro.message, true);
  }
}

credencial.addEventListener("input", () => {
  formularioEntrada.hidden = true;
  unidadeEntrada = null;
  informarEntrada("");
});

formularioEntrada.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (!unidadeEntrada) return;
  const botao = formularioEntrada.querySelector("button");
  const unidadeId = unidadeEntrada;
  const itemId = itemEntrada.value;
  const quantidade = quantidadeEntrada.valueAsNumber;
  const operacao = `glicoacesso:entrada:${unidadeId}:${itemId}:${quantidade}`;
  botao.disabled = itemEntrada.disabled = quantidadeEntrada.disabled = true;
  informarEntrada("Registrando entrada…");
  try {
    const chave = sessionStorage.getItem(operacao) ?? crypto.randomUUID();
    sessionStorage.setItem(operacao, chave);
    await chamar(`/api/unidade/v1/painel/estoque/${unidadeId}/itens/${itemId}/entradas`, {
      method: "POST",
      body: JSON.stringify({quantidade}),
      headers: {"Content-Type": "application/json", "Idempotency-Key": chave},
    });
    sessionStorage.removeItem(operacao);
    quantidadeEntrada.value = "";
    informarEntrada("Entrada registrada. O estoque será atualizado em instantes.");
    setTimeout(carregarEstoque, 2500);
  } catch (erro) {
    if (erro.conflito) sessionStorage.removeItem(operacao);
    informarEntrada(erro instanceof TypeError ? "Falha de conexão. Reenvie com o mesmo item e quantidade." : erro.message, true);
  } finally {
    botao.disabled = itemEntrada.disabled = quantidadeEntrada.disabled = false;
  }
});

function cartaoEstoque(item) {
  const artigo = document.createElement("article");
  artigo.className = "cartao";
  const cabecalho = document.createElement("header");
  const indicador = texto("span", item.permiteReserva ? "Aceita reservas" : "Sem reservas");
  indicador.className = item.permiteReserva ? "indicador" : "indicador neutro";
  cabecalho.append(texto("h3", item.itemNome), indicador);
  const dados = document.createElement("dl");
  for (const [rotulo, valor] of [
    ["Estoque físico", String(item.estoqueFisicoAtual)],
    ["Alocado para reservas", String(item.quantidadeAlocada)],
    ["Disponível", String(item.quantidadeDisponivel)],
    ["Projeção atualizada em", data(item.atualizadoEm)],
  ]) {
    const campo = document.createElement("div");
    campo.append(texto("dt", rotulo), texto("dd", valor));
    dados.append(campo);
  }
  const acao = texto("button", item.permiteReserva ? "Desabilitar reservas" : "Habilitar reservas");
  acao.type = "button";
  acao.addEventListener("click", () => configurarPermissao(item, acao));
  artigo.append(cabecalho, dados, acao);
  return artigo;
}

async function configurarPermissao(item, botao) {
  const {unidadeId, itemId} = item;
  const permiteReserva = !item.permiteReserva;
  const operacao = `glicoacesso:permissao:${unidadeId}:${itemId}:${permiteReserva}`;
  botao.disabled = true;
  try {
    const chave = sessionStorage.getItem(operacao) ?? crypto.randomUUID();
    sessionStorage.setItem(operacao, chave);
    await chamar(`/api/unidade/v1/painel/estoque/${unidadeId}/itens/${itemId}/permissao`, {
      method: "PUT",
      body: JSON.stringify({permiteReserva}),
      headers: {"Content-Type": "application/json", "Idempotency-Key": chave},
    });
    sessionStorage.removeItem(operacao);
    mensagemEstoque.classList.remove("erro");
    mensagemEstoque.textContent = "Permissão atualizada. A consulta de disponibilidade será atualizada em instantes.";
    botao.textContent = "Atualizando estoque…";
    setTimeout(carregarEstoque, 2500);
  } catch (erro) {
    if (erro.conflito) sessionStorage.removeItem(operacao);
    mensagemEstoque.classList.add("erro");
    mensagemEstoque.textContent = erro instanceof TypeError ? "Falha de conexão. Repita a mesma ação." : erro.message;
    botao.disabled = false;
  }
}

async function carregarEstoque() {
  try {
    const {corpo} = await chamar("/api/unidade/v1/painel/estoque");
    estoque.replaceChildren(...corpo.map(cartaoEstoque));
    mensagemEstoque.classList.remove("erro");
    mensagemEstoque.textContent = corpo.length === 0 ? "Nenhum item com estoque projetado."
      : "A disponibilidade pode levar alguns segundos para refletir alterações no estoque.";
  } catch (erro) {
    mensagemEstoque.classList.add("erro");
    mensagemEstoque.textContent = erro instanceof TypeError ? "Falha de conexão ao consultar o estoque." : erro.message;
  }
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();
  const botao = evento.submitter;
  botao.disabled = true;
  lista.replaceChildren();
  informar("Carregando solicitações…");
  carregarEstoque();
  carregarCatalogo();
  try {
    const {corpo} = await chamar("/api/unidade/v1/painel/reservas");
    lista.replaceChildren(...corpo.map(cartao));
    informar(corpo.length === 0 ? "Nenhuma solicitação aguardando decisão."
      : corpo.length === 1 ? "1 solicitação aguardando decisão."
      : corpo.length + " solicitações aguardando decisão.");
  } catch (erro) {
    informar(erro instanceof TypeError ? "Falha de conexão. Tente novamente." : erro.message, true);
  } finally {
    botao.disabled = false;
  }
});


const consultaRetirada = document.querySelector("#consultar-retirada");
const codigoRetirada = document.querySelector("#codigo-retirada");
const statusRetirada = document.querySelector("#status-retirada");
const resultadoRetirada = document.querySelector("#reserva-retirada");

function informarRetirada(mensagem, erro = false) {
  statusRetirada.textContent = mensagem;
  statusRetirada.classList.toggle("erro", erro);
}

async function entregar(link, botao, artigo) {
  const operacao = "glicoacesso:retirada:" + link.body.autorizacaoId;
  botao.disabled = true;
  informarRetirada("Registrando entrega…");
  try {
    const chave = sessionStorage.getItem(operacao) ?? crypto.randomUUID();
    sessionStorage.setItem(operacao, chave);
    const {corpo} = await chamar(link.href, {
      method: link.method,
      body: JSON.stringify(link.body),
      headers: {"Content-Type": "application/json", "Idempotency-Key": chave},
    });
    sessionStorage.removeItem(operacao);
    botao.remove();
    artigo.append(texto("p", "Entrega registrada em " + data(corpo.realizadaEm) + "."));
    informarRetirada("Código da retirada: " + corpo.retiradaId);
  } catch (erro) {
    if (erro.conflito) sessionStorage.removeItem(operacao);
    informarRetirada(erro instanceof TypeError ? "Falha de conexão. Repita a mesma ação." : erro.message, true);
    botao.disabled = false;
  }
}

consultaRetirada.addEventListener("submit", async evento => {
  evento.preventDefault();
  const codigo = codigoRetirada.value.trim();
  if (!/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(codigo)) {
    informarRetirada("Informe um código de reserva válido.", true);
    return;
  }
  const token = credencial.value.trim();
  const consultar = evento.submitter;
  consultar.disabled = true;
  resultadoRetirada.replaceChildren();
  informarRetirada("Consultando reserva…");
  try {
    const {corpo} = await chamar(`/api/unidade/v1/painel/reservas/${codigo}`);
    if (credencial.value.trim() !== token) return;
    const artigo = texto("article", "");
    artigo.className = "cartao";
    artigo.append(texto("h3", corpo.itemNome ?? corpo.itemId), texto("p", "Quantidade: " + corpo.quantidade));
    resultadoRetirada.append(artigo);
    const link = corpo._links?.["autorizacao-retirada"];
    adicionarCancelamento(corpo, artigo, informarRetirada);
    if (link) {
      const botao = texto("button", "Registrar entrega");
      botao.type = "button";
      botao.addEventListener("click", () => entregar(link, botao, artigo));
      artigo.append(botao);
      informarRetirada("Reserva confirmada e autorização ativa.");
    } else {
      informarRetirada(corpo.dadosAutorizacao?.status === "UTILIZADA"
        ? "A entrega já foi registrada." : "Reserva sem autorização disponível. Estado: " + corpo.status + ".");
    }
  } catch (erro) {
    if (credencial.value.trim() === token) informarRetirada(
      erro instanceof TypeError ? "Falha de conexão. Tente novamente." : erro.message, true,
    );
  } finally {
    consultar.disabled = false;
  }
});

credencial.addEventListener("input", () => {
  resultadoRetirada.replaceChildren();
  informarRetirada("");
});


function adicionarCancelamento(reserva, artigo, feedback) {
  const link = reserva._links?.cancelar;
  if (!link) return;
  const formulario = document.createElement("form");
  const campo = texto("label", "Justificativa do cancelamento");
  const justificativa = document.createElement("textarea");
  justificativa.required = true;
  justificativa.minLength = 5;
  campo.append(justificativa);
  const botao = texto("button", "Cancelar reserva");
  botao.type = "submit";
  botao.className = "perigo";
  formulario.append(campo, botao);
  artigo.append(formulario);
  formulario.addEventListener("submit", async evento => {
    evento.preventDefault();
    const motivo = justificativa.value.trim();
    if (motivo.length < 5) {
      feedback("Informe pelo menos cinco caracteres na justificativa.", true);
      return;
    }
    const operacao = "glicoacesso:cancelar-unidade:" + reserva.reservaId;
    const tentativa = JSON.parse(sessionStorage.getItem(operacao) ?? "null");
    if (tentativa && tentativa.motivo !== motivo) {
      feedback("Repita com a mesma justificativa para verificar o resultado da tentativa anterior.", true);
      return;
    }
    const chave = tentativa?.chave ?? crypto.randomUUID();
    sessionStorage.setItem(operacao, JSON.stringify({chave, motivo}));
    botao.disabled = justificativa.disabled = true;
    try {
      const {status} = await chamar(link.href, {
        method: link.method,
        body: JSON.stringify({justificativa: motivo}),
        headers: {"Content-Type": "application/json", "Idempotency-Key": chave},
      });
      if (status === 200) sessionStorage.removeItem(operacao);
      artigo.querySelectorAll("button").forEach(outro => { outro.disabled = true; });
      formulario.remove();
      feedback(status === 202 ? "Cancelamento em processamento. Consulte novamente pelo código." : "Reserva cancelada.");
    } catch (erro) {
      if (erro.conflito) {
        sessionStorage.removeItem(operacao);
        formulario.remove();
      }
      feedback(erro instanceof TypeError ? "Falha de conexão. Repita o cancelamento." : erro.message, true);
      botao.disabled = justificativa.disabled = false;
    }
  });
}
