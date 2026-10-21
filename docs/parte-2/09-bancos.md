# GlicoAcesso - Database per Service

**Etapa:** 2 — Arquitetura  
**Responsável:** Lana  
**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fronteiras dos serviços](./01-microsservicos.md), [fluxo de reservas](./05-fluxo-reservas.md) e [SAGA](./06-saga.md).

## 1. Tecnologia e isolamento

Cada microsserviço possui um banco PostgreSQL próprio e é o único responsável por acessá-lo. Os quatro domínios têm dados relacionais e precisam de transações locais, constraints e controle de concorrência. Persistência poliglota acrescentaria complexidade sem benefício claro para este escopo.

Não existem JOINs, consultas diretas, FKs ou transações ACID entre bancos de serviços diferentes. Identificadores externos são referências opacas; validações entre serviços acontecem pelas APIs e pelos fatos de integração já definidos no documento 00.

| Banco / fonte canônica | Tabelas de domínio e operação |
|---|---|
| Unidades: cadastro e atendimento | `unidades`, `contatos_unidade`, `horarios_unidade`, `idempotencia_comandos` |
| Estoque: catálogo, saldo e alocações | `itens`, `saldos`, `alocacoes`, `movimentacoes`, `idempotencia_comandos` |
| Reservas: solicitação e orquestração | `reservas`, `saga_execucoes`, `saga_etapas`, `historico_reserva`, `idempotencia_comandos` |
| Retiradas: autorização e entrega física | `autorizacoes`, `retiradas`, `idempotencia_comandos` |

Este documento modela a persistência de domínio e as estruturas necessárias para idempotência. Inbox, Outbox e a projeção CQRS são detalhadas nos documentos 10, 11 e 12; sua implementação mantém as mesmas garantias locais descritas aqui.

### Registro de idempotência dos comandos

Cada serviço mantém em seu próprio banco `idempotencia_comandos`, com `operacao text`, `principalId text`, `idempotencyKey text`, `requestHash text`, `httpStatus integer`, `responseBody jsonb` e `createdAt timestamptz`, todos obrigatórios. A chave primária é `(operacao, principalId, idempotencyKey)`. O resultado HTTP conclusivo e o efeito de domínio são confirmados na mesma transação local. Reservas persiste também a chave da etapa da SAGA antes do envio; participantes guardam o resultado para replay. O conteúdo sensível da resposta segue os controles de acesso e retenção do recurso correspondente.

Os campos `idempotencyKey` em `reservas`, `alocacoes` e `autorizacoes` identificam o comando de criação daquele registro. Comandos posteriores, como cancelamento e compensação, têm chaves próprias em `idempotencia_comandos`; não sobrescrevem a chave de criação.

### Convenções

- Identificadores de domínio usam `uuid`; `cidadaoId` e identificadores de atores usam `text`, conforme a identidade estável recebida do provedor.
- Instantes usam `timestamptz`, apresentados pelas APIs em UTC; horários de atendimento usam `time`.
- Quantidades usam inteiros; `estoqueVersion` usa `bigint`. Textos, booleanos e dados técnicos estruturados usam `text`, `boolean` e `jsonb`.
- As tabelas indicam campos obrigatórios e opcionais. PKs e campos obrigatórios recebem `NOT NULL`; valores opcionais usam `NULL`.
- FKs internas preservam o histórico: exclusões de registros referenciados são restringidas, sem cascata que apague fatos de negócio.

## 2. Banco de Unidades

Contrato relacionado: [unidade.yaml](./api/unidade.yaml).

| Tabela | Campos e tipos | PK / FKs internas |
|---|---|---|
| `unidades` | `unidadeId uuid`; `nome`, `logradouro`, `numero`, `bairro`, `cidade`, `estado`, `cep`, `orientacoesRetirada text`; `prazoAnaliseHoras integer`; `ativa boolean`; `createdAt`, `updatedAt timestamptz`. Todos obrigatórios. | PK `unidadeId`. |
| `contatos_unidade` | `unidadeId uuid`; `tipo`, `valor text`. Todos obrigatórios. | PK composta `(unidadeId, tipo, valor)`; FK `unidadeId → unidades.unidadeId`. |
| `horarios_unidade` | `unidadeId uuid`; `diaSemana smallint`; `horarioInicial`, `horarioFinal time`. Todos obrigatórios. Cada linha representa um intervalo de atendimento. | PK composta `(unidadeId, diaSemana, horarioInicial, horarioFinal)`; FK `unidadeId → unidades.unidadeId`. |

