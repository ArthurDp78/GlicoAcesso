# GlicoAcesso — desenvolvimento local

Instruções para executar os serviços Python diretamente no computador, sem a imagem Docker de cada aplicação. Para usar o sistema, prefira `.\iniciar.ps1` (ou `./iniciar.sh` no Linux), descrito no [README](../README.md#como-executar).

## Demonstração com serviços Python no Windows

Pré-requisitos: Docker Desktop aberto e [uv](https://docs.astral.sh/uv/getting-started/installation/) instalado. Na raiz do repositório, em um PowerShell:

```powershell
.\scripts\demo-local.ps1
```

O script faz o seguinte:
- sobe os cinco PostgreSQL e o RabbitMQ em Docker;
- gera os tokens de demonstração uma única vez e os guarda em `.demo-local/`, que fica fora do Git;
- aplica as migrações e inicia os oito processos em segundo plano;
- mostra os endereços dos portais e os tokens.

Se a porta 8000 estiver ocupada, use `-GatewayPorta 8010`. As outras opções:
- `-FalharRetiradas`: Retiradas passa a recusar as autorizações, para demonstrar a compensação.
- `-Zerar`: apaga os bancos e a fila de demonstração e começa do estado inicial.
- `-Parar`: encerra os processos.

Os logs ficam em `.demo-local/logs`. Se o Windows bloquear a execução de scripts, use `powershell -ExecutionPolicy Bypass -File .\scripts\demo-local.ps1`.

As seções abaixo descrevem cada processo separadamente, para quem quiser subir serviço por serviço.

Este exemplo de desenvolvimento inicia apenas o API Gateway e o BFF Cidadão. Para executar o fluxo completo, use o Docker Compose descrito acima. Use [uv](https://docs.astral.sh/uv/getting-started/installation/) na raiz do repositório. O `uv` seleciona o Python 3.14 indicado em `.python-version` e instala as versões registradas em `uv.lock`.

```powershell
uv sync --locked
```

Inicie os serviços em terminais separados:

| Serviço | Comando |
|---|---|
| API Gateway | `uv run --locked uvicorn servicos.gateway.main:app --host 127.0.0.1 --port 8000` |
| BFF Cidadão | `uv run --locked uvicorn servicos.bff_cidadao.main:app --host 127.0.0.1 --port 8001` |

Configure endereço e porta no comando de cada processo. Os dois serviços expõem `GET /health` e identificam qual processo está respondendo. Esse endpoint verifica o processo HTTP. A verificação de dependências entra quando os serviços passarem a usá-las.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8001/health
```

## Unidades e Estoque

A etapa de consultas usa dois PostgreSQL 17 independentes. Em um PowerShell com Docker Desktop em execução, crie os bancos locais de demonstração:

```powershell
docker run -d --name glico-unidades-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=unidades -p 127.0.0.1:54331:5432 -v glico-unidades-data:/var/lib/postgresql/data postgres:17
docker run -d --name glico-estoque-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=estoque -p 127.0.0.1:54332:5432 -v glico-estoque-data:/var/lib/postgresql/data postgres:17
```

Esses comandos são para a primeira execução. Nos próximos usos, inicie os contêineres existentes com `docker start glico-unidades-db glico-estoque-db`. Aguarde os bancos aceitarem conexões antes de aplicar as migrações. As credenciais do exemplo são para a demonstração local.

Na raiz do projeto, configure a URL do banco no terminal de cada serviço:

**Unidades (porta 8002)**

```powershell
$env:UNIDADES_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54331/unidades'
uv run --locked python -m servicos.migracoes unidades --demo
uv run --locked uvicorn servicos.unidades.main:app --host 127.0.0.1 --port 8002
```

**Estoque (porta 8003)**

```powershell
$env:ESTOQUE_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54332/estoque'
uv run --locked python -m servicos.migracoes estoque --demo
uv run --locked uvicorn servicos.estoque.main:app --host 127.0.0.1 --port 8003
```

O parâmetro `--demo` carrega uma unidade ativa, um item e 10 unidades disponíveis. Reaplicar as migrações e os dados de demonstração preserva os registros existentes.

```powershell
Invoke-RestMethod 'http://127.0.0.1:8002/api/cidadao/v1/unidades'
Invoke-RestMethod 'http://127.0.0.1:8003/api/cidadao/v1/estoque/itens'
Invoke-RestMethod 'http://127.0.0.1:8003/api/cidadao/v1/estoque/disponibilidade?unidadeId=10000000-0000-4000-8000-000000000001&itemId=20000000-0000-4000-8000-000000000001'
```

## Portal do cidadão

Com os quatro serviços em execução, abra [http://127.0.0.1:8000/cidadao](http://127.0.0.1:8000/cidadao), selecione **Tiras reagentes para glicemia** e clique em **Consultar**. A tela exibe a unidade, o horário, a permissão de reserva e o instante em que a disponibilidade foi atualizada. A disponibilidade vem da projeção inicial de Estoque.

As consultas públicas passam pelo Gateway. Para conferir a resposta agregada em JSON:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/cidadao/v1/explorar?itemId=20000000-0000-4000-8000-000000000001'
```

| Processo | Variável de ambiente | Padrão |
|---|---|---|
| Gateway | `BFF_CIDADAO_URL` | `http://127.0.0.1:8001` |
| BFF Cidadão | `UNIDADES_URL` | `http://127.0.0.1:8002` |
| BFF Cidadão | `ESTOQUE_URL` | `http://127.0.0.1:8003` |

## Criar e consultar reservas

Crie um terceiro PostgreSQL independente para Reservas na primeira execução.

```powershell
docker run -d --name glico-reservas-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=reservas -p 127.0.0.1:54333:5432 -v glico-reservas-data:/var/lib/postgresql/data postgres:17
```

Nas próximas execuções, use `docker start glico-reservas-db`. Gere dois tokens de demonstração distintos com o comando abaixo, executando-o duas vezes.

```powershell
uv run --locked python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Antes de iniciar **Unidades**, **Estoque** e **Reservas**, defina `$env:GLICO_RESERVAS_SERVICE_TOKEN` com o mesmo token interno nos três terminais. O navegador usa o outro token, definido como `GLICO_CIDADAO_TOKEN` no Gateway e em Reservas. O Gateway valida a credencial, e Reservas verifica a identidade e a propriedade da solicitação. As consultas públicas continuam acessíveis sem token. Use essas credenciais apenas na demonstração local.

Em um quinto terminal, após o banco de Reservas aceitar conexões:

```powershell
$env:GLICO_RESERVAS_SERVICE_TOKEN = '<token interno>'
$env:GLICO_CIDADAO_TOKEN = '<token do cidadão>'
$env:RESERVAS_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54333/reservas'
uv run --locked python -m servicos.migracoes reservas
uv run --locked uvicorn servicos.reservas.main:app --host 127.0.0.1 --port 8004
```

O BFF usa `RESERVAS_URL` com padrão `http://127.0.0.1:8004`. Se os serviços já estiverem rodando, reinicie-os com o código atual e com as variáveis necessárias.

No portal, consulte **Tiras reagentes para glicemia**, clique em **Solicitar reserva**, informe o token do cidadão e envie a quantidade desejada. Copie o código retornado para acompanhar a solicitação. A criação retorna `201` e o estado `SOLICITADA`. A alocação de estoque ocorre no fluxo posterior de confirmação.

## Profissional da unidade

O profissional de demonstração usa um terceiro token, diferente dos outros dois, e fica vinculado a uma unidade. Na execução manual, configure o mesmo token e identificador de unidade no Gateway, BFF Unidade, Unidades, Estoque e Reservas para habilitar as rotas protegidas. O vínculo é um atributo da identidade, como o papel. Por isso não fica gravado nos bancos de domínio. Antes de iniciar Reservas, acrescente:

```powershell
$env:GLICO_PROFISSIONAL_TOKEN = '<token do profissional>'
$env:GLICO_PROFISSIONAL_UNIDADE_ID = '10000000-0000-4000-8000-000000000001'
```

A cada requisição, Reservas confere em Unidades se a unidade vinculada existe e está ativa. Se não estiver, responde `403`. Se o token do profissional for igual ao do cidadão, as operações autenticadas respondem `503`. Para listar as solicitações pendentes da unidade:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8004/api/unidade/v1/reservas' -Headers @{ Authorization = 'Bearer <token do profissional>' }
```

A consulta `GET /internal/v1/reservas/{reservaId}` aceita o cidadão dono da reserva ou um profissional da mesma unidade. Um profissional de outra unidade recebe `403`. Um cidadão que não é o dono recebe `404`. O token do profissional não cria reservas (`403`), e o token do cidadão não acessa as rotas da unidade (`403`).

## Painel da unidade e aceite

O aceite é recebido pelo Orquestrador da SAGA, que tem o próprio PostgreSQL (o quarto banco). Na primeira execução:

```powershell
docker run -d --name glico-orquestrador-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=orquestrador -p 127.0.0.1:54334:5432 -v glico-orquestrador-data:/var/lib/postgresql/data postgres:17
```

Nas próximas execuções, use `docker start glico-orquestrador-db`. Gere uma chave exclusiva de assinatura, com pelo menos 32 caracteres aleatórios, pelo mesmo método usado para os tokens de demonstração. Configure o mesmo valor apenas no BFF Unidade e no Orquestrador. O BFF autentica o profissional e envia ao Orquestrador uma credencial Bearer assinada com o papel, a identidade e a unidade do profissional. A credencial expira em 60 segundos.

**Orquestrador (porta 8006)**

```powershell
$env:GLICO_BFF_UNIDADE_SIGNING_KEY = '<chave exclusiva do BFF Unidade>'
$env:ORQUESTRADOR_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54334/orquestrador'
uv run --locked python -m servicos.migracoes orquestrador
uv run --locked uvicorn servicos.orquestrador.main:app --host 127.0.0.1 --port 8006
```

**BFF Unidade (porta 8005)**

```powershell
$env:GLICO_CIDADAO_TOKEN = '<token do cidadão>'
$env:GLICO_PROFISSIONAL_TOKEN = '<token do profissional>'
$env:GLICO_PROFISSIONAL_UNIDADE_ID = '10000000-0000-4000-8000-000000000001'
$env:GLICO_BFF_UNIDADE_SIGNING_KEY = '<chave exclusiva do BFF Unidade>'
uv run --locked uvicorn servicos.bff_unidade.main:app --host 127.0.0.1 --port 8005
```

Para atualizar um ambiente existente, aplique a migração do Orquestrador antes de reiniciar os processos. Ela reconstrói comandos de aceite pendentes gravados no formato inicial e conserva a chave idempotente de cada etapa. O script de demonstração aplica a migração e acrescenta a chave do BFF ao arquivo local de tokens, preservando os tokens já gerados.

Abra [http://127.0.0.1:8000/unidade](http://127.0.0.1:8000/unidade), informe o token do profissional e clique em **Carregar painel**. Cada solicitação pendente mostra **Aceitar** e **Rejeitar**. Os botões vêm dos links `_links` que o BFF Unidade devolve.

- **Rejeitar** é uma operação local de Reservas: retorna `200` e a reserva passa a `REJEITADA`.
- **Aceitar** não muda a reserva em Reservas. Reservas devolve `409 ACEITE_ENCAMINHAR` ao BFF e grava esse destino com a chave idempotente. O BFF então encaminha o pedido ao Orquestrador com a mesma chave. O Orquestrador grava a execução (`EM_EXECUCAO`) e a primeira etapa (`ACEITAR_RESERVA`, `PENDENTE`). Só depois disso o BFF responde `202`, com `Location` apontando para `/api/unidade/v1/painel/reservas/{reservaId}`.
- Repetir a mesma ação com a mesma chave devolve o resultado original. Um segundo aceite da mesma reserva com outra chave, enquanto a confirmação ainda roda, recebe `409 EXECUCAO_CONCORRENTE`. Se o Orquestrador estiver fora do ar, o BFF responde `502`, e a repetição com a mesma chave conclui o aceite.

| Processo | Variável de ambiente | Padrão |
|---|---|---|
| Gateway | `BFF_UNIDADE_URL` | `http://127.0.0.1:8005` |
| BFF Unidade | `RESERVAS_URL` | `http://127.0.0.1:8004` |
| BFF Unidade | `ESTOQUE_URL` | `http://127.0.0.1:8003` |
| BFF Unidade | `ORQUESTRADOR_URL` | `http://127.0.0.1:8006` |

## Confirmação pela SAGA

Depois do aceite, o Orquestrador executa a confirmação em segundo plano, etapa por etapa:

1. Reservas grava `EM_CONFIRMACAO`.
2. Estoque aloca a quantidade.
3. Retiradas prepara a autorização.
4. Reservas grava `CONFIRMADA`, o ponto de compromisso.
5. A execução termina como `CONCLUIDA`.

Antes de cada chamada, a etapa fica gravada no banco do Orquestrador, com o comando e uma chave idempotente própria. Se a resposta se perder (timeout, `5xx` ou participante fora do ar), o Orquestrador repete o mesmo comando com a mesma chave. A espera entre tentativas cresce até 30 segundos. O participante devolve o resultado já gravado, sem repetir o efeito. Se o Orquestrador reiniciar, ele retoma das etapas pendentes.

**Compensação (antes do ponto de compromisso):**
- **Estoque recusa a alocação** (`SALDO_INSUFICIENTE`, por exemplo): Reservas grava `FALHA_CONFIRMACAO`. A execução termina `COMPENSADA`.
- **Retiradas recusa a preparação** (`AUTORIZACAO_NAO_CRIADA`): o Orquestrador libera a alocação em Estoque e depois grava `FALHA_CONFIRMACAO`.
- **Autorização pode ter sido criada:** ela é revogada antes de a alocação ser liberada.

A confirmação usa o quinto PostgreSQL, de Retiradas, e uma credencial de serviço do Orquestrador. Gere mais um token com o mesmo comando usado para os outros. Na primeira execução:

```powershell
docker run -d --name glico-retiradas-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=retiradas -p 127.0.0.1:54335:5432 -v glico-retiradas-data:/var/lib/postgresql/data postgres:17
```

Defina `$env:GLICO_ORQUESTRADOR_SERVICE_TOKEN = '<token do orquestrador>'` com o mesmo valor nos terminais de **Reservas**, **Estoque**, **Retiradas** e **Orquestrador**, e reinicie esses processos. Os comandos internos de cada participante só aceitam essa credencial. Reservas só aceita os cabeçalhos do profissional delegado (`X-Ator-*`) quando eles vêm com ela. Aplique a migração nova em Estoque e Reservas com os mesmos comandos de antes, sem `--demo` em Reservas.

**Retiradas (porta 8007)**

```powershell
$env:GLICO_ORQUESTRADOR_SERVICE_TOKEN = '<token do orquestrador>'
$env:RETIRADAS_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54335/retiradas'
uv run --locked python -m servicos.migracoes retiradas
uv run --locked uvicorn servicos.retiradas.main:app --host 127.0.0.1 --port 8007
```

O Orquestrador encontra os participantes por `RESERVAS_URL` (`:8004`), `ESTOQUE_URL` (`:8003`) e `RETIRADAS_URL` (`:8007`).

**Para demonstrar uma falha com compensação:** inicie Retiradas com `$env:GLICO_FALHA_PREPARAR_AUTORIZACAO = '1'` e aceite uma solicitação. A alocação é feita e depois liberada, e a reserva termina `FALHA_CONFIRMACAO`. Para ver a compensação sem alocar nada, aceite uma solicitação com quantidade maior que o saldo.

Para acompanhar uma execução:

```powershell
docker exec glico-orquestrador-db psql -U glico -d orquestrador -c "SELECT etapa_id, estado_tecnico, tentativas, erro_tecnico FROM saga_etapas ORDER BY criada_em DESC LIMIT 10"
```

A tabela de decisão do executor tem uma verificação sem dependências, rodada com `uv run --locked python -m tests.decisao_saga`.

## Projeção CQRS por eventos

A disponibilidade não é lida do saldo canônico. Ela vem de uma projeção atualizada por eventos:

1. Ao registrar entrada, alocar ou liberar, Estoque altera `saldos` e grava o evento na tabela `outbox`, na mesma transação. Os eventos são `estoque.entrada-registrada.v1`, `estoque.alocacao-criada.v1` e `estoque.alocacao-liberada.v1`.
2. Um publicador, dentro do processo de Estoque, envia os eventos pendentes à exchange `glico.eventos` do RabbitMQ. Ele usa confirmação do broker e marca o evento como `PUBLICADO` só depois dela.
3. O consumidor da projeção lê a fila `estoque.projecao-disponibilidade` e atualiza a tabela `disponibilidade`.

Cada evento traz o estado completo do saldo e a sua `estoqueVersion`. Por isso, o consumidor ignora duplicatas pela `inbox` e não deixa a leitura regredir com eventos atrasados. Mensagens inválidas vão para a fila `estoque.projecao-disponibilidade.erros`.

Com o broker fora do ar, a SAGA continua confirmando, e os eventos esperam na Outbox. Quando o broker volta, a projeção alcança o saldo. Em condições normais, isso leva menos de um segundo; a meta é de 5 s.

Para subir o RabbitMQ manualmente:

```powershell
docker run -d --name glico-rabbitmq -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -v glico-rabbitmq-data:/var/lib/rabbitmq rabbitmq:4-management
```

Estoque usa `RABBITMQ_URL` (padrão `amqp://guest:guest@127.0.0.1:5672/%2F`). Para o painel da unidade, Estoque e BFF Unidade também precisam de `GLICO_PROFISSIONAL_TOKEN` e `GLICO_PROFISSIONAL_UNIDADE_ID`. Estoque consulta `UNIDADES_URL` (padrão `http://127.0.0.1:8002`) para confirmar que a unidade está ativa antes de uma nova entrada.

### Registrar e conferir uma entrada

1. Abra `/unidade`, informe o token do profissional e clique em **Carregar painel**.
2. Em **Estoque da unidade**, selecione um medicamento ou insumo do catálogo, informe a quantidade inteira recebida e clique em **Registrar entrada**.
3. Após a atualização da projeção, confira o estoque físico e o disponível no painel. O cidadão também pode consultar a disponibilidade pelo item no portal.

A primeira entrada de um item cria seu saldo com reservas desativadas quando a unidade ainda não configurou a permissão do item. As próximas somam ao saldo físico e preservam a permissão vigente. No cartão do medicamento, clique em **Habilitar reservas**. Quando a projeção refletir a alteração, o cidadão poderá reservar o mesmo medicamento pelo portal. Se houver perda de resposta, reenvie a mesma quantidade para o mesmo item na mesma aba. O painel reutiliza a chave daquela tentativa, mesmo após recarregar a página.
