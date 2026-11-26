# Roteiro de validação e apresentação da Parte 4

A validação automatizada cria um projeto temporário com credenciais, contêineres e volumes próprios. A opção `-ComOrientacao` testa a orientação na mesma execução do fluxo distribuído. O ensaio visual usa um projeto separado e mantém os dados para consultas no navegador.

## Validação automatizada

Abra o Docker Desktop em modo de contêineres Linux e execute no PowerShell 7, na raiz do projeto.

```powershell
docker info --format '{{.ServerVersion}}'
.\scripts\validar-compose.ps1 -ComOrientacao
```

Sem chave do Google AI Studio no processo, o roteiro valida os 16 serviços, o domínio e a orientação básica com disponibilidade. Para testar também a indexação e a resposta gerada com a fonte `retirada#balcao`, informe sua chave da API antes de executar:

```powershell
$env:GOOGLE_API_KEY = Read-Host -MaskInput 'Chave da API Google AI Studio'
.\scripts\validar-compose.ps1 -ComOrientacao
```

Use `-Porta 18081` se a porta 18080 estiver ocupada. O roteiro cadastra uma unidade, registra estoque, verifica confirmação, retirada e cancelamento, provoca uma falha da SAGA e confere a persistência. Com a chave configurada, indexa os guias, exige resposta em modo RAG, confere que o índice sobrevive à recriação e desliga a chave no serviço temporário para validar o fallback. Se a resposta vier em modo básico na etapa que exige RAG, o roteiro informa a falha. A mensagem final **Validação concluída** indica que todas as verificações habilitadas passaram. O roteiro restaura as variáveis do processo e remove os recursos temporários.

## Preparar a demonstração visual

Crie o `.env` conforme o [README](../../README.md#subir-o-sistema-completo-com-docker-compose). Em uma instalação existente, confira especialmente `ORIENTACAO_DB_PASSWORD`, `GLICO_ORIENTACAO_SERVICE_TOKEN`, `GLICO_RETIRADAS_SERVICE_TOKEN` e `GLICO_BFF_CIDADAO_SIGNING_KEY`. Defina valores aleatórios distintos, mantendo as senhas dos bancos que já tenham volume. Configure `GOOGLE_API_KEY` com uma chave criada no Google AI Studio e confirme que os modelos selecionados estão disponíveis para ela.

```powershell
$env:GOOGLE_API_KEY = Read-Host -MaskInput 'Chave da API Google AI Studio'
$env:GLICO_GATEWAY_PORTA = '18083'
$env:GLICO_REDE_ADMINISTRATIVA = 'glico-parte4-admin'
$env:GLICO_CARREGAR_DEMO = '1'
$env:GLICO_FALHA_PREPARAR_AUTORIZACAO = '0'

$compose = @('-p', 'glico-parte4', '-f', 'docker-compose.yml', '-f', 'compose.orientacao.yml', '--profile', 'orientacao')
docker compose @compose --profile indexacao run --build --rm indexar-orientacao
docker compose @compose up --build -d --wait
docker compose @compose ps
```

Use o [portal cidadão](http://127.0.0.1:18083/cidadao) e o [painel da unidade](http://127.0.0.1:18083/unidade). Informe os tokens `GLICO_CIDADAO_TOKEN` e `GLICO_PROFISSIONAL_TOKEN` do seu `.env` nos respectivos portais.

## Sequência da apresentação ao vivo

1. **Domínio e CQRS.** Selecione **Tiras reagentes para glicemia** na unidade de demonstração, consulte a disponibilidade e anote o saldo no painel profissional. Crie uma reserva de uma unidade e aceite no painel. Aguarde `CONFIRMADA` e mostre a alocação no estoque. Registre a entrega no balcão, aguarde `RETIRADA` e mostre a baixa física e o encerramento da alocação.
2. **Compensação da SAGA.** Ative a falha temporária abaixo, crie outra reserva para um item com saldo e aceite-a. O portal deve chegar a `FALHA_CONFIRMACAO`. Mostre `COMPENSADA`, a alocação liberada, o saldo recomposto e a ausência de autorização. O validador automatizado checa os quatro efeitos.
3. **Bancos separados.** Mostre com `docker compose @compose ps` os cinco PostgreSQL do domínio e da coordenação, além de `db-orientacao` com pgvector. Só o Gateway publica porta.
4. **RAG.** No portal cidadão, selecione o item e use **Pedir orientação**. Pergunte *“Qual código devo levar ao balcão e onde vejo as orientações para retirar uma reserva confirmada?”*. Mostre a fonte do guia e a disponibilidade com seu horário de atualização. Diferencie a informação do BFF dos trechos documentais.
5. **Fallback.** Recrie apenas Orientação sem chave conforme o bloco abaixo. Repita a pergunta e mostre **Orientação básica** junto com os dados reais, se o BFF responder. Apresente os [seis pares da avaliação](./02-avaliacao-rag.md) e as [medições e projeções](./03-desempenho-e-custo.md), mostrando os resultados da configuração Gemini e identificando a comparação histórica com Ollama.

### Provocar a compensação

```powershell
$env:GLICO_FALHA_PREPARAR_AUTORIZACAO = '1'
docker compose @compose up -d --no-deps --force-recreate --wait retiradas
# Aceite uma nova reserva e aguarde FALHA_CONFIRMACAO.
$reservaFalha = [guid](Read-Host 'Código da reserva que falhou')
docker compose @compose exec -T db-orquestrador psql -U glico -d orquestrador -c "SELECT estado FROM saga_execucoes WHERE reserva_id='$reservaFalha' AND tipo='CONFIRMACAO';"
docker compose @compose exec -T db-estoque psql -U glico -d estoque -c "SELECT liberada_em IS NOT NULL AS liberada, consumida_em IS NOT NULL AS consumida FROM alocacoes WHERE reserva_id='$reservaFalha';"
docker compose @compose exec -T db-retiradas psql -U glico -d retiradas -c "SELECT count(*) FROM autorizacoes WHERE reserva_id='$reservaFalha';"
$env:GLICO_FALHA_PREPARAR_AUTORIZACAO = '0'
docker compose @compose up -d --no-deps --force-recreate --wait retiradas
```

### Demonstrar o fallback

```powershell
$chaveAnterior = $env:GOOGLE_API_KEY
try {
  $env:GOOGLE_API_KEY = ' '
  docker compose @compose up -d --no-deps --force-recreate --wait orientacao
  Read-Host 'Repita a pergunta no portal e pressione Enter para restaurar a chave'
} finally {
  $env:GOOGLE_API_KEY = $chaveAnterior
  docker compose @compose up -d --no-deps --force-recreate --wait orientacao
  Remove-Variable chaveAnterior
}
```

O espaço faz o processo tratar a chave como ausente mesmo quando existe uma chave no `.env`. Com a demonstração encerrada, `docker compose @compose down` para os contêineres e preserva os volumes.

## Ensaio de escalabilidade no Compose

No projeto de demonstração preparado acima, execute `docker compose @compose up -d --wait --scale unidades=2 unidades` e `docker compose @compose ps unidades`. Confira duas instâncias saudáveis de Unidades, consulte as unidades pelo portal e volte a uma réplica com `docker compose @compose up -d --wait --scale unidades=1 unidades`. As duas réplicas usam o mesmo banco do serviço. O ensaio verifica replicação da API e continuidade da consulta. Medir ganho de vazão exige um teste de carga separado.