O endereço fica diretamente em `unidades`, sem tabela própria e sem `complemento`. `numero` e `cep` são textos para preservar sua representação. Contatos e horários ficam em relações 1:N, permitindo vários contatos e intervalos para a mesma unidade.

### Integridade e compatibilidade

- `CHECK (prazoAnaliseHoras > 0)`: prazo obrigatório para toda a unidade. Ele corresponde ao campo de mesmo nome da consulta interna; `prazoAnalise` é a denominação conceitual do documento 00.
- `ativa` tem `DEFAULT true`: a unidade cadastrada já entra operacional. A saída de participação usa `ativa = false`, preservando o cadastro e as referências históricas mantidas por outros serviços.
- `diaSemana` usa 1 a 7, de segunda-feira a domingo, com `CHECK` desse intervalo. As PKs dos detalhes impedem contatos e intervalos exatamente duplicados.
- `endereco` e `horarioAtendimento`, hoje expostos como textos no OpenAPI, são compostos pela aplicação a partir dos campos e intervalos locais. A organização interna não altera esses nomes ou tipos HTTP.

Este banco não contém referências a outros domínios. Os índices das PKs atendem à consulta por unidade e à carga de seus contatos e horários; não se propõem índices adicionais sem consulta definida.

## 3. Banco de Estoque

Contrato relacionado: [estoque.yaml](./api/estoque.yaml).

| Tabela | Campos e tipos | PK / FKs internas |
|---|---|---|
| `itens` | `itemId uuid`; `nome`, `tipo text`; `createdAt`, `updatedAt timestamptz`, obrigatórios. `descricao text`, opcional. | PK `itemId`. |
| `saldos` | `unidadeId`, `itemId uuid`; `estoqueFisicoAtual`, `quantidadeAlocada integer`; `permiteReserva boolean`; `estoqueVersion bigint`; `createdAt`, `updatedAt timestamptz`. Todos obrigatórios. | PK composta `(unidadeId, itemId)`; FK `itemId → itens.itemId`. |
| `alocacoes` | `alocacaoId`, `reservaId`, `sagaId`, `unidadeId`, `itemId uuid`; `quantidade integer`; `idempotencyKey text`; `correlationId uuid`; `createdAt`, `updatedAt timestamptz`, obrigatórios. `liberadaEm`, `consumidaEm timestamptz`, opcionais. | PK `alocacaoId`; `UNIQUE (reservaId)`; FK composta `(unidadeId, itemId) → saldos`. |
| `movimentacoes` | `movimentacaoId`, `unidadeId`, `itemId uuid`; `variacaoFisica integer`; `ocorridaEm timestamptz`, obrigatórios. `alocacaoId`, `retiradaId uuid`, opcionais conforme a origem; `atorId`, `motivo text`, opcionais quando não aplicáveis. | PK `movimentacaoId`; FK composta `(unidadeId, itemId) → saldos`; FK opcional `alocacaoId → alocacoes.alocacaoId`. |

`itens` separa o cadastro canônico do item de suas quantidades em cada unidade. A API limita `tipo` a `MEDICAMENTO` ou `INSUMO`; o banco pode armazená-lo como `text` com constraint equivalente, sem exigir um tipo ENUM específico do PostgreSQL.

### Saldo, alocação e movimentação

`saldos` é a fonte canônica operacional. A disponibilidade operacional é calculada por `estoqueFisicoAtual - quantidadeAlocada`, sem armazenar uma terceira quantidade redundante nessa tabela. `quantidadeAlocada` permite acesso rápido ao total; `alocacoes` identifica quais reservas compõem esse total e permite liberar o efeito correto da SAGA.

