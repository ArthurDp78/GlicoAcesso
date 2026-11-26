#!/usr/bin/env bash
# Inicia o GlicoAcesso completo, inclusive a orientação com RAG, com um único comando.
# Equivalente a iniciar.ps1. Pode ser executado de novo a qualquer momento: credenciais, dados e
# embeddings são reaproveitados.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/compose-glicoacesso.sh
. "$RAIZ/scripts/compose-glicoacesso.sh"
ARQUIVO_ENV="$RAIZ/.env"
PERGUNTA_TESTE='Qual código devo levar ao balcão e onde vejo as orientações para retirar uma reserva confirmada?'

if [ -t 1 ]; then CIANO=$'\e[36m'; VERDE=$'\e[32m'; AMARELO=$'\e[33m'; NORMAL=$'\e[0m'
else CIANO=''; VERDE=''; AMARELO=''; NORMAL=''; fi
etapa() { printf '\n%s==> %s%s\n' "$CIANO" "$1" "$NORMAL"; }
aviso() { printf '%sAviso: %s%s\n' "$AMARELO" "$1" "$NORMAL" >&2; }

chave_valida() {
  # Mesmas restrições do configurador para valores do .env: sem espaços, aspas, $, # ou barra invertida.
  local LC_ALL=C
  [[ $1 =~ ^[!-~]{20,}$ ]] && [[ $1 != *[\'\"\$\#\\]* ]]
}

ler_chave_google() {
  CHAVE=''
  [ -t 0 ] || return 0
  echo 'A orientação com IA usa uma chave do Google AI Studio: https://aistudio.google.com/apikey'
  echo 'A chave fica somente no .env local, que não vai para o Git. Pressione Enter sem digitar'
  echo 'nada para continuar sem IA: o portal mantém a orientação básica.'
  local _
  for _ in 1 2 3; do
    IFS= read -r -s -p 'GOOGLE_API_KEY: ' CHAVE; echo
    CHAVE="${CHAVE#"${CHAVE%%[![:space:]]*}"}"; CHAVE="${CHAVE%"${CHAVE##*[![:space:]]}"}"
    if [ -z "$CHAVE" ] || chave_valida "$CHAVE"; then return 0; fi
    aviso 'A chave contém caracteres inválidos ou é curta demais. Tente de novo.'
  done
  CHAVE=''
}

gravar_chave_google() {
  # Reescreve o mesmo arquivo, preservando suas permissões. A chave passa pelo ambiente do awk,
  # nunca pela linha de comando, onde ficaria visível na lista de processos.
  local conteudo
  conteudo=$(CHAVE_GOOGLE="$1" awk '
    /^GOOGLE_API_KEY=/ { print "GOOGLE_API_KEY=" ENVIRON["CHAVE_GOOGLE"]; trocada = 1; next }
    { print }
    END { if (!trocada) print "GOOGLE_API_KEY=" ENVIRON["CHAVE_GOOGLE"] }' "$ARQUIVO_ENV")
  printf '%s\n' "$conteudo" > "$ARQUIVO_ENV"
}

porta_ocupada() { timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null; }

estado_orientacao() {
  # Define ESTADO e COR_ESTADO, como Get-EstadoOrientacao em iniciar.ps1.
  local url=$1 token=$2 tem_chave=$3 trechos=$4 itens item resposta modo
  COR_ESTADO=$AMARELO
  if [ "$tem_chave" != sim ]; then
    ESTADO='IA desativada: GOOGLE_API_KEY não configurada. O portal usa a orientação básica.'; return
  fi
  if [ "$trechos" -le 0 ]; then
    ESTADO='IA não operacional: o índice da base de conhecimento está vazio. O portal usa a orientação básica.'; return
  fi
  if ! command -v curl >/dev/null 2>&1; then
    ESTADO='Não verificada: instale o curl para testar a orientação.'; return
  fi
  if ! itens=$(curl -fsS --max-time 10 "$url/api/cidadao/v1/itens" 2>&1); then
    ESTADO="Orientação não respondeu ao teste ($itens). Tente de novo em instantes."; return
  fi
  # Uma linha por item, sem depender de jq: prefere o item de demonstração e, sem ele, usa o primeiro do catálogo.
  item=$(printf '%s' "$itens" | tr '{' '\n' | grep -E '"nome" *: *"Tiras reagentes' | grep -oE '"itemId" *: *"[0-9a-f-]+"' | head -n 1 | grep -oE '[0-9a-f-]{36}' || true)
  [ -n "$item" ] || item=$(printf '%s' "$itens" | grep -oE '"itemId" *: *"[0-9a-f-]+"' | head -n 1 | grep -oE '[0-9a-f-]{36}' || true)
  if [ -z "$item" ]; then ESTADO='Sem itens no catálogo para testar a orientação.'; return; fi
  # O token vai por arquivo de cabeçalho, fora da linha de comando.
  if ! resposta=$(curl -fsS --max-time 25 -X POST "$url/api/cidadao/v1/orientacoes" \
        -H @<(printf 'Authorization: Bearer %s\n' "$token") -H 'Content-Type: application/json; charset=utf-8' \
        --data-binary "{\"itemId\":\"$item\",\"pergunta\":\"$PERGUNTA_TESTE\"}" 2>&1); then
    ESTADO="Orientação não respondeu ao teste ($resposta). Tente de novo em instantes."; return
  fi
  modo=$(printf '%s' "$resposta" | grep -oE '"modo" *: *"[a-z_]+"' | head -n 1 | grep -oE '[a-z_]+"$' | tr -d '"' || true)
  if [ "$modo" = rag ]; then
    COR_ESTADO=$VERDE; ESTADO="IA operacional (RAG com $trechos trechos indexados)."
  else
    ESTADO='IA não operacional: o provedor recusou ou não respondeu (chave, cota ou rede). O portal usa a orientação básica, com a disponibilidade real. Confira a chave no .env e execute de novo.'
  fi
}

etapa 'Verificando o Docker'
assert_docker
echo 'Docker e Docker Compose disponíveis.'

etapa 'Preparando o .env'
primeira_vez=nao; [ -f "$ARQUIVO_ENV" ] || primeira_vez=sim
# Reaproveita o configurador: preserva valores existentes e gera só os campos faltantes, sem imprimi-los.
docker run --rm --network none --volume "$RAIZ:/repo" --workdir /repo --user "$(id -u):$(id -g)" \
  "$IMAGEM_PYTHON" python scripts/configurar-compose.py \
  || erro 'Não foi possível gerar ou validar o .env. Veja a mensagem acima.'
if [ "$primeira_vez" = sim ]; then echo '.env criado com credenciais aleatórias e distintas.'
else echo '.env existente preservado; campos faltantes foram completados.'; fi

if [ -z "$(valor_env GOOGLE_API_KEY)" ]; then
  CHAVE=''
  chave_terminal="${GOOGLE_API_KEY:-}"
  chave_terminal="${chave_terminal#"${chave_terminal%%[![:space:]]*}"}"; chave_terminal="${chave_terminal%"${chave_terminal##*[![:space:]]}"}"
  if [ -n "$chave_terminal" ] && chave_valida "$chave_terminal"; then
    CHAVE=$chave_terminal
    echo 'GOOGLE_API_KEY encontrada no terminal; gravada no .env local.'
  else
    ler_chave_google
  fi
  if [ -n "$CHAVE" ]; then gravar_chave_google "$CHAVE"; echo 'Chave gravada no .env local.'; fi
  unset CHAVE chave_terminal
fi
tem_chave=nao; [ -z "$(valor_env GOOGLE_API_KEY)" ] || tem_chave=sim

isolar_ambiente
opcoes_compose
porta=$(valor_env GLICO_GATEWAY_PORTA); porta=${porta:-8000}
[[ $porta =~ ^[0-9]+$ ]] || erro 'GLICO_GATEWAY_PORTA no .env deve ser um número de porta.'
if [ -z "$("${COMPOSE[@]}" ps --status running --quiet gateway 2>/dev/null)" ] && porta_ocupada "$porta"; then
  erro "A porta $porta já está em uso por outro programa. Altere GLICO_GATEWAY_PORTA no .env e execute de novo."
fi

indexacao='não executada'
if [ "$tem_chave" = sim ]; then
  etapa 'Sincronizando a base de conhecimento da orientação'
  echo 'Somente trechos novos ou alterados geram embeddings; os demais são reaproveitados.'
  if "${COMPOSE[@]}" --profile indexacao run --build --rm -T indexar-orientacao; then
    indexacao=sincronizada
  else
    indexacao=falhou
    aviso 'A indexação falhou. O sistema será iniciado assim mesmo; um índice anterior continua válido e, sem ele, o portal usa a orientação básica.'
  fi
else
  printf '\n%sSem GOOGLE_API_KEY: a indexação foi pulada e a orientação usará o modo básico.%s\n' "$AMARELO" "$NORMAL"
fi

etapa 'Iniciando os serviços (a primeira execução constrói as imagens e pode levar alguns minutos)'
if ! "${COMPOSE[@]}" up --build -d --wait; then
  aviso 'Algum serviço não ficou saudável. Estado atual e últimos logs:'
  "${COMPOSE[@]}" ps --all || true
  "${COMPOSE[@]}" logs --no-color --tail 20 || true
  erro 'Falha ao iniciar o GlicoAcesso. Corrija o problema indicado nos logs e execute ./iniciar.sh de novo.'
fi

etapa 'Verificando a orientação'
trechos=$("${COMPOSE[@]}" exec -T db-orientacao psql -XAt -U glico -d orientacao \
            -c 'SELECT count(*) FROM trechos_conhecimento' 2>/dev/null | tr -d '[:space:]' || true)
[[ $trechos =~ ^[0-9]+$ ]] || trechos=0
url="http://127.0.0.1:$porta"
estado_orientacao "$url" "$(valor_env GLICO_CIDADAO_TOKEN)" "$tem_chave" "$trechos"

printf '\n%sGlicoAcesso em execução.%s\n' "$VERDE" "$NORMAL"
echo "  Portal do cidadão:      $url/cidadao"
echo "  Painel da unidade:      $url/unidade"
echo "  Token do cidadão:       $(valor_env GLICO_CIDADAO_TOKEN)"
echo "  Token do profissional:  $(valor_env GLICO_PROFISSIONAL_TOKEN)"
echo "  Base de conhecimento:   $trechos trechos indexados (indexação $indexacao)"
printf '  Orientação:             %s%s%s\n' "$COR_ESTADO" "$ESTADO" "$NORMAL"
echo
echo 'Para encerrar sem apagar os dados: ./parar.sh'
