# Funções comuns a iniciar.ps1 e parar.ps1. Todas as operações usam o mesmo projeto, arquivos e .env.

$script:Projeto = 'glicoacesso'
$script:ArquivosCompose = @('docker-compose.yml', 'compose.orientacao.yml')
# Mesma base Python dos Dockerfiles: o .env é gerado sem exigir Python no computador.
$script:ImagemPython = 'python:3.14.10-slim-trixie'

function Invoke-Docker {
  # Mostra a saída no console e devolve o código de saída. A preferência local evita que mensagens
  # do Docker em stderr sejam tratadas como erro do PowerShell (comportamento do Windows PowerShell 5.1).
  param([string[]]$Argumentos)
  $ErrorActionPreference = 'Continue'
  & docker @Argumentos | Out-Host
  return $LASTEXITCODE
}

function Get-SaidaDocker {
  # Captura a saída padrão; mensagens de erro são descartadas.
  param([string[]]$Argumentos)
  $ErrorActionPreference = 'Continue'
  $saida = & docker @Argumentos 2>$null
  return [pscustomobject]@{ Codigo = $LASTEXITCODE; Linhas = @($saida) }
}

function Assert-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker não encontrado. Instale o Docker Desktop: https://docs.docker.com/desktop/'
  }
  $compose = Get-SaidaDocker @('compose', 'version', '--short')
  if ($compose.Codigo -ne 0) {
    throw 'Docker Compose v2 não encontrado. Atualize o Docker Desktop ou instale o plugin "docker compose".'
  }
  $info = Get-SaidaDocker @('info', '--format', '{{.OSType}}')
  if ($info.Codigo -ne 0) {
    throw 'O Docker está instalado, mas não responde. Abra o Docker Desktop, aguarde a inicialização e tente de novo.'
  }
  if (([string]$info.Linhas[0]).Trim() -ne 'linux') {
    throw 'O Docker Desktop está em modo de contêineres Windows. Mude para contêineres Linux e tente de novo.'
  }
}

function Get-OpcoesCompose {
  param([string]$Raiz, [switch]$SemArquivoEnv)
  $opcoes = @('compose', '--project-name', $script:Projeto, '--project-directory', $Raiz)
  if (-not $SemArquivoEnv) { $opcoes += @('--env-file', (Join-Path $Raiz '.env')) }
  foreach ($arquivo in $script:ArquivosCompose) { $opcoes += @('-f', (Join-Path $Raiz $arquivo)) }
  return ,($opcoes + @('--profile', 'orientacao'))
}

function Get-VariaveisCompose {
  param([string]$Raiz)
  $nomes = @('COMPOSE_PROJECT_NAME', 'COMPOSE_FILE', 'COMPOSE_PROFILES', 'COMPOSE_ENV_FILES', 'COMPOSE_PATH_SEPARATOR',
             'GLICO_REDE_ADMINISTRATIVA', 'ORIENTACAO_MODELO_EMBEDDING', 'ORIENTACAO_MODELO_GERACAO')
  foreach ($linha in Get-Content -LiteralPath (Join-Path $Raiz '.env.example')) {
    if ($linha -match '^([A-Z_][A-Z0-9_]*)=') { $nomes += $Matches[1] }
  }
  return $nomes | Select-Object -Unique
}

function Enter-AmbienteCompose {
  # O Compose dá precedência às variáveis do terminal sobre o .env. Elas são suspensas durante o script
  # para que o .env seja a única fonte e todas as execuções usem as mesmas credenciais e volumes.
  param([string]$Raiz)
  $salvo = @{}
  foreach ($nome in Get-VariaveisCompose $Raiz) {
    $salvo[$nome] = [Environment]::GetEnvironmentVariable($nome, 'Process')
    [Environment]::SetEnvironmentVariable($nome, $null, 'Process')
  }
  return $salvo
}

function Exit-AmbienteCompose {
  param([hashtable]$Salvo)
  foreach ($nome in $Salvo.Keys) {
    [Environment]::SetEnvironmentVariable($nome, $Salvo[$nome], 'Process')
  }
}

function Read-ArquivoEnv {
  param([string]$Arquivo)
  $valores = @{}
  if (Test-Path -LiteralPath $Arquivo -PathType Leaf) {
    foreach ($linha in Get-Content -LiteralPath $Arquivo -Encoding UTF8) {
      if ($linha -match '^([A-Z_][A-Z0-9_]*)=(.*)$') { $valores[$Matches[1]] = $Matches[2] }
    }
  }
  return $valores
}