A situação da alocação é representada pelos fatos já previstos no fluxo: está ativa enquanto `liberadaEm` e `consumidaEm` forem nulos; uma liberação preenche o primeiro, e uma retirada preenche o segundo. Isso distingue alocação ativa, liberada e consumida sem fixar nomes de enum ainda ausentes dos contratos. `sagaId` identifica a execução que criou a alocação e permanece preservado quando outra execução solicita seu encerramento.

`movimentacoes` guarda o histórico físico, sem substituir o saldo atual. `variacaoFisica` é assinada: positiva para entrada e negativa para saída; ajustes registram a diferença aplicada. Alocar ou liberar quantidade não constitui movimentação física. Uma movimentação de retirada referencia a alocação consumida e o `retiradaId` externo.

### Integridade e transações locais

- Em `saldos`: `CHECK (estoqueFisicoAtual >= 0)`, `CHECK (quantidadeAlocada >= 0)`, `CHECK (quantidadeAlocada <= estoqueFisicoAtual)` e `CHECK (estoqueVersion >= 0)`.
- Em `alocacoes`: `CHECK (quantidade > 0)`, `UNIQUE (reservaId)` e exclusão entre `liberadaEm` e `consumidaEm`; ambos não podem estar preenchidos. Uma reserva terminal não é reaberta nem realocada; uma nova solicitação recebe novo `reservaId`.
- Em `movimentacoes`: `CHECK (variacaoFisica <> 0)` e `UNIQUE (retiradaId)` para as linhas com esse identificador. Uma baixa de retirada exige `alocacaoId` e variação negativa.
- Criar uma alocação e aumentar `quantidadeAlocada` ocorre na mesma transação local, após validar disponibilidade e permissão no saldo de escrita. Liberar uma alocação reduz apenas a quantidade alocada, na mesma transação de seu encerramento.
- Consumir uma alocação reduz `estoqueFisicoAtual` e `quantidadeAlocada` pela mesma quantidade e grava a movimentação e `consumidaEm`, na mesma transação. Os dados da retirada devem corresponder à reserva, unidade, item e quantidade alocados.
- Cada alteração do agregado de saldo, inclusive sua permissão, incrementa `estoqueVersion` na mesma transação. A versão é monotônica por `(unidadeId, itemId)` e fica reservada ao uso posterior pelo CQRS.
- A aplicação serializa alterações do mesmo saldo por bloqueio da linha ou atualização condicional. Ela mantém `quantidadeAlocada` igual à soma das alocações ativas. Essa igualdade entre tabelas e a correspondência entre movimentação e alocação não são garantidas por um `CHECK` de linha.

Referências externas sem FK: `unidadeId → Unidades`; `reservaId` e `sagaId → Reservas`; `retiradaId → Retiradas`; `atorId → identidade externa`. O vínculo de `itemId` é interno a Estoque, inclusive por meio da FK composta para `saldos`.

### Índices necessários

Além das PKs e da unicidade de `retiradaId`, propõem-se:

- Índice de `alocacoes(reservaId)` para recuperar também registros encerrados da reserva.
- Índice de `movimentacoes(unidadeId, itemId, ocorridaEm)` para consultar o histórico físico de um saldo.

`UNIQUE (reservaId)` vale para todo o histórico. Retries da mesma etapa recuperam a alocação e a resposta originais pelo registro idempotente; uma reserva liberada ou consumida não recebe outra alocação. Uma nova tentativa de negócio cria outra reserva.

## 4. Banco de Reservas

Contrato relacionado: [reserva.yaml](./api/reserva.yaml).

