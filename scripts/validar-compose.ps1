param([ValidateRange(1024, 65535)][int]$Porta = 18080)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$raiz = Split-Path -Parent $PSScriptRoot
$modelo = Join-Path $raiz '.env.example'
$execucao = 'glico-val-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$arquivo = Join-Path ([IO.Path]::GetTempPath()) "$execucao-unidade.json"
$url = "http://127.0.0.1:$Porta"
$principal = @('--project-directory', $raiz, '--env-file', $modelo, '-p', $execucao,
               '-f', (Join-Path $raiz 'docker-compose.yml'))
$admin = @('--project-directory', $raiz, '--env-file', $modelo, '-p', "$execucao-admin",
           '-f', (Join-Path $raiz 'compose.admin.yml'), '--profile', 'admin')

function Executar-Compose {
  param([string[]]$Opcoes, [string[]]$Comando)
  & docker compose @Opcoes @Comando
  if ($LASTEXITCODE -ne 0) { throw "Falha no Compose ($($Comando[0]), código $LASTEXITCODE)." }
}

function Conferir {
  param([bool]$Condicao, [string]$Detalhe)
  if (-not $Condicao) { throw $Detalhe }
}

function Requisitar {
  param([string]$Caminho, [int]$Status = 200, [string]$Token = '', [string]$Chave = '', [hashtable]$Corpo, [string]$Metodo = 'POST', [string]$Correlacao = '')
  $cabecalhos = @{}
  if ($Token) { $cabecalhos.Authorization = "Bearer $Token" }
  if ($Chave) { $cabecalhos['Idempotency-Key'] = $Chave }
  if ($Correlacao) { $cabecalhos['X-Correlation-Id'] = $Correlacao }
  $opcoes = @{ Uri = "$url$Caminho"; Headers = $cabecalhos; TimeoutSec = 12; UseBasicParsing = $true }
  if ($null -ne $Corpo -or $PSBoundParameters.ContainsKey('Metodo')) {
    $opcoes.Method = $Metodo
  }
  if ($null -ne $Corpo) {
    $opcoes.ContentType = 'application/json; charset=utf-8'
    $opcoes.Body = [Text.Encoding]::UTF8.GetBytes(($Corpo | ConvertTo-Json -Depth 6 -Compress))
  }
  $resposta = Invoke-WebRequest @opcoes
  Conferir ($resposta.StatusCode -eq $Status) "$Caminho retornou HTTP $($resposta.StatusCode) em vez de $Status."
  if ($Correlacao) {
    Conferir ([string]$resposta.Headers['X-Correlation-Id'] -eq $Correlacao) "$Caminho não devolveu a correlação enviada."
  }
  if ($resposta.Headers['Content-Type'] -like 'application/json*') {
    return ($resposta.Content | ConvertFrom-Json)
  }
  return $resposta.Content
}

function Aguardar {
  param([scriptblock]$Condicao, [string]$Detalhe)
  $limite = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $limite) {
    if (& $Condicao) { return }
    Start-Sleep -Milliseconds 700
  }
  throw $Detalhe
}

function Cadastrar-Unidade {
  $saida = @(Executar-Compose $admin @('run', '--rm', '-T', '--volume', "${arquivo}:/dados/unidade.json:ro",
                                     'cadastro-unidades', '--arquivo', '/dados/unidade.json', '--chave', $chaveCadastro))
  $id = [guid]::Empty
  Conferir ($saida.Count -eq 1 -and [guid]::TryParse(([string]$saida[0]).Trim(), [ref]$id)) 'CLI não retornou um UUID.'
  return $id.ToString()
}

function Conferir-Subida {
  $ids = @(Executar-Compose $principal @('ps', '--status', 'running', '-q'))
  Conferir ($ids.Count -eq 14) "Esperados 14 serviços em execução. Encontrados $($ids.Count)."
  Conferir ((Requisitar '/health').servico -eq 'gateway') 'Gateway não respondeu à checagem de saúde.'
}

function Saldo-Confere {
  param([switch]$AposRetirada)
  $fisico = if ($AposRetirada) { 2 } else { 4 }
  $alocado = if ($AposRetirada) { 0 } else { 2 }
  $saldos = @(Requisitar '/api/unidade/v1/painel/estoque' -Token $profissional)
  $med = $saldos | Where-Object itemId -eq $medicamento
  return ($med.estoqueFisicoAtual -eq $fisico -and $med.quantidadeAlocada -eq $alocado -and
          $med.quantidadeDisponivel -eq 2 -and $med.permiteReserva -eq $true)
}

