# GlicoAcesso

<p align="center">
    <img src="./identidade-visual/logo-sem-fundo.png" alt="Logo do GlicoAcesso" width="320">
</p>

> **Encontre. Reserve. Continue seu cuidado.**

O **GlicoAcesso** é uma startup fictícia de impacto social que busca facilitar o acesso de pessoas com diabetes a medicamentos e insumos disponibilizados pela rede pública de saúde.

**Em uma frase:** conectamos cidadãos e unidades públicas de saúde participantes para tornar mais simples descobrir **onde um item está disponível, quando a informação foi atualizada, quais são as regras de retirada e, quando permitido, solicitar uma reserva antes do deslocamento**.

---


## O problema

Imagine uma pessoa que precisa retirar regularmente um medicamento ou insumo para diabetes pela rede pública. Antes de sair de casa, ela precisa responder a perguntas simples:

- **Qual unidade fornece o item de que preciso?**
- **Há disponibilidade informada? Quando ela foi atualizada?**
- **Qual é o horário de retirada?**
- **Quais documentos ou requisitos são necessários?**
- **Existe outra unidade participante caso aquela não possa atender?**

Quando essas informações estão dispersas ou são difíceis de localizar, o cidadão pode se deslocar até uma unidade e descobrir apenas no local que o item não está disponível ou que a retirada depende de outro procedimento. Isso pode gerar **tempo perdido, gasto com transporte e atraso na retirada**.

O GlicoAcesso não parte da ideia de que todas as pessoas com diabetes deixam de obter seus medicamentos. O problema que buscamos enfrentar é mais específico: **a incerteza sobre onde, quando e como acessar itens disponíveis na rede pública participante**.

### Por que esse problema importa?

- Um estudo nacional com dados da Pesquisa Nacional de Saúde identificou que **69,7% da obtenção de insulina analisada ocorreu pelo serviço público** e encontrou desigualdades de acesso associadas a renda, raça/cor e ausência de plano de saúde.
- O Ministério da Saúde informa que, após a distribuição federal de insulinas e agulhas, as localidades respondem pela distribuição, armazenamento e dispensação, podendo existir particularidades e critérios locais.
- Uma pesquisa nacional em 273 municípios encontrou **disponibilidade média de 52,9% para medicamentos traçadores na atenção primária**, com diferenças regionais. O dado é geral e não específico de diabetes ou insulina.
- A **Lei nº 14.654/2023** exige que os estoques das farmácias públicas do SUS sejam divulgados na internet, atualizados quinzenalmente e apresentados de forma acessível ao cidadão.

Esses dados não significam que uma plataforma digital possa resolver todas as desigualdades de acesso ou o desabastecimento. Eles ajudam a mostrar por que **organizar e tornar utilizáveis as informações de disponibilidade e retirada pode ser relevante**.

---


## A solução

O GlicoAcesso reúne, em um único ambiente, informações das **unidades públicas de saúde participantes** e cria um fluxo entre quem precisa encontrar um item e quem gerencia sua disponibilização.

```mermaid
flowchart LR
    A[👤 Cidadão] -->|Pesquisa medicamento ou insumo| B[🔎 GlicoAcesso]
    B -->|Consulta disponibilidade, horário e requisitos| C[🏥 Unidade participante]
    C -->|Atualiza informações e responde solicitações| B
    B -->|Exibe opções e status| A
    A -->|Solicita reserva, quando permitida| B
    B -->|Encaminha solicitação| C
    C -->|Confirma, rejeita ou registra retirada| B
```

### Para o cidadão

1. Pesquisa o medicamento ou insumo prescrito.
2. Visualiza unidades participantes que informam disponibilidade do item.
3. Consulta **data de atualização, endereço, horário e requisitos para retirada**.
4. Quando permitido, solicita uma reserva antes de se deslocar.
5. Acompanha a confirmação e a situação da retirada.
6. Caso uma unidade não possa atender, consulta outras opções participantes.

### Para a unidade de saúde

1. Mantém as informações de disponibilidade, horários e requisitos atualizadas.
2. Visualiza solicitações recebidas.
3. Confirma ou rejeita reservas conforme a disponibilidade.
4. Registra a retirada dos itens.
5. Acompanha demanda e indisponibilidades.

### De onde vêm os dados?

Nesta fase acadêmica, os dados são **simulados** e poderão ser atualizados pelas próprias unidades no sistema.

