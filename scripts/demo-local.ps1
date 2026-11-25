<#
.SYNOPSIS
  Inicia ou para o Compose local, preservando os volumes e as credenciais.
#>
param(
  [ValidateRange(1, 65535)][int]$GatewayPorta,
  [switch]$FalharRetiradas,
  [switch]$Parar,
  [switch]$Zerar
)
$ErrorActionPreference = 'Stop'
if ($Zerar) { throw 'A opção -Zerar foi removida para preservar os dados do ambiente.' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Compose não encontrado.' }

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
  if ($Parar) {
    docker compose stop
    if ($LASTEXITCODE -ne 0) { throw 'O Compose não conseguiu parar os serviços.' }
    return
  }
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Instale o uv para preparar o arquivo .env.' }
  uv run --no-project --python 3.14 python scripts/configurar-compose.py
  if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o arquivo .env.' }

  $variaveis = @{}
  if ($PSBoundParameters.ContainsKey('GatewayPorta')) { $variaveis.GLICO_GATEWAY_PORTA = "$GatewayPorta" }
  if ($FalharRetiradas) { $variaveis.GLICO_FALHA_PREPARAR_AUTORIZACAO = '1' }
  $anteriores = @{}
  try {
    foreach ($nome in $variaveis.Keys) {
      $anteriores[$nome] = [Environment]::GetEnvironmentVariable($nome, 'Process')
      [Environment]::SetEnvironmentVariable($nome, $variaveis[$nome], 'Process')
    }
    docker compose up --build --wait
    if ($LASTEXITCODE -ne 0) { throw 'O Compose não conseguiu iniciar todos os serviços.' }
    $endereco = docker compose port gateway 8000
    if ($LASTEXITCODE -ne 0) { throw 'O Gateway ainda não publicou sua porta.' }
    Write-Host "Portal do cidadão em http://$endereco/cidadao"
    Write-Host "Painel da unidade em http://$endereco/unidade"
    Write-Host 'Consulte os tokens em .env e os logs com docker compose logs.'
  } finally {
    foreach ($nome in $anteriores.Keys) {
      [Environment]::SetEnvironmentVariable($nome, $anteriores[$nome], 'Process')
    }
  }
} finally {
  Pop-Location
}