| Tabela | Campos e tipos | PK / FKs internas |
|---|---|---|
| `reservas` | `reservaId`, `unidadeId`, `itemId uuid`; `cidadaoId text`; `quantidade integer`; `status text`; `prazoAnaliseHoras integer`; `criadaEm`, `decisaoAte`, `atualizadaEm timestamptz`; `idempotencyKey text`, obrigatórios. `decisao`, `decisaoAtorId text` e `decididaEm timestamptz`, opcionais até haver decisão. | PK `reservaId`. |
| `saga_execucoes` | `sagaId`, `reservaId uuid`; `tipo`, `estado text`; `correlationId uuid`; `createdAt`, `updatedAt timestamptz`, obrigatórios. `etapaAtual`, `erroTecnico`, `motivoEncerramento text`; `encerradaEm timestamptz`; `eventId`, `retiradaId uuid`, opcionais conforme o progresso e a causa do encerramento. | PK `sagaId`; FK `reservaId → reservas.reservaId`. |
| `saga_etapas` | `sagaId uuid`; `operacao`, `estadoTecnico`, `idempotencyKey text`; `dadosComando jsonb`; `tentativas integer`; `createdAt`, `updatedAt timestamptz`, obrigatórios. `ultimaTentativaEm`, `proximoRetryEm`, `efeitoConfirmadoEm timestamptz`; `resultado jsonb`, `erroTecnico text`, opcionais. | PK composta `(sagaId, operacao)`; FK `sagaId → saga_execucoes.sagaId`. |
| `historico_reserva` | `historicoId`, `reservaId uuid`; `statusPosterior text`; `ocorridoEm timestamptz`, obrigatórios. `statusAnterior`, `atorId`, `justificativa`, `motivo text`; `sagaId`, `eventId`, `retiradaId uuid`, opcionais quando não aplicáveis. | PK `historicoId`; FK `reservaId → reservas.reservaId`; FK opcional `sagaId → saga_execucoes.sagaId`. |

`reservas` representa o negócio; `saga_execucoes` representa a coordenação técnica. Confirmação e cancelamento são execuções distintas da mesma reserva. `saga_etapas` persiste o comando lógico, sua chave, tentativas e evidências necessárias à retomada. Não se cria tabela adicional de tentativas HTTP.

`historico_reserva` modela o histórico de transições e cancelamentos exigido pelo documento 01, seção 7.2, e os registros de auditoria detalhados no documento 05, seção 13. O documento 00, seção 9.3, também exige evidência da retirada e motivo do encerramento quando a entrega vence o cancelamento. Esses documentos exigem a preservação dos dados, sem determinar uma tabela específica; a tabela aqui apresentada atende a esse requisito. O ator vem da identidade autenticada; ações automáticas são identificadas pelo motivo e pela execução ou fato que as originou. Quando o histórico referencia uma SAGA, a aplicação valida que ela pertence à mesma reserva.

### Estados canônicos

`reservas.status` recebe `CHECK` restrito aos valores do documento 00 e do OpenAPI:

`SOLICITADA`, `EM_CONFIRMACAO`, `CONFIRMADA`, `CANCELAMENTO_EM_ANDAMENTO`, `CANCELADA`, `REJEITADA`, `EXPIRADA`, `FALHA_CONFIRMACAO`, `RETIRADA`.

Os estados anterior e posterior do histórico usam o mesmo conjunto, com anterior nulo no registro inicial. `saga_execucoes.estado` recebe `CHECK` com os estados canônicos da execução:

`EM_EXECUCAO`, `COMPENSANDO`, `COMPENSACAO_PENDENTE`, `CANCELANDO`, `CANCELAMENTO_PENDENTE`, `INTERROMPIDA`, `CONCLUIDA`, `COMPENSADA`, `CANCELADA`.

`tipo` distingue `CONFIRMACAO` e `CANCELAMENTO`. `saga_execucoes.estado` usa os estados da máquina descrita no documento 06. `saga_etapas.operacao` identifica os comandos `AlocarEstoque`, `PrepararAutorizacao`, `CancelarAutorizacao` e `LiberarAlocacao`; `etapaAtual` referencia a etapa correspondente. `estadoTecnico` acompanha o envio, a incerteza, a conclusão e a compensação de cada comando. Esse detalhe técnico não cria estados de negócio adicionais para a Reserva nem substitui os estados canônicos da execução.

### Integridade e recuperação