Em uma implantação real, a plataforma poderia combinar diferentes formas de atualização conforme a infraestrutura da rede de saúde: atualização manual por profissionais autorizados, importação periódica de dados e integração com sistemas de estoque já existentes quando houver mecanismos de interoperabilidade disponíveis.

Em todos os casos, o GlicoAcesso deve mostrar de forma clara **quando a informação foi atualizada**, evitando apresentar um dado antigo como se fosse uma confirmação em tempo real.

> O GlicoAcesso não precisa começar com todas as unidades do país. A proposta pode ser adotada inicialmente por uma **rede municipal ou conjunto de unidades participantes**, expandindo à medida que novas unidades aderirem.

---


## Impacto social esperado

O objetivo do GlicoAcesso não é criar estoque onde ele não existe, mas **reduzir a incerteza e o custo de encontrar e retirar um item disponível na rede participante**.

Os beneficiários incluem pessoas com diabetes que dependem do SUS, familiares e cuidadores, profissionais das unidades e gestores municipais de saúde. O impacto pode ser especialmente relevante para pessoas com menor renda, mobilidade reduzida ou que vivem longe das unidades de dispensação, para quem um deslocamento sem sucesso pode representar um custo maior.

### Como vamos saber se a ideia funciona?

| Objetivo | Indicador proposto |
| --- | --- |
| Tornar a busca mais rápida | **Tempo para localizar uma unidade apta** |
| Reduzir viagens sem resultado | **Taxa de deslocamentos sem sucesso** |
| Dar previsibilidade à solicitação | **Taxa de reservas confirmadas** |
| Acompanhar o acesso até a retirada | **Tempo entre solicitação e retirada** |
| Melhorar a experiência | **Satisfação do usuário** |
| Apoiar a organização das unidades | **Solicitações atendidas, rejeitadas ou expiradas** |

Esses indicadores medem resultados diretamente relacionados ao que a plataforma se propõe a melhorar. O projeto **não atribui diretamente ao GlicoAcesso a redução de amputações, internações ou mortes**, pois esses resultados dependem de diversos fatores clínicos, sociais e estruturais.

---


## O que o GlicoAcesso é - e o que não é

| O GlicoAcesso **faz** | O GlicoAcesso **não faz** |
| --- | --- |
| Facilita a localização de unidades participantes | Não realiza diagnóstico |
| Organiza informações de disponibilidade e retirada | Não recomenda doses ou altera prescrições |
| Mostra quando a informação foi atualizada | Não cria medicamentos ou resolve desabastecimento |
| Permite solicitar reserva quando a unidade oferecer esse fluxo | Não garante disponibilidade nacional |
| Apoia unidades na gestão das solicitações e retiradas | Não substitui profissionais ou sistemas públicos de saúde |

A proposta é atuar como uma **ponte entre a informação existente na rede participante e o cidadão que precisa utilizá-la**.

> **GlicoAcesso: encontre, reserve e continue seu cuidado.**

---

## Integrantes

- Marcos Vinícius Pereira
- Arthur Soares Marques
- Lana da Silva Miranda
- Guilherme Lirio Miranda

## Documentação

- [Parte 1 — Concepção e pitch](./docs/parte-1-concepcao-e-pitch.md)
- [Parte 2 — Resumo e índice da arquitetura](./docs/parte-2/resumo-arquitetura.md)
- [Decisões compartilhadas](./docs/parte-2/00-decisoes-compartilhadas.md) e [diagrama de arquitetura](./docs/parte-2/02-diagrama-arquitetura.md)
- [Contratos OpenAPI](./docs/parte-2/api/) e [diagramas de sequência](./docs/parte-2/diagramas/)

## Estado do projeto e consulta local

O repositório contém a concepção do projeto e a especificação da arquitetura da Parte 2. A arquitetura documenta quatro serviços de domínio e um Orquestrador da SAGA independente, com PostgreSQL próprio para cada serviço. O portal do cidadão consulta unidades e itens através do Gateway e do BFF Cidadão. Unidades e Estoque usam bancos independentes com dados de demonstração.

Para consultar a documentação localmente, clone o repositório e abra os arquivos Markdown:

```bash
git clone https://github.com/ArthurDp78/GlicoAcesso.git
cd GlicoAcesso
```

## Desenvolvimento local

