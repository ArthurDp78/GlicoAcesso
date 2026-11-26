#!/usr/bin/env bash
# Encerra todo o GlicoAcesso, inclusive a orientação, preservando os volumes com os dados e o índice.
# Equivalente a parar.ps1.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=scripts/compose-glicoacesso.sh
. "$RAIZ/scripts/compose-glicoacesso.sh"

assert_docker
isolar_ambiente
if [ -f "$RAIZ/.env" ]; then
  opcoes_compose
else
  # Encerrar não usa as credenciais, mas o Compose exige que as variáveis obrigatórias existam.
  while IFS= read -r nome; do export "$nome=encerramento"; done \
    < <(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=$/\1/p' "$RAIZ/.env.example")
  opcoes_compose sem-env
fi
# Sem --volumes: bancos, RabbitMQ e índice vetorial são preservados para a próxima execução.
"${COMPOSE[@]}" --profile indexacao down --remove-orphans \
  || erro 'Não foi possível encerrar o GlicoAcesso. Veja a mensagem acima.'
echo 'GlicoAcesso encerrado. Os dados foram preservados; para voltar, execute ./iniciar.sh'
