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

## Versão de entrega e execução local

A versão executável da Parte 3 está na [branch `feat/fase-3`](https://github.com/ArthurDp78/GlicoAcesso/tree/feat/fase-3). O Compose reúne oito aplicações (Gateway, dois BFFs, Orquestrador, Unidades, Estoque, Reservas e Retiradas), cinco instâncias PostgreSQL e RabbitMQ.

O cidadão consulta a disponibilidade, solicita e acompanha reservas. O profissional registra entradas de estoque, configura a permissão de reserva e aceita ou rejeita solicitações. A API profissional também oferece manutenção do cadastro da unidade e ajustes de saldo. A SAGA de confirmação prepara a autorização de retirada e o CQRS atualiza a disponibilidade. O cadastro de unidades é feito pela CLI administrativa. O profissional consulta uma reserva pelo código e registra a entrega no balcão. A entrega e seu evento são gravados juntos em Retiradas. O RabbitMQ distribui o evento para Reservas, Estoque e Orquestrador. A reserva passa a `RETIRADA`, o estoque baixa o físico e encerra a alocação, e o Orquestrador guarda a evidência para reconciliação. O cidadão cancela a própria reserva. O profissional pode cancelar com justificativa. Solicitações vencidas saem da fila de decisão e ficam como `EXPIRADA`. Se a confirmação já estiver ativa, o cancelamento é registrado e aguarda sua conclusão ou compensação.

Clone a branch de entrega e entre na pasta antes de executar os comandos de desenvolvimento local.

```bash
git clone --branch feat/fase-3 --single-branch https://github.com/ArthurDp78/GlicoAcesso.git
cd GlicoAcesso
```

## Desenvolvimento local

### Subir o sistema completo com Docker Compose

Com o Docker Desktop aberto e em modo de contêineres Linux, execute o bloco a seguir na raiz do repositório. Na primeira execução ele gera um `.env` a partir de `.env.example`, com valores aleatórios distintos. Se já existir um `.env`, preserve o arquivo e complete os campos faltantes com base no exemplo.

```powershell
if (-not (Test-Path -LiteralPath .env)) {
  $gerador = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $linhas = foreach ($linha in Get-Content -LiteralPath .env.example) {
      if ($linha -match '^[A-Z0-9_]+=$') {
        $bytes = New-Object byte[] 32
        $gerador.GetBytes($bytes)
        $linha + [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
      } else {
        $linha
      }
    }
    [IO.File]::WriteAllLines((Join-Path (Get-Location).Path '.env'),
      [string[]]$linhas, [Text.UTF8Encoding]::new($false))
  } finally {
    $gerador.Dispose()
  }
}
docker compose up --build -d --wait
```

A mesma subida pode ser feita em primeiro plano com `docker compose up --build`. O Compose aguarda os bancos, roda as migrações antes de iniciar as APIs e verifica a saúde de cada serviço. A carga de demonstração é aplicada em Unidades e Estoque por padrão. Use `GLICO_CARREGAR_DEMO=0` no `.env` para iniciar uma base nova apenas com as migrações e o catálogo oficial.

- **Portal do cidadão** em [http://127.0.0.1:8000/cidadao](http://127.0.0.1:8000/cidadao), com `GLICO_CIDADAO_TOKEN` para reservar.
- **Painel da unidade** em [http://127.0.0.1:8000/unidade](http://127.0.0.1:8000/unidade), com `GLICO_PROFISSIONAL_TOKEN`.
- **Diagnóstico** com `docker compose ps` e `docker compose logs <serviço>`. Se a porta 8000 estiver ocupada, ajuste `GLICO_GATEWAY_PORTA` no `.env`.

Para registrar uma entrega, informe o código da reserva no painel profissional, em **Retirada no balcão**. A ação aparece quando a reserva está confirmada e a autorização está ativa. Em instalações existentes, preencha `GLICO_RETIRADAS_SERVICE_TOKEN` no `.env` com um valor aleatório exclusivo de pelo menos 32 caracteres. Na execução manual, configure o mesmo valor em Reservas e Retiradas e disponibilize as credenciais de demonstração do profissional para Retiradas.

O cancelamento distribuído pelo cidadão usa `GLICO_BFF_CIDADAO_SIGNING_KEY`. Em um `.env` existente, acrescente um valor aleatório exclusivo de pelo menos 32 caracteres. Na execução manual, configure a mesma chave no BFF Cidadão e no Orquestrador e defina o token do cidadão também no BFF Cidadão.

Somente o Gateway publica uma porta em `127.0.0.1`. Cada PostgreSQL tem uma rede privada com seu serviço e um volume próprio. Estoque, Retiradas, Reservas e Orquestrador acessam o RabbitMQ pela rede de mensageria. Unidades também participa da rede administrativa usada pela CLI.

`docker compose down` encerra os contêineres e preserva os volumes nomeados. Mantenha o mesmo `.env` entre execuções para reutilizar as credenciais dos bancos e do RabbitMQ.

### Validar a instalação do zero

Em um clone da versão a ser entregue, abra o Docker Desktop e execute na raiz do projeto:

```powershell
.\scripts\validar-compose.ps1
```

O script cria um projeto Compose temporário, com credenciais e volumes próprios. Ele verifica a saúde dos 14 serviços, a abertura dos portais e o funcionamento das APIs via Gateway. Cadastra uma unidade pela CLI. Na unidade de demonstração, registra a entrada de quatro unidades de um medicamento, habilita a reserva, confirma uma solicitação de duas unidades do mesmo medicamento pela SAGA e verifica a projeção CQRS. Também registra a entrega no balcão e aguarda `RETIRADA` e a projeção de duas unidades físicas, zero alocadas e duas disponíveis. Depois recria os contêineres com os mesmos volumes e confirma que os dados e as respostas idempotentes foram preservados.

O resultado esperado é a mensagem **Validação concluída**. Em caso de erro, o script informa a etapa e mostra o estado e os últimos logs dos serviços. Use `-Porta 18081` se a porta local 18080 já estiver em uso. Ao final, o script limpa os contêineres e volumes do projeto temporário.

### Cadastrar uma unidade pelo comando administrativo

Prepare um arquivo `unidade.json` com os campos abaixo. O serviço Unidades gera o identificador e cria a unidade ativa.

```json
{
  "nome": "Unidade de Saúde Central",
  "logradouro": "Rua Exemplo",
  "numero": "200",
  "bairro": "Centro",
  "cidade": "Cidade Exemplo",
  "estado": "MG",
  "cep": "30000-000",
  "orientacoesRetirada": "Apresente o código da reserva no balcão.",
  "contatos": [],
  "horarios": [{"diaSemana": 1, "horarioInicial": "08:00", "horarioFinal": "17:00"}],
  "prazoAnaliseHoras": 24
}
```

Depois de subir o Compose principal, execute o comando pelo `compose.admin.yml`. Ele acessa `unidades:8002` pela rede `GLICO_REDE_ADMINISTRATIVA` e usa a mesma `GLICO_GESTOR_REDE_TOKEN` do `.env`.

```powershell
$arquivo = (Resolve-Path .\unidade.json).Path
$chave = [guid]::NewGuid().ToString()
docker compose -f compose.admin.yml --profile admin run --build --rm `
  --volume "${arquivo}:/dados/unidade.json:ro" cadastro-unidades `
  --arquivo /dados/unidade.json --chave $chave
```

O comando imprime o ID da unidade em caso de sucesso. Em caso de timeout, use o mesmo arquivo e o mesmo valor de `$chave` na próxima tentativa para recuperar a resposta sem repetir o cadastro.

Com Unidades em execução diretamente no Windows, aplique `uv run --locked python -m servicos.migracoes unidades` e configure a mesma credencial no processo de Unidades e no terminal do comando. Nesse ambiente, use `uv run --locked python -m servicos.unidades.cli --arquivo .\unidade.json --chave $chave`. Para outra porta ou endereço local, defina `UNIDADES_URL`. Confira a unidade ativa em `GET /api/cidadao/v1/unidades` pelo Gateway. Ela aparece na busca do portal quando houver disponibilidade projetada para o item consultado.

### Construir as imagens da aplicação

Cada um dos oito serviços tem um Dockerfile em `servicos/<serviço>/Dockerfile`. Use a raiz do repositório como contexto para que o build tenha acesso ao `uv.lock` e aos módulos compartilhados. No PowerShell, com o Docker Desktop em modo de contêineres Linux:

```powershell
foreach ($servico in 'gateway', 'bff_cidadao', 'unidades', 'estoque', 'reservas', 'bff_unidade', 'orquestrador', 'retiradas') {
  docker build --file "servicos/$servico/Dockerfile" --tag "glicoacesso/${servico}:local" .
  if ($LASTEXITCODE -ne 0) { throw "Falha no build de $servico." }
}
```

As imagens usam **build em múltiplos estágios**. O primeiro estágio instala as dependências do `uv.lock` em uma `.venv`. A imagem final usa a mesma base Python slim e leva o ambiente instalado, os módulos compartilhados e os arquivos do serviço. Com isso, o `uv` e o cache de instalação ficam fora da imagem final. Alterações no código do serviço reaproveitam a camada de dependências. Cada processo é executado com usuário sem privilégios de root.

O Gateway leva os arquivos dos dois portais e a logo. As imagens dos serviços com banco levam suas migrações para que a inicialização possa executá-las com `python -m servicos.migracoes <serviço>`. A aplicação das migrações e a configuração de URLs, bancos, RabbitMQ e credenciais fazem parte da subida do sistema.

Para uma checagem isolada da imagem de entrada, suba o Gateway e consulte `http://127.0.0.1:8000/health` em outro terminal:

```powershell
docker run --rm -p 127.0.0.1:8000:8000 glicoacesso/gateway:local
```

### Demonstração com serviços Python no Windows

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

### Profissional da unidade

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

### Painel da unidade e aceite

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

#### Registrar e conferir uma entrada

1. Abra `/unidade`, informe o token do profissional e clique em **Carregar painel**.
2. Em **Estoque da unidade**, selecione um medicamento ou insumo do catálogo, informe a quantidade inteira recebida e clique em **Registrar entrada**.
3. Após a atualização da projeção, confira o estoque físico e o disponível no painel. O cidadão também pode consultar a disponibilidade pelo item no portal.

A primeira entrada de um item cria seu saldo com reservas desativadas quando a unidade ainda não configurou a permissão do item. As próximas somam ao saldo físico e preservam a permissão vigente. No cartão do medicamento, clique em **Habilitar reservas**. Quando a projeção refletir a alteração, o cidadão poderá reservar o mesmo medicamento pelo portal. Se houver perda de resposta, reenvie a mesma quantidade para o mesmo item na mesma aba. O painel reutiliza a chave daquela tentativa, mesmo após recarregar a página.

## Referências

1. [International Diabetes Federation - Dados sobre diabetes no Brasil](https://diabetesatlas.org/es/data-by-location/country/brazil/).
2. [Leal et al. - Acesso a medicamentos para hipertensão e diabetes](https://doi.org/10.1590/0102-311XPT241022).
3. [Nascimento et al. - Disponibilidade de medicamentos essenciais](https://doi.org/10.11606/S1518-8787.2017051007062).
4. [Ministério da Saúde - Insulinas humanas e agulhas para caneta](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas).
5. [Brasil - Lei nº 14.654/2023](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14654.htm).
6. [Meiners et al. — Acesso e adesão a medicamentos entre pessoas com diabetes no Brasil: evidências da PNAUM](https://doi.org/10.1590/1980-5497201700030008). *Revista Brasileira de Epidemiologia*, 2017.
