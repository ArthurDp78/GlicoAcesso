<#
.SYNOPSIS
  Sobe o GlicoAcesso localmente para demonstração (bancos e RabbitMQ em Docker, serviços com uv).

.EXAMPLE
  .\scripts\demo-local.ps1                     # sobe tudo e mostra os endereços e tokens
  .\scripts\demo-local.ps1 -GatewayPorta 8010  # se a porta 8000 estiver ocupada
  .\scripts\demo-local.ps1 -FalharRetiradas    # Retiradas recusa autorizações (demonstra a compensação)
  .\scripts\demo-local.ps1 -Parar              # encerra os serviços (os contêineres continuam)
  .\scripts\demo-local.ps1 -Zerar              # APAGA bancos e fila e sobe tudo do zero (10 físicas, 0 alocadas)
#>
param(
  [int]$GatewayPorta = 8000,
  [switch]$FalharRetiradas,
  [switch]$Parar,
  [switch]$Zerar
)
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$estado = Join-Path $raiz '.demo-local'
$logs = Join-Path $estado 'logs'
$pids = Join-Path $estado 'pids.txt'
New-Item -ItemType Directory -Force $logs | Out-Null

function Stop-Servicos {
  if (Test-Path $pids) {
    foreach ($id in Get-Content $pids) {
      # Encerra o uv e o Python filho dele.
      try { & taskkill.exe /PID $id /T /F 2>$null | Out-Null } catch {}
    }
    Remove-Item $pids
  }
}

Stop-Servicos
if ($Parar) { Write-Host 'Serviços encerrados. Contêineres seguem ativos (docker stop para parar).'; return }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Instale o uv: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker não encontrado. Abra o Docker Desktop.' }
$ocupada = Get-NetTCPConnection -LocalPort $GatewayPorta -State Listen -ErrorAction SilentlyContinue
if ($ocupada) { throw "A porta $GatewayPorta já está em uso (PID $($ocupada[0].OwningProcess)). Encerre esse processo ou use -GatewayPorta 8010." }

# --- Contêineres: cinco PostgreSQL (um por serviço) e RabbitMQ ---
$bancos = [ordered]@{ unidades = 54331; estoque = 54332; reservas = 54333; orquestrador = 54334; retiradas = 54335 }
if ($Zerar) {
  Write-Host 'Apagando contêineres e volumes de demonstração...' -ForegroundColor Yellow
  foreach ($nome in $bancos.Keys) { docker rm -f "glico-$nome-db" 2>$null | Out-Null; docker volume rm "glico-$nome-data" 2>$null | Out-Null }
  docker rm -f glico-rabbitmq 2>$null | Out-Null; docker volume rm glico-rabbitmq-data 2>$null | Out-Null
}
$existentes = docker ps -a --format '{{.Names}}'
foreach ($nome in $bancos.Keys) {
  $container = "glico-$nome-db"
  if ($existentes -contains $container) { docker start $container | Out-Null }
  else {
    docker run -d --name $container -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=$nome `
      -p "127.0.0.1:$($bancos[$nome]):5432" -v "glico-$nome-data:/var/lib/postgresql/data" postgres:17 | Out-Null
  }
}
if ($existentes -contains 'glico-rabbitmq') { docker start glico-rabbitmq | Out-Null }
else {
  docker run -d --name glico-rabbitmq -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 `
    -v glico-rabbitmq-data:/var/lib/rabbitmq rabbitmq:4-management | Out-Null
}
Write-Host 'Aguardando os bancos aceitarem conexões...'
foreach ($nome in $bancos.Keys) {
  for ($i = 0; $i -lt 60; $i++) {
    docker exec "glico-$nome-db" pg_isready -U glico -d $nome 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Milliseconds 500
  }
}

# --- Tokens de demonstração: gerados uma vez e guardados fora do Git ---
$arquivoTokens = Join-Path $estado 'tokens.json'
$novos = @{}
if (Test-Path $arquivoTokens) {
  # Preserva os tokens já gerados e acrescenta os que faltarem.
  (Get-Content $arquivoTokens -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $novos[$_.Name] = $_.Value }
}
foreach ($nome in 'servico', 'orquestrador', 'retiradas', 'admin', 'cidadao', 'profissional') {
  if (-not $novos.ContainsKey($nome)) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $novos[$nome] = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
  }
}
$novos | ConvertTo-Json | Out-File -Encoding utf8 $arquivoTokens
$tokens = Get-Content $arquivoTokens -Raw | ConvertFrom-Json