docker info --format '{{.ServerVersion}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Abra o Docker Desktop em modo de contêineres Linux e tente novamente.' }
Conferir (Test-Path -LiteralPath $modelo -PathType Leaf) '.env.example ausente no repositório.'

$valores = @{}
$anteriores = @{}
$gerador = [Security.Cryptography.RandomNumberGenerator]::Create()
$iniciado = $false
try {
  foreach ($linha in Get-Content -LiteralPath $modelo) {
    if ($linha -match '^([A-Z0-9_]+)=(.*)$') {
      $nome = $Matches[1]
      $valor = $Matches[2]
      if ($valor -eq '') {
        $bytes = New-Object byte[] 32
        $gerador.GetBytes($bytes)
        $valor = [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
      }
      $valores[$nome] = $valor
    }
  }
  $valores.GLICO_GATEWAY_PORTA = [string]$Porta
  $valores.GLICO_REDE_ADMINISTRATIVA = "$execucao-rede"
  $valores.GLICO_CARREGAR_DEMO = '1'
  $valores.GLICO_FALHA_PREPARAR_AUTORIZACAO = '0'
  foreach ($nome in $valores.Keys) {
    $anteriores[$nome] = [Environment]::GetEnvironmentVariable($nome, 'Process')
    [Environment]::SetEnvironmentVariable($nome, $valores[$nome], 'Process')
  }

  $cidadao = $valores.GLICO_CIDADAO_TOKEN
  $profissional = $valores.GLICO_PROFISSIONAL_TOKEN
  $unidade = $valores.GLICO_PROFISSIONAL_UNIDADE_ID
  $medicamento = '31a8296a-87a9-58ef-b8fc-a2248dab22b3'
  $chaveCadastro = [guid]::NewGuid().ToString()
  $cadastro = @{
    nome = 'Unidade da validação'; logradouro = 'Rua da Validação'; numero = '20'
    bairro = 'Centro'; cidade = 'Cidade de Teste'; estado = 'MG'; cep = '30000-000'
    orientacoesRetirada = 'Apresente a confirmação.'; prazoAnaliseHoras = 24
    contatos = @(); horarios = @(@{diaSemana = 1; horarioInicial = '08:00'; horarioFinal = '17:00'})
  }
  [IO.File]::WriteAllText($arquivo, ($cadastro | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))

  Write-Host "Subindo o ambiente isolado $execucao..."
  $iniciado = $true
  Executar-Compose $principal @('up', '--build', '-d', '--wait', '--wait-timeout', '180')
  Conferir-Subida
  Conferir ((Requisitar '/cidadao') -match '<title>') 'O portal do cidadão não respondeu.'
  Conferir ((Requisitar '/unidade') -match '<title>') 'O portal da unidade não respondeu.'

  Write-Host 'Cadastrando unidade pela CLI...'
  Executar-Compose $admin @('build', 'cadastro-unidades')
  $cadastrada = Cadastrar-Unidade
  $unidades = @(Requisitar '/api/cidadao/v1/unidades')
  Conferir (@($unidades | Where-Object unidadeId -eq $cadastrada).Count -eq 1) 'Unidade cadastrada ausente da lista pública.'

  Write-Host 'Registrando entrada e confirmando reserva...'
  $catalogo = Requisitar '/api/unidade/v1/painel/estoque/catalogo' -Token $profissional
  Conferir ($catalogo.unidadeId -eq $unidade -and $catalogo.itens.itemId -contains $medicamento) 'Catálogo do profissional incompleto.'
  $rotaEntrada = "/api/unidade/v1/painel/estoque/$unidade/itens/$medicamento/entradas"
  $chaveEntrada = [guid]::NewGuid().ToString()
  $entrada = Requisitar $rotaEntrada -Status 201 -Token $profissional -Chave $chaveEntrada -Corpo @{quantidade = 4}
  $repeticao = Requisitar $rotaEntrada -Status 201 -Token $profissional -Chave $chaveEntrada -Corpo @{quantidade = 4}
  Conferir ($entrada.movimentacaoId -and $entrada.movimentacaoId -eq $repeticao.movimentacaoId) 'A entrada foi duplicada.'

  $rotaPermissao = "/api/unidade/v1/painel/estoque/$unidade/itens/$medicamento/permissao"
  $chavePermissao = [guid]::NewGuid().ToString()
  $correlacao = [guid]::NewGuid().ToString()
  $permissao = Requisitar $rotaPermissao -Metodo PUT -Token $profissional -Chave $chavePermissao -Corpo @{permiteReserva = $true}
  Conferir ($permissao.permiteReserva -eq $true) 'A permissão de reserva não foi habilitada.'
  Aguardar {
    $opcoesMedicamento = @(Requisitar "/api/cidadao/v1/explorar?itemId=$medicamento")
    $disponivel = $opcoesMedicamento | Where-Object unidadeId -eq $unidade
    $disponivel.disponivel -and $disponivel.permiteReserva
  } 'O portal do cidadão não recebeu a permissão na projeção.'
  $pedido = @{unidadeId = $unidade; itemId = $medicamento; quantidade = 2}
  $reserva = Requisitar '/api/cidadao/v1/reservas' -Status 201 -Token $cidadao -Chave ([guid]::NewGuid().ToString()) -Corpo $pedido
  Conferir ($reserva.status -eq 'SOLICITADA') 'A reserva não foi criada como SOLICITADA.'
  $pendentes = @(Requisitar '/api/unidade/v1/painel/reservas' -Token $profissional)
  Conferir (@($pendentes | Where-Object reservaId -eq $reserva.reservaId).Count -eq 1) 'Reserva ausente do painel da unidade.'
  $decisao = "/api/unidade/v1/reservas/$($reserva.reservaId)/decisao"
  Requisitar $decisao -Status 202 -Token $profissional -Chave ([guid]::NewGuid().ToString()) -Corpo @{decisao = 'ACEITAR'} -Correlacao $correlacao | Out-Null
  $rotaReserva = "/api/cidadao/v1/reservas/$($reserva.reservaId)"
  Aguardar { (Requisitar $rotaReserva -Token $cidadao).status -eq 'CONFIRMADA' } 'A SAGA não confirmou a reserva.'
  Aguardar { Saldo-Confere } 'A projeção não refletiu a entrada e a alocação.'
  $explorar = @(Requisitar "/api/cidadao/v1/explorar?itemId=$medicamento")
  $disponibilidade = $explorar | Where-Object unidadeId -eq $unidade
  Conferir ($disponibilidade.disponivel -and $disponibilidade.permiteReserva -eq $true) 'Consulta pública de disponibilidade divergente.'

  Write-Host 'Registrando a retirada no balcão...'
  $rotaPainel = "/api/unidade/v1/painel/reservas/$($reserva.reservaId)"
  $detalhe = Requisitar $rotaPainel -Token $profissional
  $acao = $detalhe._links.'autorizacao-retirada'
  Conferir ($detalhe.dadosAutorizacao.status -eq 'ATIVA' -and $acao.href -eq '/api/unidade/v1/retiradas') 'Autorização ativa ausente no painel.'
  $corpoRetirada = @{autorizacaoId = $acao.body.autorizacaoId}
  $chaveRetirada = [guid]::NewGuid().ToString()
  $entrega = Requisitar $acao.href -Status 201 -Token $profissional -Chave $chaveRetirada -Corpo $corpoRetirada
  Conferir ([bool]$entrega.retiradaId) 'Identificador da retirada ausente.'
  Conferir ((Requisitar $rotaPainel -Token $profissional).dadosAutorizacao.status -eq 'UTILIZADA') 'A autorização ainda aparece como ativa.'

  Aguardar { (Requisitar $rotaReserva -Token $cidadao).status -eq 'RETIRADA' } 'Reservas não recebeu a entrega.'
  Aguardar { Saldo-Confere -AposRetirada } 'A baixa física ou a projeção da retirada não convergiu.'

  Write-Host 'Verificando cancelamentos local e distribuído...'
  $pedidoCancelamento = @{unidadeId = $unidade; itemId = $medicamento; quantidade = 1}
  $local = Requisitar '/api/cidadao/v1/reservas' -Status 201 -Token $cidadao -Chave ([guid]::NewGuid().ToString()) -Corpo $pedidoCancelamento
  $rotaLocal = "/api/cidadao/v1/reservas/$($local.reservaId)/cancelar"
  $localCancelada = Requisitar $rotaLocal -Metodo POST -Token $cidadao -Chave ([guid]::NewGuid().ToString())
  Conferir ($localCancelada.status -eq 'CANCELADA') 'Cancelamento local não concluído.'

  $distribuida = Requisitar '/api/cidadao/v1/reservas' -Status 201 -Token $cidadao -Chave ([guid]::NewGuid().ToString()) -Corpo $pedidoCancelamento
  $rotaDistribuida = "/api/cidadao/v1/reservas/$($distribuida.reservaId)"
  $rotaAceite = "/api/unidade/v1/reservas/$($distribuida.reservaId)/decisao"
  Requisitar $rotaAceite -Status 202 -Token $profissional -Chave ([guid]::NewGuid().ToString()) -Corpo @{decisao = 'ACEITAR'} | Out-Null
  Aguardar { (Requisitar $rotaDistribuida -Token $cidadao).status -eq 'CONFIRMADA' } 'Reserva para cancelamento não confirmada.'
  $chaveCancelamento = [guid]::NewGuid().ToString()
  Requisitar "$rotaDistribuida/cancelar" -Metodo POST -Status 202 -Token $cidadao -Chave $chaveCancelamento | Out-Null
  Aguardar { (Requisitar $rotaDistribuida -Token $cidadao).status -eq 'CANCELADA' } 'Cancelamento distribuído não concluído.'
  Aguardar { Saldo-Confere -AposRetirada } 'O cancelamento não liberou a alocação.'

  Write-Host 'Recriando os contêineres com os mesmos volumes...'
  Executar-Compose $principal @('down')
  Executar-Compose $principal @('up', '-d', '--wait', '--wait-timeout', '180')
  Conferir-Subida
  Conferir ((Cadastrar-Unidade) -eq $cadastrada) 'A resposta idempotente da CLI se perdeu após a recriação.'
  $unidades = @(Requisitar '/api/cidadao/v1/unidades')
  Conferir (@($unidades | Where-Object unidadeId -eq $cadastrada).Count -eq 1) 'Cadastro perdido após a recriação.'
  Conferir ((Requisitar $rotaReserva -Token $cidadao).status -eq 'RETIRADA') 'Estado RETIRADA perdido após a recriação.'
  $repeticao = Requisitar $rotaEntrada -Status 201 -Token $profissional -Chave $chaveEntrada -Corpo @{quantidade = 4}
  Conferir ($repeticao.movimentacaoId -eq $entrada.movimentacaoId) 'Movimentação ou idempotência perdida após a recriação.'
  Conferir (Saldo-Confere -AposRetirada) 'Projeção divergente após a recriação.'
  Conferir ((Requisitar $rotaDistribuida -Token $cidadao).status -eq 'CANCELADA') 'Cancelamento perdido após a recriação.'
  Requisitar "$rotaDistribuida/cancelar" -Metodo POST -Status 202 -Token $cidadao -Chave $chaveCancelamento | Out-Null
  $repeticaoEntrega = Requisitar $acao.href -Status 201 -Token $profissional -Chave $chaveRetirada -Corpo $corpoRetirada
  Conferir ($repeticaoEntrega.retiradaId -eq $entrega.retiradaId) 'Retirada ou idempotência perdida após a recriação.'
  Write-Host 'Validação concluída: 14 serviços, portais, CLI, SAGA, retirada, CQRS e persistência.' -ForegroundColor Green
} catch {
  if ($iniciado) {
    & docker compose @principal ps --all
    & docker compose @principal logs --no-color --tail 15
  }
  throw
} finally {
  if ($iniciado) {
    & docker compose @principal down --volumes --remove-orphans
    if ($LASTEXITCODE -ne 0) { Write-Warning "Não foi possível limpar o projeto de teste $execucao." }
  }
  foreach ($nome in $anteriores.Keys) {
    [Environment]::SetEnvironmentVariable($nome, $anteriores[$nome], 'Process')
  }
  if (Test-Path -LiteralPath $arquivo -PathType Leaf) { Remove-Item -LiteralPath $arquivo }
  $gerador.Dispose()
}
