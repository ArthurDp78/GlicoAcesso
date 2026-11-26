# shellcheck shell=bash
# Funções comuns a iniciar.sh e parar.sh, equivalentes a compose-glicoacesso.ps1.
# Todas as operações usam o mesmo projeto, arquivos e .env.

PROJETO=glicoacesso
# Mesma base Python dos Dockerfiles: o .env é gerado sem exigir Python no computador.
# shellcheck disable=SC2034  # Usada por iniciar.sh.
IMAGEM_PYTHON=python:3.14.10-slim-trixie

erro() { printf '\nErro: %s\n' "$1" >&2; exit 1; }

assert_docker() {
  command -v docker >/dev/null 2>&1 \
    || erro 'Docker não encontrado. Instale o Docker Engine: https://docs.docker.com/engine/install/'
  docker compose version --short >/dev/null 2>&1 \
    || erro 'Docker Compose v2 não encontrado. Instale o plugin "docker compose": https://docs.docker.com/compose/install/linux/'
  local saida
  if ! saida=$(docker info --format '{{.OSType}}' 2>&1); then
    case "$saida" in
      *"permission denied"*)
        # shellcheck disable=SC2016  # O comando sugerido é exibido literalmente.
        erro 'Sem permissão para usar o Docker. Adicione seu usuário ao grupo docker (sudo usermod -aG docker "$USER") e entre de novo na sessão.' ;;
      *) erro 'O Docker Engine não está em execução. Inicie-o (por exemplo, sudo systemctl start docker) e tente de novo.' ;;
    esac
  fi
  [ "$saida" = linux ] || erro 'O Docker não está executando contêineres Linux.'
}

opcoes_compose() {
  # Preenche o vetor COMPOSE. Sem argumento, usa o .env da raiz.
  COMPOSE=(docker compose --project-name "$PROJETO" --project-directory "$RAIZ")
  [ "${1:-}" = sem-env ] || COMPOSE+=(--env-file "$RAIZ/.env")
  COMPOSE+=(-f "$RAIZ/docker-compose.yml" -f "$RAIZ/compose.orientacao.yml" --profile orientacao)
}

isolar_ambiente() {
  # O Compose dá precedência às variáveis do terminal sobre o .env. Elas são removidas deste processo
  # para que o .env seja a única fonte; o terminal de quem executou o script não é alterado.
  local nome
  unset COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES COMPOSE_ENV_FILES COMPOSE_PATH_SEPARATOR \
        GLICO_REDE_ADMINISTRATIVA ORIENTACAO_MODELO_EMBEDDING ORIENTACAO_MODELO_GERACAO
  while IFS= read -r nome; do unset "$nome"; done < <(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' "$RAIZ/.env.example")
}

valor_env() {
  # Valor de uma variável no .env (vazio se ausente).
  sed -n "s/^$1=//p" "$RAIZ/.env" 2>/dev/null | tail -n 1
}