# --- Ambiente compartilhado pelos processos filhos ---
$env:GLICO_RESERVAS_SERVICE_TOKEN = $tokens.servico
$env:GLICO_ORQUESTRADOR_SERVICE_TOKEN = $tokens.orquestrador
$env:GLICO_RETIRADAS_SERVICE_TOKEN = $tokens.retiradas
$env:GLICO_ADMIN_SERVICE_TOKEN = $tokens.admin
$env:GLICO_CIDADAO_TOKEN = $tokens.cidadao
$env:GLICO_PROFISSIONAL_TOKEN = $tokens.profissional
$env:GLICO_PROFISSIONAL_UNIDADE_ID = '10000000-0000-4000-8000-000000000001'
foreach ($nome in $bancos.Keys) {
  Set-Item "env:$($nome.ToUpper())_DATABASE_URL" "postgresql://glico:glico-demo@127.0.0.1:$($bancos[$nome])/$nome"
}
$env:RABBITMQ_URL = 'amqp://guest:guest@127.0.0.1:5672/%2F'
$env:GLICO_FALHA_PREPARAR_AUTORIZACAO = if ($FalharRetiradas) { '1' } else { '' }

Push-Location $raiz
try {
  uv sync --locked
  foreach ($nome in $bancos.Keys) {
    if ($nome -in 'unidades', 'estoque') { uv run --locked python -m servicos.migracoes $nome --demo }
    else { uv run --locked python -m servicos.migracoes $nome }
    if ($LASTEXITCODE -ne 0) { throw "Falha ao migrar $nome." }
  }

  $servicos = [ordered]@{
    gateway = @('servicos.gateway.main:app', $GatewayPorta)
    'bff-cidadao' = @('servicos.bff_cidadao.main:app', 8001)
    unidades = @('servicos.unidades.main:app', 8002)
    estoque = @('servicos.estoque.main:app', 8003)
    reservas = @('servicos.reservas.main:app', 8004)
    'bff-unidade' = @('servicos.bff_unidade.main:app', 8005)
    orquestrador = @('servicos.orquestrador.main:app', 8006)
    retiradas = @('servicos.retiradas.main:app', 8007)
  }
  foreach ($nome in $servicos.Keys) {
    $app, $porta = $servicos[$nome]
    $processo = Start-Process -PassThru -WindowStyle Hidden -FilePath uv `
      -ArgumentList 'run', '--locked', 'uvicorn', $app, '--host', '127.0.0.1', '--port', "$porta" `
      -RedirectStandardOutput "$logs\$nome.out.log" -RedirectStandardError "$logs\$nome.log"
    Add-Content $pids $processo.Id
  }
  foreach ($nome in $servicos.Keys) {
    $porta = $servicos[$nome][1]
    for ($i = 0; $i -lt 60; $i++) {
      try { Invoke-RestMethod "http://127.0.0.1:$porta/health" -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($i -eq 60) { Write-Warning "$nome não respondeu. Veja $logs\$nome.log" }
  }
} finally { Pop-Location }

Write-Host ''
Write-Host 'GlicoAcesso em execução.' -ForegroundColor Green
Write-Host "  Portal do cidadão:    http://127.0.0.1:$GatewayPorta/cidadao"
Write-Host "  Painel da unidade:    http://127.0.0.1:$GatewayPorta/unidade"
Write-Host '  RabbitMQ (guest/guest): http://127.0.0.1:15672'
Write-Host "  Token do cidadão:     $($tokens.cidadao)"
Write-Host "  Token do profissional: $($tokens.profissional)"
Write-Host "  Logs: $logs"
if ($FalharRetiradas) { Write-Host '  Retiradas está recusando autorizações (falha provocada).' -ForegroundColor Yellow }
Write-Host 'Para encerrar: .\scripts\demo-local.ps1 -Parar'