- Em `reservas`: `CHECK (quantidade > 0)`, `CHECK (prazoAnaliseHoras > 0)` e `decisaoAte = criadaEm + prazoAnaliseHoras` em horas. O prazo é uma cópia da configuração aplicada na criação; mudar o cadastro de Unidades não altera o vencimento já registrado.
- `decisao`, quando preenchida, aceita apenas `ACEITAR` ou `REJEITAR`, conforme o comando HTTP, acompanhada de ator e instante. Esses três campos são preenchidos juntos; `REJEITADA` é estado da reserva, não valor do comando.
- `tentativas >= 0` em `saga_etapas`. A PK composta mantém uma linha por operação lógica da execução; retries atualizam essa linha e reutilizam a `Idempotency-Key` armazenada em `idempotencyKey`. Cada operação lógica tem chave própria, além do resultado armazenado pelo participante.
- `dadosComando` preserva os dados necessários para repetir o mesmo comando, inclusive identificadores e quantidade; `resultado` preserva a resposta conclusiva e identificadores de efeitos confirmados. Erros são sanitizados e não armazenam credenciais ou perfis pessoais.
- Um índice UNIQUE parcial em `saga_execucoes(reservaId)` para `EM_EXECUCAO`, `COMPENSANDO`, `COMPENSACAO_PENDENTE`, `CANCELANDO` e `CANCELAMENTO_PENDENTE` garante uma única execução ativa. `INTERROMPIDA` é terminal e fica fora desse índice.
- Aceite, transição para `EM_CONFIRMACAO`, histórico e criação da execução são atômicos no banco de Reservas. A finalização grava `CONFIRMADA`, `CONCLUIDA` e histórico na mesma transação local.
- Se uma confirmação for interrompida para cancelar, seus efeitos e etapas continuam preservados. A execução de cancelamento usa novo `sagaId` depois do encerramento da anterior, conforme o documento 06.
- Quando a retirada vence o cancelamento, a reserva admite `CANCELAMENTO_EM_ANDAMENTO → RETIRADA`; a execução de cancelamento termina em `INTERROMPIDA`, com motivo e evidências. As alterações e a auditoria são atômicas com a deduplicação exigida pelo documento 00. Respostas tardias não podem levar a reserva para `CANCELADA` nem reabrir a execução.
- Transições usam bloqueio ou atualização condicional pelo estado atual. Um `CHECK` de valores não valida sozinho a máquina de estados. Expiração só atua sobre `SOLICITADA`; justificativa é obrigatória no cancelamento profissional, conforme o contrato vigente, e fica no histórico.

Referências externas sem FK: `unidadeId → Unidades`; `itemId → Estoque`; `cidadaoId`, `decisaoAtorId` e `atorId → identidade externa`; `retiradaId → Retiradas`. `eventId` é referência ao fato recebido, sem FK para o produtor. Os `sagaId` usados neste banco possuem os vínculos internos indicados nas tabelas.

### Índices necessários

Além das PKs e dos UNIQUE indicados:

- `reservas(unidadeId, status, criadaEm)` para a fila de análise da unidade.
- `reservas(cidadaoId, criadaEm)` para acompanhamento das próprias solicitações.
- Índice parcial `reservas(decisaoAte)` apenas para `SOLICITADA`, para localizar vencimentos.
- `saga_execucoes(reservaId)` para recuperar também o histórico de execuções encerradas.
- Índice parcial de `saga_execucoes(updatedAt)` nos cinco estados ativos para recuperar a orquestração após reinício.
- `historico_reserva(reservaId, ocorridoEm)` para auditoria da reserva.

A PK de `saga_etapas` permite carregar as etapas da execução. A recuperação lê somente dados locais persistidos; registrar que uma chamada foi enviada não prova seu sucesso. Reservas repete o comando com a mesma `Idempotency-Key` e conteúdo para que o participante devolva a resposta conclusiva gravada com o efeito local. O GET da autorização documentado em `retirada.yaml` serve à agregação operacional, não substitui esse replay.

## 5. Banco de Retiradas

Contrato relacionado: [retirada.yaml](./api/retirada.yaml).