### Rodar tudo com um comando (Windows)

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

A base executável da Parte 3 contém dois processos HTTP independentes: API Gateway e BFF Cidadão. Use [uv](https://docs.astral.sh/uv/getting-started/installation/) na raiz do repositório. O `uv` seleciona o Python 3.14 indicado em `.python-version` e instala as versões registradas em `uv.lock`.

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

### Unidades e Estoque

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

### Portal do cidadão

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

### Criar e consultar reservas

Crie um terceiro PostgreSQL independente para Reservas na primeira execução.

```powershell
docker run -d --name glico-reservas-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=reservas -p 127.0.0.1:54333:5432 -v glico-reservas-data:/var/lib/postgresql/data postgres:17
```

Nas próximas execuções, use `docker start glico-reservas-db`. Gere dois tokens de demonstração distintos com o comando abaixo, executando-o duas vezes.

```powershell
uv run --locked python -c "import secrets; print(secrets.token_urlsafe(32))"
```

O navegador usa o token do cidadão (`GLICO_CIDADAO_TOKEN`), validado pelo BFF Cidadão. O BFF chama os serviços com a própria credencial e delega a identidade do usuário. Antes de iniciar cada processo, defina as credenciais da tabela em [Credenciais por processo](#credenciais-por-processo). As consultas públicas continuam acessíveis sem token. Use essas credenciais apenas na demonstração local.

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

### Profissional da unidade

O profissional de demonstração usa um token próprio e fica vinculado a uma unidade. O vínculo é um atributo da identidade, como o papel, e não fica gravado nos bancos de domínio. Antes de iniciar o BFF Unidade, defina:

```powershell
$env:GLICO_PROFISSIONAL_TOKEN = '<token do profissional>'
$env:GLICO_PROFISSIONAL_UNIDADE_ID = '10000000-0000-4000-8000-000000000001'
```

No aceite, Reservas confere em Unidades se a unidade vinculada está ativa; se não estiver, responde `403`. Consultar, rejeitar, cancelar e entregar continuam possíveis. Tokens repetidos entre identidades impedem a inicialização. Para listar as solicitações pendentes da unidade:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/unidade/v1/painel/reservas' -Headers @{ Authorization = 'Bearer <token do profissional>' }
```

A consulta `GET /internal/v1/reservas/{reservaId}` aceita o cidadão dono da reserva ou um profissional da mesma unidade. Um profissional de outra unidade recebe `403`. Um cidadão que não é o dono recebe `404`. Os serviços aceitam somente a identidade delegada pelos BFFs.

### Painel da unidade e aceite

O aceite é recebido pelo Orquestrador da SAGA, que tem o próprio PostgreSQL (o quarto banco). Na primeira execução:

```powershell
docker run -d --name glico-orquestrador-db -e POSTGRES_USER=glico -e POSTGRES_PASSWORD=glico-demo -e POSTGRES_DB=orquestrador -p 127.0.0.1:54334:5432 -v glico-orquestrador-data:/var/lib/postgresql/data postgres:17
```

Nas próximas execuções, use `docker start glico-orquestrador-db`. Inicie mais dois processos, com as credenciais da tabela em [Credenciais por processo](#credenciais-por-processo):

**Orquestrador (porta 8006)**

```powershell
$env:GLICO_CIDADAO_TOKEN = '<token do cidadão>'
$env:GLICO_PROFISSIONAL_TOKEN = '<token do profissional>'
$env:GLICO_PROFISSIONAL_UNIDADE_ID = '10000000-0000-4000-8000-000000000001'
$env:ORQUESTRADOR_DATABASE_URL = 'postgresql://glico:glico-demo@127.0.0.1:54334/orquestrador'
uv run --locked python -m servicos.migracoes orquestrador
uv run --locked uvicorn servicos.orquestrador.main:app --host 127.0.0.1 --port 8006
```

**BFF Unidade (porta 8005)**

```powershell
uv run --locked uvicorn servicos.bff_unidade.main:app --host 127.0.0.1 --port 8005
```

Abra [http://127.0.0.1:8000/unidade](http://127.0.0.1:8000/unidade), informe o token do profissional e clique em **Carregar solicitações**. Cada solicitação pendente mostra **Aceitar** e **Rejeitar**. Os botões vêm dos links `_links` que o BFF Unidade devolve.

- **Rejeitar** é uma operação local de Reservas: retorna `200` e a reserva passa a `REJEITADA`.
- **Aceitar** não muda a reserva em Reservas. Reservas devolve `409 ACEITE_ENCAMINHAR` ao BFF e grava esse destino com a chave idempotente. O BFF então encaminha o pedido ao Orquestrador com a mesma chave. O Orquestrador grava a execução (`EM_EXECUCAO`) e a primeira etapa (`ACEITAR_RESERVA`, `PENDENTE`). Só depois disso o BFF responde `202`, com `Location` apontando para `/api/unidade/v1/painel/reservas/{reservaId}`.
- Repetir a mesma ação com a mesma chave devolve o resultado original. Um segundo aceite da mesma reserva com outra chave, enquanto a confirmação ainda roda, recebe `409 EXECUCAO_CONCORRENTE`. Se o Orquestrador estiver fora do ar, o BFF responde `503`, e a repetição com a mesma chave conclui o aceite.

| Processo | Variável de ambiente | Padrão |
|---|---|---|
| Gateway | `BFF_UNIDADE_URL` | `http://127.0.0.1:8005` |
| BFF Unidade | `RESERVAS_URL` | `http://127.0.0.1:8004` |
| BFF Unidade | `ESTOQUE_URL` | `http://127.0.0.1:8003` |
| BFF Unidade | `ORQUESTRADOR_URL` | `http://127.0.0.1:8006` |

### Confirmação pela SAGA

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

### Projeção CQRS por eventos

A disponibilidade não é lida do saldo canônico. Ela vem de uma projeção atualizada por eventos:

1. Ao alocar ou liberar, Estoque altera `saldos` e grava o evento na tabela `outbox`, na mesma transação. Os eventos são `estoque.alocacao-criada.v1` e `estoque.alocacao-liberada.v1`.
2. Um publicador, dentro do processo de Estoque, envia os eventos pendentes à exchange `glico.eventos` do RabbitMQ. Ele usa confirmação do broker e marca o evento como `PUBLICADO` só depois dela.
3. O consumidor da projeção lê a fila `estoque.projecao-disponibilidade` e atualiza a tabela `disponibilidade`.

Cada evento traz o estado completo do saldo e a sua `estoqueVersion`. Por isso, o consumidor ignora duplicatas pela `inbox` e não deixa a leitura regredir com eventos atrasados. Mensagens inválidas vão para a fila `estoque.projecao-disponibilidade.erros`.

Com o broker fora do ar, a SAGA continua confirmando, e os eventos esperam na Outbox. Quando o broker volta, a projeção alcança o saldo. Em condições normais, isso leva menos de um segundo; a meta é de 5 s.

Para subir o RabbitMQ manualmente:

```powershell
docker run -d --name glico-rabbitmq -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 -v glico-rabbitmq-data:/var/lib/rabbitmq rabbitmq:4-management
```

Estoque usa `RABBITMQ_URL` (padrão `amqp://guest:guest@127.0.0.1:5672/%2F`). Para o painel de estoque da unidade, o BFF Unidade também precisa de `GLICO_PROFISSIONAL_TOKEN` e `GLICO_PROFISSIONAL_UNIDADE_ID`. O painel, em `/api/unidade/v1/painel/estoque`, mostra o estoque físico, o alocado, o disponível e o instante da projeção (`atualizadoEm`). O painel `/unidade` exibe esses dados abaixo das solicitações.

### Credenciais por processo

Cada token tem no mínimo 32 caracteres e deve ser diferente dos demais. Um processo não inicia se faltar uma credencial sua ou se houver tokens repetidos entre os que ele conhece. A verificação alcança só as variáveis presentes no próprio processo.

| Processo | Credenciais |
|---|---|
| BFF Cidadão | `GLICO_CIDADAO_TOKEN`, `GLICO_BFF_CIDADAO_TOKEN` |
| BFF Unidade | `GLICO_PROFISSIONAL_TOKEN`, `GLICO_PROFISSIONAL_UNIDADE_ID`, `GLICO_BFF_UNIDADE_TOKEN` |
| Unidades | `GLICO_RESERVAS_SERVICE_TOKEN`, `GLICO_BFF_CIDADAO_TOKEN`, `GLICO_BFF_UNIDADE_TOKEN`, `GLICO_ADMIN_SERVICE_TOKEN` |
| Estoque | `GLICO_RESERVAS_SERVICE_TOKEN`, `GLICO_ORQUESTRADOR_SERVICE_TOKEN`, `GLICO_BFF_UNIDADE_TOKEN`, `GLICO_ADMIN_SERVICE_TOKEN` |
| Reservas | `GLICO_RESERVAS_SERVICE_TOKEN`, `GLICO_ORQUESTRADOR_SERVICE_TOKEN`, `GLICO_RETIRADAS_SERVICE_TOKEN`, `GLICO_BFF_CIDADAO_TOKEN`, `GLICO_BFF_UNIDADE_TOKEN` |
| Retiradas | `GLICO_RETIRADAS_SERVICE_TOKEN`, `GLICO_ORQUESTRADOR_SERVICE_TOKEN`, `GLICO_BFF_UNIDADE_TOKEN` |
| Orquestrador | `GLICO_ORQUESTRADOR_SERVICE_TOKEN`, `GLICO_BFF_CIDADAO_TOKEN`, `GLICO_BFF_UNIDADE_TOKEN` |

Na futura configuração do Docker Compose, cada contêiner deve receber apenas as próprias credenciais, distintas e protegidas fora do Git. Veja o [documento 03](./docs/parte-2/03-api-gateway.md).

### Administração, cancelamento e retirada

Além das variáveis das seções anteriores, configure:

| Processo | Variável | Uso |
|---|---|---|
| Reservas e Retiradas | `GLICO_RETIRADAS_SERVICE_TOKEN` | Retiradas consulta o estado canônico em Reservas antes da entrega. |
| Unidades e Estoque | `GLICO_ADMIN_SERVICE_TOKEN` | Cadastro de unidades e do catálogo, operações internas sem vínculo com uma unidade. |
| Reservas, Retiradas e Orquestrador | `RABBITMQ_URL` | Publicar e consumir `retirada.concluida.v1`. |
| Retiradas | `RESERVAS_URL` | Padrão `http://127.0.0.1:8004`. |
| Reservas | `GLICO_EXPIRACAO_INTERVALO` | Intervalo da expiração em segundos, padrão `5`. |

Reaplique as migrações dos cinco serviços. Uma retirada que não corresponda à alocação não recebe baixa: ela é registrada em `ocorrencias_retirada` e o evento fica em `estoque.baixa-retirada.erros`. Corrigida a causa, devolva os eventos à fila (a Inbox continua deduplicando):

```bash
uv run --locked python -m servicos.reprocessar estoque.baixa-retirada
```

Para reconstruir a projeção de disponibilidade a partir dos saldos, com Estoque em execução ou não:

```bash
uv run --locked python -m servicos.estoque.projecao
```

Os testes de integração usam um PostgreSQL e um RabbitMQ **descartáveis**. Eles apagam os bancos `teste_*` e esvaziam as filas do broker indicado, então não aponte para o ambiente de demonstração.

```bash
export GLICO_TESTE_PG='postgresql://postgres:teste@127.0.0.1:55432/postgres'
export GLICO_TESTE_RABBIT='amqp://guest:guest@127.0.0.1:55672/%2F'
uv run --locked python -m unittest tests.test_unidades tests.test_estoque tests.test_reservas tests.test_retiradas tests.test_saga tests.test_revisao tests.test_decisoes tests.test_borda
```

Para validar também status, corpos e cabeçalhos contra os OpenAPI, execute os testes com `GLICO_TESTE_TROCAS=/tmp/trocas.jsonl` e depois:

```bash
uv run --no-project --with pyyaml --with jsonschema python -m tests.contratos /tmp/trocas.jsonl
```

## Referências

1. [International Diabetes Federation - Dados sobre diabetes no Brasil](https://diabetesatlas.org/es/data-by-location/country/brazil/).
2. [Leal et al. - Acesso a medicamentos para hipertensão e diabetes](https://doi.org/10.1590/0102-311XPT241022).
3. [Nascimento et al. - Disponibilidade de medicamentos essenciais](https://doi.org/10.11606/S1518-8787.2017051007062).
4. [Ministério da Saúde - Insulinas humanas e agulhas para caneta](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas).
5. [Brasil - Lei nº 14.654/2023](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14654.htm).
6. [PNAUM - Acesso e adesão a medicamentos entre pessoas com diabetes no Brasil](https://doi.org/10.1590/1980-549720180003).
