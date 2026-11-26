#Requires -Version 5.1
<#
.SYNOPSIS
  Encerra todo o GlicoAcesso, inclusive a orientação, preservando os volumes com os dados e o índice.

.EXAMPLE
  .\parar.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
. (Join-Path $raiz 'scripts/compose-glicoacesso.ps1')

$ambiente = $null
try {
  Assert-Docker
  $ambiente = Enter-AmbienteCompose $raiz
  $temEnv = Test-Path -LiteralPath (Join-Path $raiz '.env') -PathType Leaf
  if (-not $temEnv) {
    # Encerrar não usa as credenciais, mas o Compose exige que as variáveis obrigatórias existam.
    foreach ($linha in Get-Content -LiteralPath (Join-Path $raiz '.env.example')) {
      if ($linha -match '^([A-Z_][A-Z0-9_]*)=$') { [Environment]::SetEnvironmentVariable($Matches[1], 'encerramento', 'Process') }
    }
  }
  $compose = (Get-OpcoesCompose $raiz -SemArquivoEnv:(-not $temEnv)) + @('--profile', 'indexacao')
  # Sem --volumes: bancos, RabbitMQ e índice vetorial são preservados para a próxima execução.
  $codigo = Invoke-Docker ($compose + @('down', '--remove-orphans'))
  if ($codigo -ne 0) { throw 'Não foi possível encerrar o GlicoAcesso. Veja a mensagem acima.' }
  Write-Host 'GlicoAcesso encerrado. Os dados foram preservados; para voltar, execute .\iniciar.ps1' -ForegroundColor Green
} catch {
  Write-Host "Erro: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
} finally {
  if ($ambiente) { Exit-AmbienteCompose $ambiente }
}