| Tabela | Campos e tipos | PK / FKs internas |
|---|---|---|
| `autorizacoes` | `autorizacaoId`, `reservaId`, `sagaId`, `unidadeId`, `itemId uuid`; `quantidade integer`; `idempotencyKey text`; `correlationId uuid`; `createdAt`, `updatedAt timestamptz`, obrigatórios. `canceladaEm timestamptz`, opcional. | PK `autorizacaoId`; `UNIQUE (reservaId)`. |
| `retiradas` | `retiradaId`, `autorizacaoId uuid`; `realizadaEm timestamptz`; `atorId text`; `correlationId uuid`. Todos obrigatórios. | PK `retiradaId`; FK `autorizacaoId → autorizacoes.autorizacaoId`; `UNIQUE (autorizacaoId)`. |

Uma autorização representa o que foi autorizado durante a SAGA; uma retirada representa a entrega física posterior. Guardar as duas separadamente permite preservar autorizações canceladas e comprovar entregas sem confundir preparação com entrega.

`unidadeId`, `itemId` e `quantidade` são uma cópia local do conteúdo autorizado, junto de `reservaId` e do `sagaId` criador. Esses dados permitem verificar a entrega e preservar o fato autorizado; não transferem a Retiradas a propriedade dos cadastros ou do estoque. São preservados após criação, inclusive quando outra execução cancela a autorização.

A situação local é representada pela autorização criada, por `canceladaEm` e pela existência de uma linha em `retiradas`. Não se fixa enum adicional de autorização. Sua existência, sem cancelamento ou entrega, não comprova que a reserva foi globalmente confirmada.

### Integridade e concorrência

- `CHECK (quantidade > 0)` em `autorizacoes`.
- `UNIQUE (reservaId)` garante uma autorização por reserva, inclusive após cancelamento; preparar novamente não cria uma segunda autorização nem reativa a anterior.
- `UNIQUE (autorizacaoId)` em `retiradas` garante no máximo uma entrega por autorização.
- Para registrar uma nova entrega, Retiradas consulta `GET /internal/v1/reservas/{reservaId}/estado` e só prossegue com o mesmo identificador e `status = CONFIRMADA`. Timeout, indisponibilidade ou estado diferente impedem o registro naquele momento.
- A consulta não bloqueia Reservas. Na transação local, revogação e entrega disputam a mesma linha de autorização: a aplicação a bloqueia e revalida `canceladaEm` e a existência de retirada antes de gravar. Uma autorização cancelada não recebe entrega; uma autorização utilizada não pode ser cancelada. Essa exclusão entre tabelas exige a transação e não é obtida por `CHECK` isolado.
- Se a consulta retornar `CONFIRMADA` e o cancelamento começar depois, mantém-se a corrida local já definida: apenas revogação ou entrega vence. A retirada que vencer impede o cancelamento e é preservada como fato de negócio.
- `atorId` é obtido da identidade autenticada, conforme a exigência dos documentos 00 e 01 de registrar quem realizou a entrega. Não é um campo adicional no corpo HTTP atual, que recebe `autorizacaoId`. `correlationId` é metadado de rastreamento.
- Entrega e registro para publicação são confirmados na mesma transação local, conforme o documento 00; a estrutura técnica será detalhada separadamente.

Referências externas sem FK em `autorizacoes`: `reservaId` e `sagaId → Reservas`, `unidadeId → Unidades`, `itemId → Estoque`. Em `retiradas`, `atorId` referencia a identidade externa; `correlationId` é correlação, não relacionamento de domínio. A retirada obtém os identificadores do conteúdo entregue pela FK interna para sua autorização.

As PKs e os UNIQUE atendem às consultas por autorização e reserva e à detecção de entrega anterior. Não há consulta adicional definida que justifique outro índice neste banco.

## 6. Decisões alinhadas

Os contratos e este modelo definem uma convenção única para idempotência, armazenamento de resultados repetíveis e unicidade histórica da alocação por `reservaId`. Os estados técnicos da SAGA seguem os nomes definidos em 00 e 06; qualquer alteração exige atualizar contratos, banco, diagramas e documentos dependentes no mesmo conjunto de mudanças.

Consistência, Outbox e CQRS estão detalhados em [10](./10-consistencia.md), [11](./11-outbox.md) e [12](./12-cqrs.md). A autorização consultada pelo BFF Unidade é uma projeção operacional, não uma autorização para registrar entrega; o fluxo de entrega permanece protegido pela validação canônica em Reservas.
