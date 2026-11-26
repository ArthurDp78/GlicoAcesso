#Requires -Version 5.1
<#
.SYNOPSIS
  Inicia o GlicoAcesso completo, inclusive a orientação com RAG, com um único comando.

.DESCRIPTION
  Gera ou completa o .env com credenciais aleatórias e distintas, pede a GOOGLE_API_KEY quando ela
  ainda não estiver configurada, sincroniza o índice da orientação e sobe todos os serviços.
  Pode ser executado de novo a qualquer momento: credenciais, dados e embeddings são reaproveitados.

.EXAMPLE
  .\iniciar.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$raiz = $PSScriptRoot
. (Join-Path $raiz 'scripts/compose-glicoacesso.ps1')
$arquivoEnv = Join-Path $raiz '.env'
$perguntaTeste = 'Qual código devo levar ao balcão e onde vejo as orientações para retirar uma reserva confirmada?'

function Write-Etapa([string]$Texto) { Write-Host ''; Write-Host "==> $Texto" -ForegroundColor Cyan }

function Test-ChaveValida([string]$Chave) {
  # Mesmas restrições do configurador para valores do .env: sem espaços, aspas, $, # ou barra invertida.
  return ($Chave -match '^[!-~]{20,}$') -and ($Chave -notmatch '[''"$#\\]')
}

function Read-ChaveGoogle {
  if ([Console]::IsInputRedirected) { return '' }
  Write-Host 'A orientação com IA usa uma chave do Google AI Studio: https://aistudio.google.com/apikey'
  Write-Host 'A chave fica somente no .env local, que não vai para o Git. Pressione Enter sem digitar'
  Write-Host 'nada para continuar sem IA: o portal mantém a orientação básica.'
  for ($tentativa = 1; $tentativa -le 3; $tentativa++) {
    $segura = Read-Host -AsSecureString 'GOOGLE_API_KEY'
    $ponteiro = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($segura)
    try { $chave = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ponteiro)).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ponteiro) }
    if (-not $chave -or (Test-ChaveValida $chave)) { return $chave }
    Write-Warning 'A chave contém caracteres inválidos ou é curta demais. Tente de novo.'
  }
  return ''
}

