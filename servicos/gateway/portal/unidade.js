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
  if (resposta.status === 404) throw new Error("Reserva não encontrada.");
  if (resposta.status === 409) {
    const motivos = {
      ESTADO_INCOMPATIVEL: "A reserva não aguarda mais decisão ou o prazo terminou.",
      EXECUCAO_CONCORRENTE: "Já existe uma confirmação em andamento para esta reserva.",
      CHAVE_IDEMPOTENTE_CONFLITANTE: "Esta ação já foi enviada com outros dados.",
    };
    throw new Error(motivos[corpo.codigo] ?? "A operação conflita com o estado atual.");
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
  artigo.append(cabecalho, dados);
  return artigo;
}

async function carregarEstoque() {
  try {
    const {corpo} = await chamar("/api/unidade/v1/painel/estoque");
    estoque.replaceChildren(...corpo.map(cartaoEstoque));
    mensagemEstoque.classList.remove("erro");
    mensagemEstoque.textContent = corpo.length === 0 ? "Nenhum item com estoque projetado."
      : "Leitura da projeção CQRS. Após uma confirmação, a atualização chega em alguns segundos.";
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
