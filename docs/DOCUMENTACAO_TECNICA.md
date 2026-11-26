# GlicoAcesso — Documentação Técnica

![Logotipo do GlicoAcesso](../identidade-visual/logo-sem-fundo.png)

## Sumário

- [Visão geral do projeto](#visão-geral-do-projeto)
- [Etapa 1 — Concepção e fundamentação](#etapa-1--concepção-e-fundamentação)
- [Etapa 2 — Arquitetura e projeto do sistema](#etapa-2--arquitetura-e-projeto-do-sistema)
  - [Arquitetura no congelamento](#arquitetura-no-congelamento)
  - [Gateway, BFFs, REST e HATEOAS](#gateway-bffs-rest-e-hateoas)
  - [Persistência, Outbox e CQRS](#persistência-outbox-e-cqrs)
  - [SAGA e compensações](#saga-e-compensações)
- [Etapa 3 — Infraestrutura e implantação](#etapa-3--infraestrutura-e-implantação)
  - [Executar do zero](#executar-do-zero)
- [Etapa 4 — Integração final e inteligência artificial](#etapa-4--integração-final-e-inteligência-artificial)
  - [Fluxos implementados](#fluxos-implementados)
  - [Inteligência artificial e avaliação](#inteligência-artificial-e-avaliação)
- [Visão consolidada do sistema](#visão-consolidada-do-sistema)
  - [Arquitetura e dados atuais](#arquitetura-e-dados-atuais)
  - [Catálogo de APIs](#catálogo-de-apis)
  - [Segurança e operação](#segurança-e-operação)
  - [Testes e evidências](#testes-e-evidências)
- [Matriz de atendimento aos requisitos](#matriz-de-atendimento-aos-requisitos)
- [Histórico de evolução e contribuições](#histórico-de-evolução-e-contribuições)
- [Pendências e limitações](#pendências-e-limitações)
- [Referências](#referências)

## Visão geral do projeto

O GlicoAcesso é uma startup fictícia desenvolvida na disciplina de Sistemas Distribuídos. Sua proposta é facilitar a localização, a reserva e a retirada de medicamentos e insumos para diabetes em unidades participantes. O cidadão consulta onde o item consta como disponível e acompanha a solicitação. A unidade mantém seus dados operacionais, gerencia saldo e reservas e registra a entrega presencial. Um gestor de rede cadastra unidades pela interface administrativa de linha de comando.

O público inclui pessoas com diabetes, familiares, cuidadores, profissionais de dispensação e gestores da rede participante. O escopo inicial é uma rede local, com dados de demonstração no protótipo. O trabalho corresponde a 70% da nota da disciplina. A equipe é formada por **Arthur Soares Marques, Guilherme Lirio Miranda, Lana da Silva Miranda e Marcos Vinícius Pereira**. [README do projeto](../README.md)

**Estado em 25/11/2026.** A `main` analisada, em `9d18a62`, contém oito aplicações HTTP, dois portais web, cinco PostgreSQL independentes no Compose, RabbitMQ, processamento de confirmação e cancelamento, registro de retirada e projeção de disponibilidade. A etapa final estava aberta. IA e avaliação associada permaneciam pendentes. O código e a configuração fundamentam os estados de implementação, e a [seção de testes](#testes-e-evidências) identifica o alcance da verificação. [Revisão analisada](https://github.com/ArthurDp78/GlicoAcesso/commit/9d18a62ca1c07bf495f283df3b8e4600cc6c0a6c)

| Marco | Data da disciplina, horário de Brasília | Evidência disponível |
| --- | --- | --- |
| 1 · Proposta | 17/09/2026 | README, pitch, fundamentação e identidade visual no [snapshot de 17/09](https://github.com/ArthurDp78/GlicoAcesso/tree/422b9ce). |
| 2 · Arquitetura | Congelamento em 21/10 às 23h59. Apresentações em 22 e 27/10. | [Projeto congelado](https://github.com/ArthurDp78/GlicoAcesso/tree/b059d68). [Dois reparos Mermaid em 22/10](https://github.com/ArthurDp78/GlicoAcesso/compare/b059d68...1ca8bef). |
| 3 · Infraestrutura | 17/11/2026 | A última revisão de `main` até a data era [`1ca8bef`](https://github.com/ArthurDp78/GlicoAcesso/tree/1ca8bef). O executável e o Compose entraram nos dias 24 e 25/11. |
| 4 · Integração e IA | Congelamento em 09/12 às 23h59. Apresentações em 10 e 15/12. | [Snapshot de 25/11](https://github.com/ArthurDp78/GlicoAcesso/tree/9d18a62), anterior ao congelamento. |

A reconstrução usa a primeira linha de ancestralidade de `main` para os cortes de entrega e as referências locais e remotas disponíveis para as contribuições. Esses cortes identificam o conteúdo versionado naquela data. Registros de apresentação, avaliações e materiais fora do repositório dependem de evidência própria.

## Etapa 1 — Concepção e fundamentação

### Problema, identidade e proposta de valor

A primeira etapa registrou a marca GlicoAcesso, o logotipo em duas versões e a frase de apresentação “Encontre, reserve e continue seu cuidado”. O pitch apresenta uma pessoa que precisa retirar um item já prescrito e que, antes de sair de casa, precisa localizar uma unidade, confirmar horário e entender como funciona a retirada. Idosos, pessoas de baixa renda, moradores distantes das unidades, familiares e cuidadores são públicos particularmente expostos ao custo de viagens repetidas. [Pitch no corte de setembro](https://github.com/ArthurDp78/GlicoAcesso/blob/422b9ce/docs/parte-1-concepcao-e-pitch.md) · [Identidade visual original](../identidade-visual/logo.png)

A proposta reuniu em uma busca o item, a unidade, o endereço, o horário, as instruções e o momento da última atualização. Quando a unidade habilitasse reservas, o cidadão poderia solicitar pelo portal, aguardar a decisão e usar o código na retirada. A unidade cuidaria de cadastro, disponibilidade, decisão e registro da entrega. A origem proposta era a atualização pelas unidades, com integração a controles de estoque locais como possibilidade futura. Dados simulados seriam usados no desenvolvimento inicial.

O recorte é operacional, em torno do acesso a itens já prescritos. Uma unidade participante continua responsável pelos requisitos de dispensação. Disponibilidade informada e uma reserva confirmada são estados distintos, sujeitos às regras locais e à atualização dos dados.

### Fundamentação do problema

| Fonte | Evidência usada no projeto | Alcance |
| --- | --- | --- |
| International Diabetes Federation, *Diabetes Atlas* | Estimativa de **16,6 milhões** de pessoas de 20 a 79 anos com diabetes no Brasil em 2024. | Dimensiona o público potencial. [IDF](https://idf.org/our-network/regions-and-members/south-and-central-america/members/brazil/) |
| Leal, Galvão e Roncalli (2024), análise da PNS 2019 | O serviço público respondeu por **69,7%** da obtenção de insulina observada no estudo, com desigualdades associadas a fatores como renda, raça/cor e cobertura de saúde. | Evidência sobre vias de obtenção na população estudada. [Fiocruz](https://periodicos.fiocruz.br/pt-br/node/41168) |
| Nascimento et al. (2017), PNAUM–Serviços | Disponibilidade média de **52,9%** para um conjunto de medicamentos traçadores observados na atenção primária do SUS em amostra de 273 municípios. | Retrato da amostra e do conjunto de traçadores. [Revista de Saúde Pública](https://revistas.usp.br/rsp/pt_BR/article/view/139736) |
| Ministério da Saúde | Distribuição e dispensação de insulinas humanas e agulhas envolvem responsabilidades dos entes e procedimentos locais. | Contextualiza a existência de diferentes unidades e orientações. [Ministério da Saúde](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas) |
| Brasil, Lei nº 14.654/2023 | Prevê divulgação eletrônica dos estoques de medicamentos das farmácias públicas do SUS com atualização quinzenal. | Contexto de transparência. [Lei nº 14.654/2023](https://legis.senado.leg.br/norma/37511268/publicacao/37513960) |
| Meiners et al. (2017), PNAUM | Estudo de acesso, gratuidade e adesão a medicamentos entre pessoas com diabetes. | Apoia o contexto da proposta. O DOI e o ano foram corrigidos na documentação posterior. [Revista Brasileira de Epidemiologia](https://www.scielo.br/j/rbepid/a/gjRBy6Q3mX6rnSK8frkTJbv/?lang=pt) |

### Escopo e impacto esperado

```mermaid
flowchart LR
    pessoa["Cidadão ou cuidador"] --> busca["Pesquisar um item prescrito"]
    unidade["Unidade participante"] --> busca
    busca --> dados["Ver disponibilidade, horário e instruções"]
    dados --> pedido["Solicitar reserva onde habilitada"]
    pedido --> decisao["Aguardar análise da unidade"]
    decisao --> balcao["Retirar na unidade quando confirmada"]
```

O diagrama representa a **proposta de setembro**. O README já esboçava quatro domínios de software. O material arquivado inclui a contextualização, um cenário ilustrativo, um pitch distribuído em quatro falas, a identidade visual e as referências. No corte de 17/09, o repositório continha esses documentos e a licença, sem sistema executável.

| Objetivo | Indicador proposto | Evidência a coletar em um piloto |
| --- | --- | --- |
| Localizar um ponto de retirada com menos esforço | Tempo da primeira busca à localização de uma unidade apta | Registro da jornada de busca e confirmação do usuário. |
| Reduzir viagens improdutivas | Percentual de viagens iniciadas após consulta que terminam sem retirada | Pesquisa após a visita, inclusive para quem deixou de usar o portal. |
| Dar previsibilidade às solicitações | Confirmadas sobre solicitações e tempo entre pedido e entrega | Estados, timestamps e identificadores de reserva, com recorte por unidade. |
| Organizar atendimento e recorrência | Solicitações concluídas, rejeitadas ou expiradas, continuidade das retiradas e satisfação | Histórico operacional e questionário voluntário após o atendimento. |

São indicadores propostos. O histórico disponível não traz linha de base, piloto controlado ou efeitos clínicos medidos. A evolução posterior refinou a linguagem sobre projeção, explicação de origem do catálogo e fluxos de cadastro, manutenção e retirada. Também corrigiu a referência de Meiners. [Concepção atual](parte-1-concepcao-e-pitch.md) · [Revisão de novembro](https://github.com/ArthurDp78/GlicoAcesso/commit/1360333)

## Etapa 2 — Arquitetura e projeto do sistema

### Arquitetura no congelamento

O desenho congelado em 21/10 organizava os quatro domínios em serviços com propriedade exclusiva de dados. **Unidades** responde sobre a rede e suas regras de atendimento. **Estoque** detém catálogo, saldos e alocações. **Reservas** detém a solicitação e, nesse desenho, coordenava a SAGA. **Retiradas** prepara autorização e responde pelo registro da entrega. Essas fronteiras evitam que o portal tenha de combinar dados internamente ou que a entrega dependa de escritas em bancos alheios. [Diagrama original](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/02-diagrama-arquitetura.md)

```mermaid
flowchart TB
    cidadao["Portal do cidadão"] --> gateway["API Gateway"]
    profissional["Painel da unidade"] --> gateway
    gateway --> bffCidadao["BFF Cidadão"]
    gateway --> bffUnidade["BFF Unidade"]
    bffCidadao --> unidades["Unidades"]
    bffCidadao --> estoque["Estoque"]
    bffCidadao --> reservas["Reservas e coordenação da SAGA"]
    bffUnidade --> unidades
    bffUnidade --> estoque
    bffUnidade --> reservas
    bffUnidade --> retiradas["Retiradas"]
    reservas -->|"Comandos REST"| estoque
    reservas -->|"Comandos REST"| retiradas
    retiradas -.->|"Evento de retirada"| broker["RabbitMQ"]
    estoque -.->|"Eventos de estoque"| broker
    broker -.-> reservas
    broker -.-> estoque
```

REST atende consultas e comandos que precisam de resposta de um serviço proprietário. RabbitMQ transporta fatos após confirmação de uma transação local. No congelamento, havia quatro bancos projetados, seis arquivos OpenAPI e diagramas lógicos. Em 22/10 dois commits ajustaram a sintaxe dos diagramas da SAGA. Provedor de identidade, topologia de implantação, endereços e parâmetros de execução ainda estavam abertos. A separação do Orquestrador, seu banco próprio e o terceiro consumidor do evento de retirada pertencem à revisão posterior. [Resumo no congelamento](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/resumo-arquitetura.md) · [Revisão arquitetural de 24/11](https://github.com/ArthurDp78/GlicoAcesso/compare/1ca8bef...3ecb975)

### Gateway, BFFs, REST e HATEOAS

O Gateway concentra a entrada e encaminha somente as combinações de caminho e método expostas. O BFF adapta o contrato para o cliente. O BFF Cidadão combina cadastro e projeção de estoque por unidade, devolvendo disponibilidade como booleano, horário e orientação. O BFF Unidade exibe saldos, alocações, solicitações e, no detalhe de uma reserva, autorização quando aplicável. As diferenças atendem às tarefas de cada público e limitam a divulgação do saldo operacional.

```mermaid
flowchart LR
    request["Chamada HTTP"] --> gate{"Rota registrada no Gateway"}
    gate -->|"api/cidadao/v1"| citizen["BFF Cidadão"]
    gate -->|"api/unidade/v1"| unit["BFF Unidade"]
    gate -->|"internal/v1"| inaccessible["Fora das rotas públicas"]
    citizen --> view["Disponibilidade, orientações e reserva própria"]
    unit --> work["Fila, saldo e autorização de retirada"]
```

Os prefixos versionados são `/api/cidadao/v1`, `/api/unidade/v1` e `/internal/v1`. Os contratos distinguem consultas `GET`, criações e comandos `POST`, substituições de estado cadastral `PUT`, atualização de situação `PATCH` e liberação de alocação `DELETE`. `201` indica criação, `202` indica processamento aceito, `204` indica conclusão sem corpo, e `409` indica incompatibilidade de estado ou conflito de idempotência. Consulte o [catálogo](#catálogo-de-apis) para autenticação e respostas por operação.

HATEOAS coloca em `_links` o método, a rota e, no painel, o corpo quando necessário. O cidadão recebe `self` e pode receber `cancelar`. A unidade pode receber `aceitar`, `rejeitar` e `cancelar`, além de `autorizacao-retirada` quando a reserva está confirmada e a autorização ativa. O cliente usa esses links para montar ações, e os serviços revalidam o estado no comando. Uma resposta obtida antes de outro usuário agir pode conter um link que deixou de ser executável.

**Rastreio no código atual.** O [Gateway](../servicos/gateway/main.py) repassa método, corpo, parâmetros e cabeçalhos selecionados. [BFF Cidadão](../servicos/bff_cidadao/main.py) e [BFF Unidade](../servicos/bff_unidade/main.py) compõem as respostas. Consulte o mesmo UUID pelos dois caminhos de reserva com as credenciais de demonstração compatíveis para comparar os contratos. O BFF Cidadão faz uma requisição por unidade ativa na busca, com concorrência limitada a 12. Um par sem projeção é omitido. A indisponibilidade de uma dependência pode interromper toda a busca. No painel, a falha ao consultar apenas o nome complementar do item é tolerada. [Projeto do Gateway](parte-2/03-api-gateway.md) · [Projeto dos BFFs](parte-2/04-bffs.md) · [HATEOAS](parte-2/07-hateoas.md)

### Persistência, Outbox e CQRS

**Banco por serviço.** O desenho previa quatro PostgreSQL independentes. Transações, unicidade, chaves locais e restrições de saldo apoiam a integridade de cada domínio. Identificadores de outros domínios são referências mantidas via API ou eventos. A revisão posterior acrescentou o banco do Orquestrador para separar estado de execução do estado de negócio. A topologia atual pode ser demonstrada no Compose consultando o banco próprio de cada serviço. [Projeto de bancos](parte-2/09-bancos.md) · [Topologia atual](#arquitetura-e-dados-atuais)

**Consistência eventual e Transactional Outbox.** Gravar a entrega em PostgreSQL e publicar separadamente no broker cria um dual write. Uma falha entre as duas ações poderia perder o fato ou publicar um efeito que o banco não confirmou. O desenho registra o efeito e o evento na mesma transação local e delega a publicação posterior ao worker. O padrão se aplica à entrega física em Retiradas e às alterações de saldo em Estoque. A Inbox registra consumo por par consumidor/evento junto da aplicação local. Se a publicação for confirmada e o status da Outbox não puder ser gravado, a mesma mensagem pode sair novamente.

**CQRS de Estoque.** O saldo e as alocações atendem aos comandos. A tabela `disponibilidade` atende à leitura no mesmo PostgreSQL, com esquema e atualização separados. O consumidor usa o snapshot de saldo no evento, a identidade do evento e a versão crescente por par unidade/item. A disponibilidade é o físico menos o alocado. Uma baixa de retirada reduz as duas parcelas na mesma quantidade, pois a disponibilidade já havia sido reduzida na alocação. O instante `atualizadoEm` pertence ao estado projetado. O projeto definiu cerca de **5 s** em condições normais como meta de defasagem. O script de validação usa uma janela de espera de 60 s, e o repositório não publica medições dessa meta. [Consistência e dual write](parte-2/10-consistencia.md) · [Outbox e Inbox](parte-2/11-outbox.md) · [CQRS](parte-2/12-cqrs.md)

```mermaid
flowchart LR
    cmd["Entrada, alocação, ajuste ou baixa"] --> tx["Transação local em Estoque"]
    tx --> saldo[("Saldo canônico e movimentações")]
    tx --> outbox[("Outbox")]
    outbox --> worker["Publicador após commit"]
    worker --> mq["RabbitMQ"]
    mq --> proj["Consumidor com Inbox e comparação de versão"]
    proj --> read[("Projeção disponibilidade")]
    read --> bff["Consulta pelos BFFs"]
```

No código, [eventos de Estoque](../servicos/estoque/eventos.py) gravam e projetam o estado, [Retiradas](../servicos/retiradas/main.py) grava o evento de entrega, [mensageria](../servicos/mensageria.py) implementa publicação e consumo. Para demonstrar, registre uma entrada pelo painel e observe a alteração saindo da resposta da escrita e aparecendo na consulta. Use a disponibilidade projetada para informar a busca e o saldo canônico para validar o comando. Falhas do broker podem atrasar a projeção, e mensagens inválidas exigem inspeção da fila de erro.

### SAGA e compensações

Uma SAGA coordena transações locais de vários serviços e usa comandos compensatórios quando uma transação posterior não pode ser concluída. A equipe escolheu orquestração para tornar explícita a ordem de alocação, autorização e confirmação, simplificar a auditoria e concentrar decisões sobre falha. Na alternativa coreografada os serviços reagiriam a eventos de etapa e distribuiriam essas decisões. A ordem continua explícita na implementação de novembro, agora em um Orquestrador independente. [Decisão original](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/06-saga.md)

| Resultado projetado em outubro | Decisão |
| --- | --- |
| Caminho feliz | Reservas coordena, Estoque aloca, Retiradas autoriza e Reservas confirma. |
| Recusa de estoque | Encerra a confirmação em falha sem criar autorização. |
| Recusa conclusiva de autorização após alocação | Libera a quantidade alocada e conclui a compensação. |
| Autorização possivelmente criada em falha definitiva posterior | Revoga a autorização antes de liberar a alocação. |
| Timeout ou resposta perdida | Repete o comando com chave e conteúdo idempotentes para recuperar o resultado. |

Os diagramas históricos explicitam os participantes e a ordem. [Caminho feliz no corte de outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/diagramas/saga-caminho-feliz.md) · [Compensação no corte de outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/diagramas/saga-compensacao.md) · [Correções dos diagramas em 22/10](https://github.com/ArthurDp78/GlicoAcesso/compare/b059d68...1ca8bef)

A seção [Fluxos implementados](#fluxos-implementados) traz esses caminhos no executável, aponta o executor e descreve como reproduzi-los. O custo da coordenação explícita é operar um trabalhador durável e lidar com estados intermediários, indisponibilidade temporária e reconciliação. Os componentes de borda encaminham ou compõem respostas. O coordenador detém o progresso da transação distribuída.

## Etapa 3 — Infraestrutura e implantação

### Corte de novembro e evolução posterior

Na data de apresentação de **17/11**, o histórico disponível ainda terminava nos ajustes de diagramas de 22/10. Os arquivos de implantação e testes atuais documentam a execução **posterior à data da etapa**. Em 24/11 entraram a base Python, as primeiras rotas e portais, a SAGA, o primeiro consumidor CQRS, oito Dockerfiles e o Compose. Em 25/11 foram integrados cancelamento, eventos de retirada, mais consumidores e a verificação da compensação. O README passou a orientar a execução pela `main`. [Primeira base Python](https://github.com/ArthurDp78/GlicoAcesso/commit/db56a65) · [Dockerfiles](https://github.com/ArthurDp78/GlicoAcesso/commit/8b265b7) · [Compose](https://github.com/ArthurDp78/GlicoAcesso/commit/3cf7772) · [Validação](https://github.com/ArthurDp78/GlicoAcesso/commit/b4c2130)

A presença de portais, scripts e código dá meios para demonstrar a solução posterior. As capturas de 25/11 mostram a consulta pública e o painel carregado com uma solicitação pendente. O histórico examinado não inclui vídeo ou link de gravação que confirme duração, presença dos quatro integrantes e execução em 17/11. [Portal do cidadão](assets/portal-cidadao.png) · [Painel da unidade](assets/painel-unidade.png)

### Topologia Compose

```mermaid
flowchart TB
    browser["Navegador no host"] --> edge["borda · Gateway"]
    edge --> bff["BFF Cidadão e BFF Unidade"]
    bff --> api["servicos · domínios e Orquestrador"]
    cli["CLI em Compose administrativo"] --> admin["administracao · Unidades"]
    api --> databases["Cinco redes dados-* · um par serviço e PostgreSQL por rede"]
    api --> events["mensageria · RabbitMQ e quatro aplicações"]
    databases --> data["Cinco volumes PostgreSQL"]
    events --> brokerDisk["Volume RabbitMQ"]
```

O diagrama resume as redes do [Compose principal](../docker-compose.yml) e do [Compose administrativo](../compose.admin.yml). A CLI é um contêiner avulso no perfil `admin`, com a imagem de Unidades e montagem de arquivo JSON somente leitura. Na rede de mensageria estão Estoque, Retiradas, Reservas, Orquestrador e RabbitMQ. A rede de administração conecta Unidades e a CLI. A rede de serviços conecta os BFFs, os quatro domínios e o Orquestrador. Com exceção de `borda`, as redes do Compose principal são internas.

| Aplicação ou dependência | Porta e exposição no Compose |
| --- | --- |
| Gateway | Contêiner `8000`. Publicação somente em `127.0.0.1:${GLICO_GATEWAY_PORTA:-8000}`. |
| BFF Cidadão e BFF Unidade | `8001` e `8005`, sem publicação no host. |
| Unidades, Estoque, Reservas e Retiradas | `8002`, `8003`, `8004` e `8007`, respectivamente, na rede interna. |
| Orquestrador | `8006`, na rede interna. |
| PostgreSQL 17 | Cinco instâncias, porta interna `5432`, volumes `postgres-unidades`, `postgres-estoque`, `postgres-reservas`, `postgres-orquestrador` e `postgres-retiradas`. |
| RabbitMQ 4 management | AMQP interno em `5672`, volume `rabbitmq`. A interface de administração da imagem também fica sem publicação no host. |

Cada serviço tem seu Dockerfile. São três estágios nomeados, uma base Python 3.14 slim, instalação travada via `uv sync --locked` e runtime com ambiente virtual e código necessário. O `uv` e o cache da instalação ficam na etapa de dependências. As imagens executam com UID/GID 10001. O Gateway carrega os HTML, CSS, JavaScript e a marca. Os cinco serviços persistentes carregam as migrações SQL e iniciam o Uvicorn só depois da execução de [migrações](../servicos/migracoes.py). O migrador aplica os nomes em ordem, registra cada arquivo aplicado e usa lock transacional. A carga opcional de demonstração roda em Unidades e Estoque. [Dockerfile do Gateway](../servicos/gateway/Dockerfile) · [Dockerfile de Estoque](../servicos/estoque/Dockerfile)

Os bancos usam `pg_isready`, RabbitMQ usa `rabbitmq-diagnostics -q ping` e cada aplicação expõe `/health`. As dependências declaradas usam `service_healthy`. Essas rotas HTTP confirmam a resposta do processo. A subida com `--wait` precisa ser complementada por uma operação real através dos BFFs para atestar disponibilidade funcional de banco, broker e serviços a jusante.

### Configuração

Preencha `.env` com valores aleatórios distintos. O [modelo](../.env.example) contém os nomes e valores de demonstração que podem ser versionados. A tabela descreve a finalidade das credenciais e parâmetros.

| Variável | Uso |
| --- | --- |
| `POSTGRES_UNIDADES_PASSWORD`, `POSTGRES_ESTOQUE_PASSWORD`, `POSTGRES_RESERVAS_PASSWORD`, `POSTGRES_ORQUESTRADOR_PASSWORD`, `POSTGRES_RETIRADAS_PASSWORD` | Cinco senhas independentes. Use caracteres hexadecimais para compor as URLs do Compose. |
| `RABBITMQ_PASSWORD` | Conta de mensageria e URLs dos quatro participantes. |
| `GLICO_CIDADAO_TOKEN`, `GLICO_PROFISSIONAL_TOKEN`, `GLICO_PROFISSIONAL_UNIDADE_ID` | Perfis da demonstração. O vínculo do profissional deve apontar para uma unidade cadastrada. |
| `GLICO_GESTOR_REDE_TOKEN` | Cadastro administrativo de unidade, usada em Unidades e na CLI. |
| `GLICO_RESERVAS_SERVICE_TOKEN`, `GLICO_ORQUESTRADOR_SERVICE_TOKEN`, `GLICO_RETIRADAS_SERVICE_TOKEN` | Credenciais internas distintas para validação de reserva, etapas da SAGA e leitura canônica antes da entrega. |
| `GLICO_BFF_UNIDADE_SIGNING_KEY`, `GLICO_BFF_CIDADAO_SIGNING_KEY` | Chaves distintas para delegação entre BFF e Orquestrador. |
| `GLICO_GATEWAY_PORTA`, `GLICO_REDE_ADMINISTRATIVA` | Porta publicada e nome da rede também usada pelo Compose administrativo. |
| `GLICO_CARREGAR_DEMO`, `GLICO_FALHA_PREPARAR_AUTORIZACAO` | Carga inicial fictícia e injeção de recusa para testar compensação. Defaults `1` e `0`. |

Algumas chaves internas aceitam valor vazio na interpolação do Compose para compatibilidade com instalações existentes. A retirada precisa de `GLICO_RETIRADAS_SERVICE_TOKEN` em Reservas e Retiradas, e o cancelamento distribuído do cidadão precisa de `GLICO_BFF_CIDADAO_SIGNING_KEY` no BFF e no Orquestrador. Configure ambas para o fluxo completo. Na execução manual, defina ainda os `*_DATABASE_URL`, `RABBITMQ_URL` e as URLs dos destinos HTTP conforme os hosts escolhidos. [Configuração completa](../docker-compose.yml) · [Execução manual no Windows](../README.md#demonstração-com-serviços-python-no-windows)

### Executar do zero

Pré-requisitos para a execução integrada são Git, Docker com daemon ativo, plugin Compose, acesso aos registros das imagens e navegador. A instalação abaixo usa Bash e Python 3 somente para gerar `.env`. Para PowerShell, há [comando equivalente](../README.md#subir-o-sistema-completo-com-docker-compose).

```bash
git clone https://github.com/ArthurDp78/GlicoAcesso.git
cd GlicoAcesso
python3 - <<'PY'
from os import open as open_file
from pathlib import Path
from secrets import token_hex

lines = Path(".env.example").read_text(encoding="utf-8").splitlines()
content = [line + token_hex(32) if line.endswith("=") and line[:-1].isidentifier() else line
           for line in lines]
try:
    with open(".env", "x", encoding="utf-8", opener=lambda path, flags: open_file(path, flags, 0o600)) as target:
        target.write("\n".join(content) + "\n")
except FileExistsError:
    print("Preservado .env existente. Confira os campos de .env.example.")
PY
docker compose config --quiet
docker compose up --build -d --wait
docker compose ps
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/api/cidadao/v1/itens
```

Abra `http://127.0.0.1:8000/cidadao` e `http://127.0.0.1:8000/unidade`, ajustando a porta quando necessário. O catálogo e a busca são públicos. Para reservar, informe no portal o valor local de `GLICO_CIDADAO_TOKEN`. Para operar a unidade, informe `GLICO_PROFISSIONAL_TOKEN` no painel. Comece com “Tiras reagentes para glicemia”, o item de exemplo indicado no README. Uma unidade ativa aparece na busca quando existe projeção para a combinação consultada. No ambiente sem demonstração, cadastre uma unidade, vincule o perfil local, registre estoque e habilite reservas. [Sequência de cadastro via CLI e exemplo de JSON](../README.md#cadastrar-uma-unidade-pelo-comando-administrativo)

```bash
# Após criar unidade.json no diretório atual
chave="$(python3 -c 'import uuid; print(uuid.uuid4())')"
docker compose -f compose.admin.yml --profile admin run --build --rm \
  --volume "$PWD/unidade.json:/dados/unidade.json:ro" cadastro-unidades \
  --arquivo /dados/unidade.json --chave "$chave"
```

Guarde o valor de `chave` para repetir o cadastro após timeout. Mesmo arquivo e mesma chave recuperam o resultado idempotente. Para reproduzir a suíte isolada com PowerShell, execute `pwsh -File scripts/validar-compose.ps1`. O script cria projeto, rede, credenciais e volumes de teste e os descarta ao final, inclusive em falha. `docker compose down` encerra a instalação principal e preserva os volumes. Use o mesmo `.env` ao reiniciar com volumes existentes. [Script integrado](../scripts/validar-compose.ps1)

| Sintoma | Checagem |
| --- | --- |
| Porta ocupada | Ajuste `GLICO_GATEWAY_PORTA` e use a nova porta no navegador. O script isolado aceita `-Porta`. |
| Compose reclama de variável ausente | Preencha as linhas vazias do modelo com valores distintos antes de subir. |
| Banco ou broker falham após troca de senha | Confira se as credenciais coincidem com a configuração dos volumes existentes e examine os logs. |
| Consulta abre, mas reserva ou retirada falha | Confira tokens, papel, unidade vinculada, autorização e chaves internas de comunicação. Use `docker compose logs reservas retiradas orquestrador`. |
| Saúde responde, mas saldo público permanece antigo | Consulte `atualizadoEm`, os logs de Estoque e RabbitMQ e a publicação e o consumo das filas. O estado projetado é assíncrono. |
| A CLI não encontra Unidades | Suba primeiro o Compose principal e confirme `GLICO_REDE_ADMINISTRATIVA` nos dois arquivos. |

## Etapa 4 — Integração final e inteligência artificial

### Fluxos implementados

O ponto de partida desta etapa é a infraestrutura publicada em 24/11. Os commits de 25/11 acrescentaram manutenção da unidade, ajustes de estoque, expiração, cancelamento durável, registro de retirada e observação por três consumidores. O fluxo atravessa Gateway, BFF e domínio. O panorama a seguir descreve o código no corte de 25/11, com congelamento previsto para 09/12. [Integração de domínio](https://github.com/ArthurDp78/GlicoAcesso/commit/8f4c8f7) · [Consumidores e teste de retirada/cancelamento](https://github.com/ArthurDp78/GlicoAcesso/commit/4a22ed9)

**Criação e decisão.** Reservas consulta o prazo de uma unidade ativa (1 a 720 horas) e a permissão canônica do par unidade/item. Grava `SOLICITADA` e `decisaoAte` em transação local. O prazo é preservado na reserva. O profissional vinculado pode rejeitar ou pedir confirmação no prazo. Rejeitar é local em Reservas. Um trabalhador marca solicitações vencidas como `EXPIRADA`. O aceite preliminar autoriza o BFF Unidade a encaminhar ao Orquestrador, que responde `202`. O trabalhador revalida e executa a transição para `EM_CONFIRMACAO`. [Reservas](../servicos/reservas/main.py) · [BFF Unidade](../servicos/bff_unidade/main.py)

```mermaid
sequenceDiagram
    participant P as Profissional
    participant G as Gateway
    participant B as BFF Unidade
    participant O as Orquestrador
    participant R as Reservas
    participant E as Estoque
    participant T as Retiradas
    P->>G: Enviar decisão ACEITAR
    G->>B: Repassar credencial e chave
    B->>R: Validar decisão da unidade
    R-->>B: ACEITE_ENCAMINHAR
    B->>O: Persistir solicitação de confirmação
    O-->>B: 202
    B-->>G: 202 com Location do painel
    G-->>P: Acompanhar a reserva
    O->>R: Aceitar e passar para EM_CONFIRMACAO
    O->>E: Alocar no saldo canônico
    E-->>O: 201 alocação
    O->>T: Preparar autorização
    T-->>O: 201 autorização
    O->>R: Confirmar a reserva
    R-->>O: 200 CONFIRMADA
    O->>O: Marcar SAGA CONCLUIDA
```

**Compensação.** Cada etapa guarda a intenção e uma chave estável antes da chamada. O executor serializa o progresso com lock e `SKIP LOCKED`. Falha conclusiva de Retiradas com `AUTORIZACAO_NAO_CRIADA` libera a alocação antes de encerrar a reserva em `FALHA_CONFIRMACAO` e a SAGA em `COMPENSADA`. Se a autorização pode existir e o resultado já é conclusivo para compensar, a revogação vem antes da liberação. Timeout, erro de rede e resposta incerta repetem a etapa e usam espera exponencial até 30 s entre tentativas. `COMPENSACAO_PENDENTE` ou `CANCELAMENTO_PENDENTE` identifica a espera quando aplicável. [Executor](../servicos/orquestrador/executor.py) · [Diagrama detalhado atual](parte-2/diagramas/saga-falha.md)

```mermaid
sequenceDiagram
    participant O as Orquestrador
    participant E as Estoque
    participant T as Retiradas
    participant R as Reservas
    O->>E: Alocar quantidade
    E-->>O: 201 alocação
    O->>T: Preparar autorização
    T-->>O: 422 AUTORIZACAO_NAO_CRIADA
    O->>E: Liberar alocação
    E-->>O: 204
    O->>R: Registrar falha da confirmação
    R-->>O: 200 FALHA_CONFIRMACAO
    O->>O: Marcar SAGA COMPENSADA
```

**Retirada.** O profissional busca a reserva pelo código e registra a entrega autorizada. Retiradas confere a unidade, o estado canônico e a autorização. A transação local grava a entrega, marca a autorização utilizada e inclui `retirada.concluida.v1` na Outbox. Reservas consome e marca `RETIRADA`, Estoque baixa o físico e encerra a alocação, e Orquestrador guarda evidência de entrega. O trabalhador de Estoque emite um segundo evento para atualizar a projeção. [Retiradas](../servicos/retiradas/main.py) · [Consumidor de Reservas](../servicos/reservas/eventos.py) · [Consumidor de Estoque](../servicos/estoque/retiradas.py) · [Consumidor do Orquestrador](../servicos/orquestrador/eventos.py)

```mermaid
flowchart TD
    panel["Painel e Gateway"] --> bff["BFF Unidade"]
    bff --> delivery["Retiradas · entrega e Outbox"]
    delivery --> broker["RabbitMQ · retirada concluída"]
    broker --> reservations["Reservas · status RETIRADA"]
    broker --> inventory["Estoque · baixa física e baixa da alocação"]
    broker --> workflow["Orquestrador · evidência da entrega"]
    inventory --> outbox["Outbox · retirada baixada"]
    outbox --> projection["RabbitMQ e consumidor da projeção"]
    projection --> stock["Disponibilidade atualizada"]
```

**Cancelamento.** O cidadão cancela a própria reserva, e o profissional da unidade informa uma justificativa válida de pelo menos cinco caracteres. Em `SOLICITADA` dentro do prazo, a transição é local e pode retornar `200`. Se a confirmação começou ou terminou, o BFF encaminha com delegação assinada, e o Orquestrador responde `202`. O cancelamento aguarda uma confirmação ativa, sinaliza `CANCELAMENTO_EM_ANDAMENTO`, revoga a autorização antes de liberar a alocação e pede a conclusão a Reservas. Uma entrega já registrada interrompe o cancelamento e o evento leva a reserva a `RETIRADA`. Para o cidadão a confirmação ou o cancelamento podem exigir consulta posterior. [Encaminhamento nos BFFs](../servicos/cancelamento_bff.py) · [Diagrama concorrência entrega/cancelamento](parte-2/diagramas/saga-cancelamento-retirada.md)

**Como demonstrar com a validação do repositório.** O script integrado cadastra unidade, registra quatro unidades de um item, habilita a reserva, solicita duas, acompanha o aceite e observa a projeção de duas disponíveis. Em seguida registra a retirada e espera físico 2, alocado 0 e disponível 2. Exercita cancelamento local e distribuído. Na seção de compensação, recria Retiradas com `GLICO_FALHA_PREPARAR_AUTORIZACAO=1` em ambiente isolado, aceita outra reserva e confere liberação canônica, ausência de autorização, `COMPENSADA` e projeção. Por fim recria os contêineres mantendo os volumes e confere persistência e repetição idempotente. Esse é o comportamento programado do roteiro. O [registro de verificação](#testes-e-evidências) indica o que foi executado nesta análise. [Roteiro executável](../scripts/validar-compose.ps1)

### Inteligência artificial e avaliação

O corte de 25/11 tem portal, regras de domínio, catálogo SQL e APIs operacionais. O repositório está sem serviço LLM, documentos ingeridos para recuperação, embeddings, banco vetorial, cadeia de recuperação e geração, tool LangChain, assistente ou agente. O catálogo SQL é usado por Estoque. Os mecanismos de timeout, retry e compensação encontrados pertencem ao sistema distribuído e não demonstram resiliência de IA. [Dependências travadas](../pyproject.toml) · [Catálogo](../servicos/estoque/migrations/004_catalogo_diabetes_pfpb.sql) · [Infraestrutura atual](../docker-compose.yml)

O requisito futuro é aplicar IA a uma necessidade do domínio. No protótipo atual, a pessoa consulta as orientações cadastradas, o horário, a disponibilidade e o estado da reserva diretamente na interface. Para a avaliação acadêmica, a base própria, ingestão, recuperação, geração com e sem RAG, integração LangChain e pelo menos dois mecanismos de resiliência são entregas a comprovar no congelamento. O repositório ainda não traz as cinco perguntas de avaliação, respostas comparáveis, latência, estimativas por operação ou projeções em escala. Na ausência de implementação, esta revisão não atribui ao projeto um desenho RAG, fornecedor ou métricas.

## Visão consolidada do sistema

### Arquitetura e dados atuais

![Arquitetura do GlicoAcesso com Gateway, BFFs, SAGA, serviços e eventos RabbitMQ](assets/glicoacesso-arquitetura.svg)

O diagrama da equipe reúne as chamadas HTTP, a coordenação da confirmação e do cancelamento, os bancos por serviço e o caminho da Outbox até os consumidores. O Orquestrador recebe o evento de cada entrega concluída em uma fila própria, inclusive quando há cancelamento em andamento. [Abrir o SVG em tamanho original](assets/glicoacesso-arquitetura.svg) · [Consumidor do Orquestrador](../servicos/orquestrador/eventos.py)

<details>
<summary>Mapa de chamadas e eventos em Mermaid</summary>

```mermaid
flowchart LR
    citizen["Portal cidadão"] --> gw["Gateway"]
    professional["Painel unidade"] --> gw
    gw --> bc["BFF Cidadão"]
    gw --> bu["BFF Unidade"]
    bc --> u["Unidades"]
    bc --> e["Estoque"]
    bc --> r["Reservas"]
    bc -->|"Cancelar"| o["Orquestrador"]
    bu --> u
    bu --> e
    bu --> r
    bu --> t["Retiradas"]
    bu -->|"Confirmar ou cancelar"| o
    manager["CLI do gestor"] --> u
    r --> u
    r --> e
    e -->|"Verificar unidade ativa"| u
    t -->|"Verificar reserva"| r
    o -->|"Validar e aplicar estados"| r
    o -->|"Alocar ou liberar"| e
    o -->|"Preparar ou revogar autorização"| t
    e -.-> broker["RabbitMQ"]
    t -.-> broker
    broker -.-> e
    broker -.-> r
    broker -.-> o
```

</details>

O mapa Mermaid também mostra a CLI do gestor e a consulta de Estoque a Unidades para validar o vínculo com uma unidade ativa nas alterações de estoque. As interfaces do cidadão e do profissional são portais web servidos pelo Gateway. Os clientes usam as rotas dos BFFs e os links de ação que eles retornam. [Código dos portais](../servicos/gateway/portal/) · [Cadastro administrativo](../servicos/unidades/cli.py) · [Diagrama do repositório](parte-2/02-diagrama-arquitetura.md)

| Componente | Responsabilidade | Dados sob sua autoridade | Implementação |
| --- | --- | --- | --- |
| Gateway | Servir portais, validar perfil na borda, rotear chamadas | Sem persistência de domínio | [Gateway](../servicos/gateway/) |
| BFF Cidadão | Agregar consulta pública e apresentar reserva própria | Sem persistência de domínio | [BFF Cidadão](../servicos/bff_cidadao/) |
| BFF Unidade | Apresentar fila, saldos, autorizações e ações por unidade | Sem persistência de domínio | [BFF Unidade](../servicos/bff_unidade/) |
| Unidades | Manter cadastro, situação, horário, contato e prazo | `unidades`, `contatos_unidade`, `horarios_unidade`, comandos idempotentes | [Migrações de Unidades](../servicos/unidades/migrations/) |
| Estoque | Manter catálogo, controlar quantidade e alocações e projetar disponibilidade | `itens`, `saldos`, `alocacoes`, `movimentacoes`, `disponibilidade`, Outbox e Inbox | [Migrações de Estoque](../servicos/estoque/migrations/) |
| Reservas | Manter solicitação, prazos, estado de negócio e histórico | `reservas`, `historico_reserva`, Inbox e comandos idempotentes | [Migrações de Reservas](../servicos/reservas/migrations/) |
| Retiradas | Autorizar e registrar entrega | `autorizacoes`, `entregas`, Outbox e comandos idempotentes | [Migrações de Retiradas](../servicos/retiradas/migrations/) |
| Orquestrador | Persistir e executar confirmações, compensações e cancelamentos | `saga_execucoes`, `saga_etapas`, `entregas_observadas`, Inbox e comandos idempotentes | [Migrações do Orquestrador](../servicos/orquestrador/migrations/) |

```mermaid
flowchart LR
    units["Unidades"] --> unitsDb[("unidades · cadastro e horários")]
    stock["Estoque"] --> stockDb[("estoque · saldo, alocações e projeção")]
    reservations["Reservas"] --> reservationsDb[("reservas · estado e histórico")]
    pickups["Retiradas"] --> pickupsDb[("retiradas · autorizações e entregas")]
    saga["Orquestrador"] --> sagaDb[("orquestrador · execuções e etapas")]
```

A persistência usa PostgreSQL 17, SQL e Psycopg. Cada domínio e o Orquestrador acessam somente seu banco. Estoque garante saldo físico não negativo e alocado entre zero e o físico. Uma entrada positiva cria ou aumenta o saldo. A permissão de reserva é controlada por unidade e item. Ajuste exige motivo e respeita alocações e limite do saldo. A presença de um item no catálogo não implica existência de saldo nem disponibilidade em unidade específica. A migração inclui medicamentos para diabetes do Farmácia Popular, e a carga fictícia inclui tiras reagentes. O catálogo é carregado localmente. [SQL de catálogo](../servicos/estoque/migrations/004_catalogo_diabetes_pfpb.sql) · [Dados de demonstração](../servicos/estoque/demo.sql)

### Mensageria e operação

RabbitMQ usa a exchange topic durável `glico.eventos`. `retirada.concluida.v1` vai a filas independentes de Reservas, Estoque e Orquestrador. A fila `estoque.projecao-disponibilidade` recebe `estoque.#`, que inclui `estoque.alocacao-criada.v1`, `estoque.alocacao-liberada.v1`, `estoque.entrada-registrada.v1`, `estoque.ajuste-registrado.v1`, `estoque.permissao-alterada.v1` e `estoque.retirada-baixada.v1`. Cada evento inclui identidade, tipo e versão, agregado, correlação, instante e conteúdo. [Implementação de mensageria](../servicos/mensageria.py) · [Eventos de estoque](../servicos/estoque/eventos.py)

Mensagens persistentes, confirmação de publicação, atualização posterior da Outbox, ACK após o commit, deduplicação e dead letter tratam falhas comuns. O envio pode ser repetido. Banco temporariamente indisponível causa reentrega, enquanto falha permanente de validação segue para a fila de erro. O desenho descreve recuperação da projeção a partir de `saldos`. A `main` analisada não oferece comando administrativo para reconstruí-la. Existe um commit de reconstrução na branch de backend ainda sem merge. [Projeto da reconstrução](parte-2/12-cqrs.md) · [Implementação em branch](https://github.com/ArthurDp78/GlicoAcesso/commit/166aa65)

### Catálogo de APIs

O catálogo abaixo enumera as rotas de negócio da revisão. Os contratos por serviço trazem schemas e exemplos. Para conferir um campo ou status em caso de divergência, prevalecem os modelos Pydantic, os handlers e as respostas de execução. `/health` responde `200` em cada aplicação. O Gateway também serve `GET /cidadao`, `GET /unidade`, suas rotas de marca e os arquivos estáticos em `/cidadao/assets` e `/unidade/assets`.

#### Rotas públicas pelo Gateway

| Prefixo | Método e caminho relativo | Principais entradas e respostas |
| --- | --- | --- |
| `/api/cidadao/v1` | `GET /itens`, `GET /unidades` | Catálogo e unidades ativas em listas públicas. `200`. |
| `/api/cidadao/v1` | `GET /explorar` | `itemId` em query, UUID. `200` com dados da unidade, booleanos `disponivel` e `permiteReserva`, orientação e `atualizadoEm`. `422` para UUID ausente/inválido. |
| `/api/cidadao/v1` | `POST /reservas` | Token do cidadão, chave, `unidadeId`, `itemId` e `quantidade` inteira positiva. `201` com representação, `Location` e links. Retorna `422` para unidade inativa, prazo legado inválido ou reserva sem permissão e `409` para conflito de chave. |
| `/api/cidadao/v1` | `GET /reservas/{reservaId}` | Token do cidadão e UUID. `200` com a própria reserva ou `404` quando não pertence ao perfil. |
| `/api/cidadao/v1` | `POST /reservas/{reservaId}/cancelar` | Token e chave, sem justificativa de cidadão. `200` para conclusão local, `202` para cancelamento distribuído e `409` para conflito de estado ou chave. |
| `/api/unidade/v1` | `GET /painel/reservas`, `GET /painel/reservas/{reservaId}` | Token profissional e UUID no detalhe. `200` com fila de pendentes ou detalhe, `404` para reserva inexistente e `403` para reserva de outra unidade. |
| `/api/unidade/v1` | `POST /reservas/{reservaId}/decisao` | Token, chave, `decisao` igual a `ACEITAR` ou `REJEITAR`. `202` no aceite encaminhado e `200` na rejeição concluída. |
| `/api/unidade/v1` | `POST /reservas/{reservaId}/cancelar` | Token, chave e `justificativa`. `200` ou `202`. Estado incompatível retorna `409`. |
| `/api/unidade/v1` | `GET /painel/estoque`, `GET /painel/estoque/catalogo` | Token profissional. `200` com saldos projetados da unidade ou catálogo com identificador da unidade vinculada. |
| `/api/unidade/v1` | `POST /painel/estoque/{unidadeId}/itens/{itemId}/entradas` | Token, chave, `quantidade` positiva e `motivo` opcional. `201` com movimentação e versão. |
| `/api/unidade/v1` | `PUT /painel/estoque/{unidadeId}/itens/{itemId}/permissao` | Token, chave e booleano `permiteReserva`. `200` com a permissão. |
| `/api/unidade/v1` | `POST /painel/estoque/{unidadeId}/itens/{itemId}/ajustes` | Token, chave, `variacaoFisica` inteira diferente de zero e `motivo`. `201` com movimentação. Pode retornar `409` por saldo incompatível. |
| `/api/unidade/v1` | `GET /unidade`, `PUT /unidade` | Perfil profissional vinculado. `200` com o cadastro. PUT exige chave, nome, endereço estruturado, orientações, contatos, horários e prazo. |
| `/api/unidade/v1` | `PUT /unidade/horarios`, `PATCH /unidade/status`, `PUT /unidade/prazo-analise` | Token, chave e `horarios`, `ativa` ou `prazoAnaliseHoras`, respectivamente. `200` com cadastro. |
| `/api/unidade/v1` | `POST /retiradas` | Token, chave e `autorizacaoId`. `201` com `autorizacaoId`, `retiradaId` e `realizadaEm`. Pode retornar `409` por situação incompatível. |

Credencial ausente ou inválida nas rotas protegidas retorna `401`. Papel incorreto, unidade fora do vínculo ou autorização insuficiente podem retornar `403`, com `404` usado em algumas consultas para limitar divulgação. Validação do framework retorna `422`, inclusive chave obrigatória ausente onde declarada como header. Indisponibilidade e timeouts podem retornar `502`, `503` ou `504`, conforme a camada. O cabeçalho `Idempotency-Key` aceita de 1 a 128 caracteres nos comandos principais. [Contrato BFF Cidadão](parte-2/api/bff-cidadao.yaml) · [Contrato BFF Unidade](parte-2/api/bff-unidade.yaml) · [Gateway](../servicos/gateway/main.py)

#### Rotas entre serviços e administração

Os prefixos da tabela abreviam rotas. `I` indica `/internal/v1`, `C` indica `/api/cidadao/v1` e `U` indica `/api/unidade/v1`. Os caminhos com `C` e `U` abaixo são usados entre processos e o Gateway publica apenas a lista anterior.

| Serviço | Operações | Contrato e autorização |
| --- | --- | --- |
| Unidades | `GET C/unidades`. `GET I/unidades/{unidadeId}`. `POST I/unidades`. `PUT I/unidades/{unidadeId}` e `/horarios`. `PATCH I/unidades/{unidadeId}/status`. `GET` e `PUT I/unidades/{unidadeId}/prazo-analise`. | Listagem pública. Cadastro administrativo `201`, manutenção vinculada e consulta de prazo por Reservas. [OpenAPI](parte-2/api/unidade.yaml) · [Handler](../servicos/unidades/main.py) |
| Estoque | `GET C/estoque/itens` e `C/estoque/disponibilidade`. `GET U/estoque/itens` e `U/estoque/{unidadeId}/itens`. `POST U/estoque/{unidadeId}/itens/{itemId}/entradas` e `/ajustes`. `PUT` no mesmo recurso, em `/permissao`. `GET I/unidades/{unidadeId}/itens/{itemId}/permissao-reserva`. `POST I/alocacoes`. `DELETE I/alocacoes/{reservaId}`. | Consulta pública, ações e saldos com perfil profissional, permissão para Reservas e comandos de alocação `201` e liberação `204` para o Orquestrador. Liberação identifica SAGA em `X-Saga-Id`. [OpenAPI](parte-2/api/estoque.yaml) · [Handler](../servicos/estoque/main.py) |
| Reservas | `POST C/reservas` e `C/reservas/{reservaId}/cancelar`. `GET U/reservas`. `POST U/reservas/{reservaId}/decisao` e `/cancelar`. `GET I/reservas/{reservaId}`, `/estado` e `/permissao-cancelamento`. `POST I/reservas/{reservaId}` com sufixos `/aceite`, `/confirmar`, `/falhar-confirmacao`, `/iniciar-cancelamento` e `/finalizar-cancelamento`. | Respostas de operação `200` ou `201` quando concluídas. Comandos de SAGA por credencial do Orquestrador, estado canônico para Retiradas e verificação de vínculo nas consultas e decisões de ator. `ACEITE_ENCAMINHAR` é o sinal interno `409` para o BFF iniciar o fluxo. [OpenAPI](parte-2/api/reserva.yaml) · [Handler](../servicos/reservas/main.py) |
| Retiradas | `POST I/autorizacoes`. `GET I/autorizacoes/{reservaId}`. `POST I/autorizacoes/{reservaId}/cancelar`. `POST U/retiradas`. | Orquestrador prepara `201` e revoga `200`. Profissional consulta `200` e registra entrega `201` mediante autorização vinculada. `409 ENTREGA_JA_REGISTRADA` pode interromper reversão. [OpenAPI](parte-2/api/retirada.yaml) · [Handler](../servicos/retiradas/main.py) |
| Orquestrador | `POST I/reservas/{reservaId}/confirmacoes` e `/cancelamentos`. `GET I/sagas/{sagaId}`. | BFFs enviam ator delegado assinado e chave. Aceite de execução `202`. Consulta de execução `200`, restrita ao ator autorizado. [OpenAPI](parte-2/api/orquestrador.yaml) · [Handler](../servicos/orquestrador/main.py) |

#### Exemplos de contrato

A requisição abaixo usa identificadores da carga fictícia. Configure o token no terminal de teste. Leia o UUID de reserva e a unidade vinculada a partir do fluxo. Reutilize a chave para repetir a mesma solicitação.

```bash
BASE=http://127.0.0.1:8000
curl -sS -i "$BASE/api/cidadao/v1/explorar?itemId=20000000-0000-4000-8000-000000000001"
curl -sS -i -X POST "$BASE/api/cidadao/v1/reservas" \
  -H "Authorization: Bearer ${GLICO_CIDADAO_TOKEN:?Defina a credencial local}" \
  -H 'Idempotency-Key: reserva-demo-001' \
  -H 'Content-Type: application/json' \
  -d '{"unidadeId":"10000000-0000-4000-8000-000000000001","itemId":"20000000-0000-4000-8000-000000000001","quantidade":2}'
```

| Informação de exemplo | BFF Cidadão | BFF Unidade |
| --- | --- | --- |
| Consulta de Estoque | `{"disponivel":true,"permiteReserva":true,"atualizadoEm":"2026-11-25T15:00:00Z"}` | `{"estoqueFisicoAtual":4,"quantidadeAlocada":2,"quantidadeDisponivel":2,"permiteReserva":true,"atualizadoEm":"2026-11-25T15:00:00Z"}` |
| Pendente · ações disponibilizadas | `self` e `cancelar` | `self`, `aceitar`, `rejeitar` e `cancelar` |
| Identidade e autorização | Campos públicos da reserva, sem `cidadaoId` | Identificador do cidadão de demonstração, nome do item quando disponível e dados de autorização quando aplicável |

Um recorte de `_links` no painel para uma reserva pendente usa o corpo de decisão explícito.

```json
{
  "_links": {
    "aceitar": {
      "href": "/api/unidade/v1/reservas/00000000-0000-4000-8000-000000000010/decisao",
      "method": "POST",
      "body": {"decisao": "ACEITAR"}
    }
  }
}
```

### Segurança e operação

As credenciais Bearer estáticas e distintas representam um cidadão, um profissional vinculado a uma unidade e um gestor de rede em demonstração. A borda verifica papel em rotas protegidas e os serviços verificam propriedade, unidade e escopo nos pontos de decisão. Internamente há credenciais por serviço e delegação assinada por HMAC entre BFF e Orquestrador, com validade de 60 segundos e verificação de papel. Em comandos canônicos, a autenticação técnica do Orquestrador acompanha a identidade delegada. O Compose restringe a publicação ao loopback e isola os bancos. O Gateway e serviços com middleware geram ou propagam `X-Correlation-Id`. Respostas sensíveis selecionadas usam `Cache-Control: no-store`. [Identidade](../servicos/identidade_demo.py) · [Delegação](../servicos/delegacao_unidade.py) · [HTTP e correlação](../servicos/http.py)

As interfaces pedem o token de demonstração quando necessário. O perfil usa identificadores fixos e a execução local usa HTTP. Para uso institucional com pessoas e equipes distintas ainda são necessários identidade individual, gestão de credenciais, transporte seguro, avaliação de privacidade, auditoria e procedimentos de restauração e operação. O repositório descreve um protótipo local.

### Organização e tecnologias

| Caminho | Conteúdo |
| --- | --- |
| [`docs/`](./) | Concepção e pitch, decisões arquiteturais, contratos OpenAPI, diagramas e documentação central. |
| [`identidade-visual/`](../identidade-visual/) | Marca original em duas versões PNG. |
| [`servicos/`](../servicos/) | Oito aplicações FastAPI, HTTPX para comunicação, Pydantic para modelos, Psycopg e SQL para dados, Pika para eventos RabbitMQ. |
| [`servicos/gateway/portal/`](../servicos/gateway/portal/) | Dois portais com HTML, CSS e JavaScript. |
| [`scripts/`](../scripts/) | Demonstração local com processos Python e validação da instalação Compose em PowerShell. |
| [`tests/`](../tests/) | Testes unitários e roteiro separado de decisões do executor. |
| [`pyproject.toml`](../pyproject.toml), [`uv.lock`](../uv.lock) e [`.python-version`](../.python-version) | Dependências, versões travadas e Python. |
| [`docker-compose.yml`](../docker-compose.yml) e [`compose.admin.yml`](../compose.admin.yml) | Infraestrutura declarativa e entrada do cadastro administrativo. |

### Testes e evidências

- **Testes unitários.** `python -m unittest discover -s tests -v` executou **14 testes com sucesso** no Python 3.14.10 e nas dependências de `uv.lock`. Abrange validação de cadastro, CLI com respostas controladas, assinatura, expiração e escopo de delegação. [Testes](../tests/)
- **Decisões da SAGA.** [`tests/decisao_saga.py`](../tests/decisao_saga.py) usa respostas e conexão simuladas para conferir transições do executor. A execução separada com `python -m tests.decisao_saga` conferiu **25 casos**. A integração depende de PostgreSQL, RabbitMQ e dos serviços reais.
- **Fluxo integrado fora do Compose.** Subiram oito aplicações, cinco instâncias PostgreSQL 17.12 e RabbitMQ 3.12.1 em processos isolados, usando o código de `9d18a62` e a carga fictícia. O teste atravessou o Gateway, confirmou os contratos diferentes dos BFFs, cadastro e repetição pela CLI, entrada de estoque, CQRS, confirmação, retirada, baixa e cancelamentos local e distribuído. Na falha conclusiva induzida, verificou alocação liberada, ausência de autorização, projeção restaurada, reserva em `FALHA_CONFIRMACAO` e SAGA `COMPENSADA`. Após reiniciar as oito aplicações, a consulta confirmou os registros e o replay idempotente da entrada nos mesmos bancos.
- **Interfaces.** A execução em Chromium confirmou busca com resultado, fila e estoque, aceite no painel, consulta e registro de retirada. [Captura do portal](assets/portal-cidadao.png) · [Captura do painel](assets/painel-unidade.png)
- **Compose integrado.** [`scripts/validar-compose.ps1`](../scripts/validar-compose.ps1) contém a sequência de instalação a partir do zero, testes HTTP, comandos SQL de verificação, falha provocada e recriação de contêineres. O [script de demonstração manual](../scripts/demo-local.ps1) também sobe infraestrutura e inicia processos Python. Os dois arquivos passaram em `docker compose config --quiet` com ambiente gerado do zero. A execução do roteiro via Docker, incluindo os builds, volumes e redes do Compose e a imagem RabbitMQ 4, ficou indisponível porque o daemon não estava ativo neste ambiente.

## Matriz de atendimento aos requisitos

As classificações da Etapa 2 se referem ao projeto no congelamento de outubro. Para as Etapas 3 e 4, a coluna de evidência informa quando o artefato apareceu e o que esteve disponível para verificação. **Implementado** indica código ou material entregue no repositório. Resultados de execução têm evidência própria na seção [Testes e evidências](#testes-e-evidências).

| Etapa | Requisito do professor | Status | Implementação no projeto | Evidência |
| --- | --- | --- | --- | --- |
| 1 | Nome e identidade da startup | Implementado | Marca, frase de apresentação e duas imagens do logotipo. | [Identidade e pitch de setembro](https://github.com/ArthurDp78/GlicoAcesso/tree/422b9ce) |
| 1 | Problema e motivação com quatro referências ou mais | Implementado | Pesquisa, publicação institucional e base legal embasam a proposta. Uma citação foi corrigida depois. | [Fundamentação](#fundamentação-do-problema) |
| 1 | Público beneficiado | Implementado | Cidadãos, familiares, cuidadores e rede local participante. | [Concepção](parte-1-concepcao-e-pitch.md) |
| 1 | Impacto e indicadores | Documentado/projetado | Indicadores de acesso e organização propostos para avaliação. | [Escopo e impacto esperado](#escopo-e-impacto-esperado) |
| 1 | Esboço da solução | Documentado/projetado | Consulta, análise, reserva, atendimento presencial e atualização de dados. | [Pitch de setembro](https://github.com/ArthurDp78/GlicoAcesso/blob/422b9ce/docs/parte-1-concepcao-e-pitch.md) |
| 1 | Repositório público e README inicial | Implementado | README inicial e revisão no dia da apresentação. | [Primeiro commit](https://github.com/ArthurDp78/GlicoAcesso/commit/60e5032) · [README em setembro](https://github.com/ArthurDp78/GlicoAcesso/blob/422b9ce/README.md) |
| 1 | Quatro integrantes e contribuições | Implementado | Integrantes listados e contribuições rastreáveis por Git. | [Histórico de evolução e contribuições](#histórico-de-evolução-e-contribuições) |
| 2 | Pelo menos quatro domínios, fronteiras e responsabilidades | Documentado/projetado | Unidades, Estoque, Reservas e Retiradas no congelamento. | [Desenho de outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/01-microsservicos.md) |
| 2 | Diagramas de componentes e comunicação | Documentado/projetado | Gateway, BFFs, domínios, REST, RabbitMQ e bancos. | [Diagrama de outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/02-diagrama-arquitetura.md) |
| 2 | Contratos REST, verbos e códigos | Documentado/projetado | Seis arquivos OpenAPI e comandos de domínio. A configuração física permaneceu em aberto. | [OpenAPI congelado](https://github.com/ArthurDp78/GlicoAcesso/tree/b059d68/docs/parte-2/api) |
| 2 | Estratégia de versionamento e HATEOAS | Documentado/projetado | Prefixos v1 e links do recurso Reserva por estado e papel. | [HATEOAS congelado](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/07-hateoas.md) |
| 2 | Gateway, funções e roteamento | Documentado/projetado | Entrada por público, segregação de caminhos internos e autenticação na borda. | [Gateway congelado](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/03-api-gateway.md) |
| 2 | Dois BFFs, justificativa e diferença de respostas | Documentado/projetado | Visão de disponibilidade pública e visão operacional da unidade, com campos e links próprios. | [BFFs congelados](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/04-bffs.md) |
| 2 | Banco por serviço e justificativa | Documentado/projetado | Quatro PostgreSQL previstos, com transações e isolamento dos domínios. | [Banco por serviço em outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/09-bancos.md) |
| 2 | Consistência eventual, dual write e Transactional Outbox | Documentado/projetado | Commit local, publicação posterior e deduplicação. | [PR #4](https://github.com/ArthurDp78/GlicoAcesso/pull/4) |
| 2 | SAGA de três domínios, escolha e justificativa | Documentado/projetado | Reservas coordena Estoque e Retiradas no desenho de outubro. | [PR #2](https://github.com/ArthurDp78/GlicoAcesso/pull/2) |
| 2 | Compensações, caminho feliz e falha | Documentado/projetado | Ordem inversa, idempotência e diagramas de sequência. Ajustes Mermaid entraram em 22/10. | [SAGA e compensações](#saga-e-compensações) |
| 2 | CQRS, modelos, atualização e defasagem | Documentado/projetado | Saldo e projeção em tabelas distintas, atualização via broker, meta aproximada de 5 s. | [CQRS congelado](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/12-cqrs.md) |
| 3 | Dockerfile por serviço e multi-stage | Implementado | Oito Dockerfiles posteriores à apresentação. | [Commit de 24/11](https://github.com/ArthurDp78/GlicoAcesso/commit/8b265b7) |
| 3 | Volumes e redes isoladas | Implementado | Cinco volumes de bancos, um do broker e redes por camada. | [Compose de 24/11](https://github.com/ArthurDp78/GlicoAcesso/commit/3cf7772) |
| 3 | Compose com um único comando para a aplicação | Implementado | `docker compose up --build -d --wait` após configuração. | [Executar do zero](#executar-do-zero) |
| 3 | Vídeo de até dez minutos com quatro integrantes | Não identificado | Nenhum vídeo ou link nos materiais versionados conhecidos. | [Corte da apresentação](https://github.com/ArthurDp78/GlicoAcesso/tree/1ca8bef) |
| 3 | Demonstração funcional na entrega | Implementado parcialmente | Roteiro de validação e interfaces posteriores a 17/11. Execução na apresentação sem evidência versionada. | [Testes e evidências](#testes-e-evidências) |
| 4 | Fluxo ponta a ponta por Gateway, BFF e domínios | Implementado | Busca, reserva, confirmação, retirada e cancelamento atravessam a borda. | [Fluxos implementados](#fluxos-implementados) |
| 4 | Caminho feliz da SAGA | Implementado | Executor durável aloca, prepara autorização e confirma. | [Executor](../servicos/orquestrador/executor.py) |
| 4 | Falha da SAGA com compensação efetiva | Implementado | Recusa de autorização aciona liberação e grava falha. Há cenário automatizado específico. | [Teste de compensação](https://github.com/ArthurDp78/GlicoAcesso/commit/b4c2130) |
| 4 | Escrita refletida na leitura CQRS | Implementado | Entrada, alocação, configuração e entrega repercutem na projeção. | [Eventos de estoque](../servicos/estoque/eventos.py) |
| 4 | Bancos separados | Implementado | Instância PostgreSQL e volume por serviço persistente. | [Topologia Compose](#topologia-compose) |
| 4 | LLM e utilidade no domínio | Não identificado | Não há seleção de modelo ou funcionalidade de IA versionada no corte. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| 4 | Base própria, ingestão, embeddings, banco vetorial, recuperação e geração | Não identificado | Os dados operacionais SQL pertencem a Estoque e demais domínios. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| 4 | Cinco perguntas e avaliação com/sem recuperação | Não identificado | Ausência de conjunto de avaliação e comparação. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| 4 | LangChain, chain e tool de dados reais | Não identificado | Ausência de implementação e dependência. | [Dependências](../pyproject.toml) |
| 4 | Agente acompanhado de justificativa, se usado | Não aplicável | Nenhum agente no corte. Requisito condicional. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| 4 | Dois mecanismos de resiliência de IA | Não identificado | Timeouts, retries e compensações atuais pertencem ao domínio operacional. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| 4 | Latência, custo por operação e projeção de escala | Não identificado | Não há medições ou estimativas de IA versionadas. | [IA e avaliação](#inteligência-artificial-e-avaliação) |
| Geral | Repositório público e único, README e /docs | Implementado | Um repositório público de referência com README, decisões, diagramas e contratos. | [Repositório](https://github.com/ArthurDp78/GlicoAcesso) · [README](../README.md) |
| Geral | Quatro autores, configuração de autoria e coautoria | Implementado | Commits dos quatro integrantes, variantes de nome e trailers de coautoria em commits de novembro. | [Histórico de evolução e contribuições](#histórico-de-evolução-e-contribuições) |
| Geral | Desenvolvimento em branches e histórico distribuído | Implementado | Marcos em setembro, outubro e novembro e branches com merges. Uma frente de backend ainda não integrada. | [Histórico de evolução e contribuições](#histórico-de-evolução-e-contribuições) |
| Geral | Pull requests e revisões | Implementado parcialmente | Quatro PRs integrados e revisões de conteúdo registradas em commits. Reviews formais e discussões nesses PRs não apareceram na consulta ao GitHub. | [Pull requests](https://github.com/ArthurDp78/GlicoAcesso/pulls?q=is%3Apr) |
| Geral | Execução por terceiro a partir do zero | Implementado | Instruções, Compose, modelo de variáveis e script isolado disponíveis. | [Executar do zero](#executar-do-zero) |
| Geral | Incorporação de correções do professor | Não identificado | Ajustes arquiteturais e de contratos são rastreáveis. O histórico não registra quais corresponderam a pareceres do professor. | [PR #3](https://github.com/ArthurDp78/GlicoAcesso/pull/3) · [Revisão de novembro](https://github.com/ArthurDp78/GlicoAcesso/commit/3ecb975) |
| Geral | Demonstração funcional dos padrões | Implementado parcialmente | Fluxos distribuídos validados em processos locais. Execução via Compose e demonstração de IA permanecem pendentes na auditoria. | [Testes e evidências](#testes-e-evidências) |

## Histórico de evolução e contribuições

| Data | Mudança verificável | Evidência |
| --- | --- | --- |
| 07 a 17/09 | Início do repositório, fundamentação, revisão de pitch e README, marca e primeiros domínios. | [Histórico até 17/09](https://github.com/ArthurDp78/GlicoAcesso/compare/60e5032...422b9ce) |
| 09 a 21/10 | Arquitetura, Gateway, BFFs, contratos, HATEOAS, sequência SAGA, persistência, Outbox e CQRS. | [PR #1](https://github.com/ArthurDp78/GlicoAcesso/pull/1) · [PR #2](https://github.com/ArthurDp78/GlicoAcesso/pull/2) · [PR #3](https://github.com/ArthurDp78/GlicoAcesso/pull/3) · [PR #4](https://github.com/ArthurDp78/GlicoAcesso/pull/4) |
| 22/10 | Ajustes de sintaxe dos diagramas de sucesso e compensação após o congelamento. | [Diff](https://github.com/ArthurDp78/GlicoAcesso/compare/b059d68...1ca8bef) |
| 24/11 | Orquestrador separado, quinto banco, portais e serviços, catálogo, cadastro via CLI, projeção e Compose. | [Revisão](https://github.com/ArthurDp78/GlicoAcesso/commit/fc72d2c) · [Portal cidadão](https://github.com/ArthurDp78/GlicoAcesso/commit/999869a) · [Infraestrutura](https://github.com/ArthurDp78/GlicoAcesso/commit/3cf7772) |
| 25/11 | Retirada assíncrona, cancelamento durável, limites de prazo e correções de idempotência e vínculo. Teste de compensação no Compose. | [Domínio](https://github.com/ArthurDp78/GlicoAcesso/commit/8f4c8f7) · [Prazo](https://github.com/ArthurDp78/GlicoAcesso/commit/01d9fcc) · [Vínculo](https://github.com/ArthurDp78/GlicoAcesso/commit/015ccff) · [Compensação](https://github.com/ArthurDp78/GlicoAcesso/commit/b4c2130) |

| Integrante | Contribuições com evidência |
| --- | --- |
| Marcos Vinícius Pereira | Fundamentação inicial e decisões arquiteturais dos microsserviços e do Gateway. [Fundamentação](https://github.com/ArthurDp78/GlicoAcesso/commit/d615242) · [PR #1](https://github.com/ArthurDp78/GlicoAcesso/pull/1) |
| Arthur Soares Marques | Repositório e README iniciais, especificação e diagramas da SAGA, integração das frentes em PRs e correções de diagramas. [README](https://github.com/ArthurDp78/GlicoAcesso/commit/289df4a) · [SAGA](https://github.com/ArthurDp78/GlicoAcesso/commit/1dc99b8) · [Correção](https://github.com/ArthurDp78/GlicoAcesso/commit/1ca8bef) |
| Lana da Silva Miranda | Marca e concepção, persistência, consistência, Outbox e CQRS, correções de contratos e trabalho posterior na branch `feat/backend-microsservicos`. [Identidade](https://github.com/ArthurDp78/GlicoAcesso/commit/fb75f21) · [PR #4](https://github.com/ArthurDp78/GlicoAcesso/pull/4) · [Branch](https://github.com/ArthurDp78/GlicoAcesso/tree/feat/backend-microsservicos) |
| Guilherme Lirio Miranda | Contratos dos BFFs e HATEOAS em outubro, revisão e código da arquitetura executável, Compose e integração de novembro. [HATEOAS](https://github.com/ArthurDp78/GlicoAcesso/commit/992a544) · [Contratos](https://github.com/ArthurDp78/GlicoAcesso/commit/351129f) · [Compose](https://github.com/ArthurDp78/GlicoAcesso/commit/3cf7772) |

O Git registra variantes como `Arthur Soares` e `ArthurDp78`, e `Guilherme`, `Guilherme Lirio` e `Guilherme Lirio Miranda`. Quatro commits de implementação registram trailers de coautoria. Não há tags no conjunto de referências consultado. `feat/fase-3` está contida na `main`. `feat/backend-microsservicos` contém trabalho de backend, contratos e testes que o snapshot principal não incorpora. Os PRs #1 a #4 têm merge no histórico. A consulta de reviews e de discussão desses PRs retornou listas vazias, de modo que a evidência de revisão disponível vem de diffs, mensagens e correções. Os hashes das oito branches remotas conferem com as referências locais examinadas. [Frentes no GitHub](https://github.com/ArthurDp78/GlicoAcesso/branches)

## Pendências e limitações

- **Entrega e IA.** Localizar a evidência da apresentação de 17/11 e do vídeo, se estiverem fora do repositório. Para dezembro, ainda falta material executável de IA, RAG, LangChain, resiliência e avaliação de qualidade, desempenho e custos.
- **README e materiais históricos.** A seção atual de execução aponta corretamente para oito aplicações. O trecho sobre “base executável” de dois processos registra uma fase inicial do desenvolvimento. Os diagramas de outubro colocam a SAGA em Reservas. A revisão de novembro e o código explicitam a mudança do coordenador e o quinto banco. [README](../README.md#demonstração-com-serviços-python-no-windows) · [Projeto de outubro](https://github.com/ArthurDp78/GlicoAcesso/blob/b059d68/docs/parte-2/06-saga.md)
- **Exemplos desatualizados dos BFFs.** O documento 04 ilustra nome do item, endereço e orientações dentro do detalhe de reserva do cidadão, e orientações e saldo no detalhe profissional. No código, o cidadão obtém endereço e orientações em `GET /explorar`. O detalhe da unidade pode acrescentar nome de item e autorização. O saldo vem de `GET /painel/estoque`. A troca BFF–Reservas usa a credencial do ator, e a assinatura delegada é usada na ida ao Orquestrador. [Documento 04](parte-2/04-bffs.md) · [BFF Cidadão](../servicos/bff_cidadao/main.py) · [BFF Unidade](../servicos/bff_unidade/main.py)
- **Cobertura dos contratos.** Os sete YAMLs e os handlers correspondem em método e caminho nas 59 operações de negócio do catálogo. Códigos genéricos de falha da borda e validação em algumas consultas públicas estão incompletos. A especificação do Gateway produzida pelo framework descreve o proxy, de modo que schemas de domínio continuam nos BFFs e serviços. [Contratos](parte-2/api/) · [Tratamento de falhas HTTP](../servicos/http.py)
- **Interface e automação operacional.** A API profissional já expõe alteração de cadastro, horários, situação, prazo e ajustes, enquanto o painel visível oferece a fila, consulta e retirada, entrada de estoque e permissão de reserva. A `main` não traz automação de reconstrução da projeção, integração de estoque externo ou rotinas de reprocessamento administrativo das filas de erro. [Painel](../servicos/gateway/portal/unidade.html) · [Rotas](../servicos/bff_unidade/main.py)
- **Recuperação.** A compensação pode permanecer pendente se um participante não confirmar o comando. O código usa retries, mas faltam procedimento operacional de intervenção, alarmes e evidência de recuperação sob falhas prolongadas. O health check de cada API oferece alcance de processo. O estado de domínio e a projeção exigem verificação adicional.
- **Transição para piloto.** Identidade individual, gestão de perfis e credenciais, operação segura, requisitos locais e origem verificável do estoque precisam ser avaliados antes de implantação com dados reais. Os indicadores sociais são metas de observação. Permanecem sem resultados medidos.

## Referências

### Materiais do projeto

- [Repositório público e README](https://github.com/ArthurDp78/GlicoAcesso) · [Estado de 25/11](https://github.com/ArthurDp78/GlicoAcesso/tree/9d18a62)
- [Concepção e pitch](parte-1-concepcao-e-pitch.md) · [Decisões arquiteturais compartilhadas](parte-2/00-decisoes-compartilhadas.md) · [Resumo arquitetural](parte-2/resumo-arquitetura.md)
- [Contratos OpenAPI](parte-2/api/) · [Diagramas originais](parte-2/diagramas/) · [Licença MIT](../LICENSE)

### Referências científicas, institucionais e legais

- International Diabetes Federation. *IDF Diabetes Atlas*, estimativas nacionais para o Brasil em 2024. [Relatório de país](https://idf.org/our-network/regions-and-members/south-and-central-america/members/brazil/)
- Leal, Galvão e Roncalli. Acesso a medicamentos para o tratamento de hipertensão arterial sistêmica e diabetes mellitus tipo 2 na população brasileira. *Cadernos de Saúde Pública*, 2024. [Artigo e DOI 10.1590/0102-311XPT241022](https://www.scielo.br/j/csp/a/cfqPFJcpwpWPGCtsgVWdKWm/abstract/?lang=pt)
- Nascimento, R. C. R. M. et al. Disponibilidade de medicamentos essenciais na atenção primária do Sistema Único de Saúde. *Revista de Saúde Pública*, 2017. [DOI](https://doi.org/10.11606/S1518-8787.2017051007062)
- Ministério da Saúde. Insulinas humanas e agulhas para caneta. [Página institucional](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas)
- Brasil. Lei nº 14.654, de 23 de agosto de 2023. Publicidade dos estoques das farmácias públicas do SUS. [Texto no Senado Federal](https://legis.senado.leg.br/norma/37511268/publicacao/37513960)
- Meiners, M. M. M. A. et al. Acesso e adesão a medicamentos entre pessoas com diabetes no Brasil. *Revista Brasileira de Epidemiologia*, 2017. [DOI](https://doi.org/10.1590/1980-5497201700030008)
- Ministério da Saúde. Programa Farmácia Popular do Brasil. Lista de medicamentos e insumos que fundamenta a inclusão do recorte de diabetes. [Elenco oficial](https://www.gov.br/saude/pt-br/composicao/sectics/farmacia-popular/arquivos/lista-de-medicamentos-e-insumos-pfpb.pdf/view)