function Save-ChaveGoogle([string]$Chave) {
  $linhas = [Collections.Generic.List[string]]([IO.File]::ReadAllLines($arquivoEnv))
  $indice = $linhas.FindIndex({ param($linha) $linha -match '^GOOGLE_API_KEY=' })
  if ($indice -ge 0) { $linhas[$indice] = "GOOGLE_API_KEY=$Chave" } else { $linhas.Add("GOOGLE_API_KEY=$Chave") }
  # Reescreve o mesmo arquivo, preservando suas permissões, em UTF-8 sem BOM.
  [IO.File]::WriteAllText($arquivoEnv, (($linhas -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
}

function Test-PortaOcupada([int]$Porta) {
  $cliente = New-Object Net.Sockets.TcpClient
  try {
    $tentativa = $cliente.BeginConnect('127.0.0.1', $Porta, $null, $null)
    return ($tentativa.AsyncWaitHandle.WaitOne(500) -and $cliente.Connected)
  } catch { return $false } finally { $cliente.Close() }
}

function Get-EstadoOrientacao([string]$Url, [string]$TokenCidadao, [bool]$TemChave, [int]$Trechos) {
  if (-not $TemChave) {
    return @{ Cor = 'Yellow'; Texto = 'IA desativada: GOOGLE_API_KEY não configurada. O portal usa a orientação básica.' }
  }
  if ($Trechos -le 0) {
    return @{ Cor = 'Yellow'; Texto = 'IA não operacional: o índice da base de conhecimento está vazio. O portal usa a orientação básica.' }
  }
  try {
    # Sem @(): no Windows PowerShell 5.1 a lista JSON chega como um único objeto e o pipeline a enumera.
    $itens = Invoke-RestMethod -Uri "$Url/api/cidadao/v1/itens" -TimeoutSec 10 -UseBasicParsing
    $item = $itens | Where-Object nome -like 'Tiras reagentes*' | Select-Object -First 1
    if (-not $item) { $item = $itens | Select-Object -First 1 }
    if (-not $item) { return @{ Cor = 'Yellow'; Texto = 'Sem itens no catálogo para testar a orientação.' } }
    $corpo = @{ itemId = $item.itemId; pergunta = $perguntaTeste } | ConvertTo-Json -Compress
    $resposta = Invoke-RestMethod -Uri "$Url/api/cidadao/v1/orientacoes" -Method Post -TimeoutSec 25 -UseBasicParsing `
      -Headers @{ Authorization = "Bearer $TokenCidadao" } -ContentType 'application/json; charset=utf-8' `
      -Body ([Text.Encoding]::UTF8.GetBytes($corpo))
  } catch {
    return @{ Cor = 'Yellow'; Texto = "Orientação não respondeu ao teste ($($_.Exception.Message)). Tente de novo em instantes." }
  }
  if ($resposta.modo -eq 'rag') {
    return @{ Cor = 'Green'; Texto = "IA operacional (RAG com $Trechos trechos indexados)." }
  }
  return @{ Cor = 'Yellow'; Texto = 'IA não operacional: o provedor recusou ou não respondeu (chave, cota ou rede). ' +
            'O portal usa a orientação básica, com a disponibilidade real. Confira a chave no .env e execute de novo.' }
}

$ambiente = $null
$chave = $null
try {
  Write-Etapa 'Verificando o Docker'
  Assert-Docker
  Write-Host 'Docker e Docker Compose disponíveis.'

  Write-Etapa 'Preparando o .env'
  $primeiraVez = -not (Test-Path -LiteralPath $arquivoEnv)
  $opcoesPython = @('run', '--rm', '--network', 'none', '--volume', "${raiz}:/repo", '--workdir', '/repo')
  if ($IsLinux -or $IsMacOS) { $opcoesPython += @('--user', "$(& id -u):$(& id -g)") }
  # Reaproveita o configurador: preserva valores existentes e gera só os campos faltantes, sem imprimi-los.
  $codigo = Invoke-Docker ($opcoesPython + @($script:ImagemPython, 'python', 'scripts/configurar-compose.py'))
  if ($codigo -ne 0) { throw 'Não foi possível gerar ou validar o .env. Veja a mensagem acima.' }
  if ($primeiraVez) { Write-Host '.env criado com credenciais aleatórias e distintas.' }
  else { Write-Host '.env existente preservado; campos faltantes foram completados.' }

  $valores = Read-ArquivoEnv $arquivoEnv
  $chaveNoTerminal = [Environment]::GetEnvironmentVariable('GOOGLE_API_KEY', 'Process')
  if (-not $valores.GOOGLE_API_KEY) {
    if ($chaveNoTerminal -and (Test-ChaveValida $chaveNoTerminal.Trim())) {
      $chave = $chaveNoTerminal.Trim()
      Write-Host 'GOOGLE_API_KEY encontrada no terminal; gravada no .env local.'
    } else {
      $chave = Read-ChaveGoogle
    }
    if ($chave) { Save-ChaveGoogle $chave; Write-Host 'Chave gravada no .env local.' }
    $valores = Read-ArquivoEnv $arquivoEnv
  }
  $chave = $null
  $temChave = [bool]$valores.GOOGLE_API_KEY

  $ambiente = Enter-AmbienteCompose $raiz
  $compose = Get-OpcoesCompose $raiz
  $porta = 8000
  if ($valores.GLICO_GATEWAY_PORTA) { $porta = [int]$valores.GLICO_GATEWAY_PORTA }
  $gatewayAtivo = Get-SaidaDocker ($compose + @('ps', '--status', 'running', '--quiet', 'gateway'))
  if (-not ($gatewayAtivo.Linhas | Where-Object { $_ }) -and (Test-PortaOcupada $porta)) {
    throw "A porta $porta já está em uso por outro programa. Altere GLICO_GATEWAY_PORTA no .env e execute de novo."
  }

  $indexacao = 'não executada'
  if ($temChave) {
    Write-Etapa 'Sincronizando a base de conhecimento da orientação'
    Write-Host 'Somente trechos novos ou alterados geram embeddings; os demais são reaproveitados.'
    $codigo = Invoke-Docker ($compose + @('--profile', 'indexacao', 'run', '--build', '--rm', '-T', 'indexar-orientacao'))
    if ($codigo -eq 0) { $indexacao = 'sincronizada' }
    else {
      $indexacao = 'falhou'
      Write-Warning 'A indexação falhou. O sistema será iniciado assim mesmo; um índice anterior continua válido e, sem ele, o portal usa a orientação básica.'
    }
  } else {
    Write-Host ''
    Write-Host 'Sem GOOGLE_API_KEY: a indexação foi pulada e a orientação usará o modo básico.' -ForegroundColor Yellow
  }

  Write-Etapa 'Iniciando os serviços (a primeira execução constrói as imagens e pode levar alguns minutos)'
  $codigo = Invoke-Docker ($compose + @('up', '--build', '-d', '--wait'))
  if ($codigo -ne 0) {
    Write-Warning 'Algum serviço não ficou saudável. Estado atual e últimos logs:'
    Invoke-Docker ($compose + @('ps', '--all')) | Out-Null
    Invoke-Docker ($compose + @('logs', '--no-color', '--tail', '20')) | Out-Null
    throw 'Falha ao iniciar o GlicoAcesso. Corrija o problema indicado nos logs e execute .\iniciar.ps1 de novo.'
  }

  Write-Etapa 'Verificando a orientação'
  $contagem = Get-SaidaDocker ($compose + @('exec', '-T', 'db-orientacao', 'psql', '-XAt', '-U', 'glico', '-d', 'orientacao',
                                           '-c', 'SELECT count(*) FROM trechos_conhecimento'))
  $trechos = 0
  if ($contagem.Codigo -eq 0) { [void][int]::TryParse(([string]$contagem.Linhas[0]).Trim(), [ref]$trechos) }
  $url = "http://127.0.0.1:$porta"
  $estado = Get-EstadoOrientacao $url $valores.GLICO_CIDADAO_TOKEN $temChave $trechos

  Write-Host ''
  Write-Host 'GlicoAcesso em execução.' -ForegroundColor Green
  Write-Host "  Portal do cidadão:      $url/cidadao"
  Write-Host "  Painel da unidade:      $url/unidade"
  Write-Host "  Token do cidadão:       $($valores.GLICO_CIDADAO_TOKEN)"
  Write-Host "  Token do profissional:  $($valores.GLICO_PROFISSIONAL_TOKEN)"
  Write-Host "  Base de conhecimento:   $trechos trechos indexados (indexação $indexacao)"
  Write-Host "  Orientação:             $($estado.Texto)" -ForegroundColor $estado.Cor
  Write-Host ''
  Write-Host 'Para encerrar sem apagar os dados: .\parar.ps1'
} catch {
  Write-Host ''
  Write-Host "Erro: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
} finally {
  $chave = $null
  if ($ambiente) { Exit-AmbienteCompose $ambiente }
}
