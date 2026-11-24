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

Antes de iniciar **Unidades**, **Estoque** e **Reservas**, defina `$env:GLICO_RESERVAS_SERVICE_TOKEN` com o mesmo token interno nos três terminais. O navegador usa o outro token, definido como `GLICO_CIDADAO_TOKEN` somente no processo de Reservas. O Gateway e o BFF encaminham a credencial do cidadão para Reservas, que verifica a identidade e a propriedade da solicitação. As consultas públicas continuam acessíveis sem token. Use essas credenciais apenas na demonstração local.

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

## Referências

1. [International Diabetes Federation - Dados sobre diabetes no Brasil](https://diabetesatlas.org/es/data-by-location/country/brazil/).
2. [Leal et al. - Acesso a medicamentos para hipertensão e diabetes](https://doi.org/10.1590/0102-311XPT241022).
3. [Nascimento et al. - Disponibilidade de medicamentos essenciais](https://doi.org/10.11606/S1518-8787.2017051007062).
4. [Ministério da Saúde - Insulinas humanas e agulhas para caneta](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas).
5. [Brasil - Lei nº 14.654/2023](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14654.htm).
6. [PNAUM - Acesso e adesão a medicamentos entre pessoas com diabetes no Brasil](https://doi.org/10.1590/1980-549720180003).
