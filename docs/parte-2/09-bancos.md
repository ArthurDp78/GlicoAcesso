# GlicoAcesso - Database per Service

**Etapa:** 2 — Arquitetura\
**Responsável:** Lana\
**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fronteiras dos serviços](./01-microsservicos.md), [fluxo de reservas](./05-fluxo-reservas.md) e [SAGA](./06-saga.md).

## 1. Tecnologia e isolamento

Os quatro microsserviços de domínio e o Orquestrador da SAGA têm cinco instâncias PostgreSQL independentes. Cada serviço acessa apenas sua instância. PostgreSQL permite proteger dados relacionais e resultados idempotentes com transações locais, constraints e controle de concorrência. O Orquestrador usa essas mesmas garantias para persistir e retomar execuções.

Não existem JOINs, consultas diretas, FKs ou transações ACID entre bancos de serviços diferentes. Identificadores externos são referências opacas; validações entre serviços acontecem pelas APIs e pelos fatos de integração já definidos no documento 00.

| Banco / fonte canônica | Tabelas de domínio e operação |
|---|---|
| Unidades: cadastro e atendimento | `unidades`, `contatos_unidade`, `horarios_unidade`, `idempotencia_comandos` |
| Estoque: catálogo, saldo e alocações | `itens`, `saldos`, `alocacoes`, `movimentacoes`, `idempotencia_comandos`, `inbox`, `outbox`, `disponibilidade` |
| Reservas: solicitação e histórico | `reservas`, `historico_reserva`, `idempotencia_comandos`, `inbox` |
| Retiradas: autorização e entrega física | `autorizacoes`, `retiradas`, `idempotencia_comandos`, `outbox` |
| Orquestrador: coordenação da SAGA | `saga_execucoes`, `saga_etapas`, `saga_pedidos_cancelamento`, `idempotencia_comandos`, `inbox` |

Este documento modela a persistência de domínio e as estruturas necessárias para idempotência. Inbox, Outbox e a projeção CQRS são detalhadas nos documentos 10, 11 e 12; sua implementação mantém as mesmas garantias locais descritas aqui.

### Registro de idempotência dos comandos

Cada serviço mantém em seu próprio banco `idempotencia_comandos`, com `operacao text`, `principalId text`, `idempotencyKey text`, `requestHash text`, `httpStatus integer`, `responseBody jsonb` e `createdAt timestamptz`, todos obrigatórios. A chave primária é `(operacao, principalId, idempotencyKey)`. O resultado HTTP conclusivo e o efeito de domínio são confirmados na mesma transação local. O Orquestrador registra o resultado da recepção do pedido junto da execução ou do pedido de cancelamento durável. Também persiste a chave de cada comando de etapa antes do envio. Os participantes guardam o resultado para repetição idempotente. O conteúdo sensível da resposta segue os controles de acesso e retenção do recurso correspondente.

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
| `horarios_unidade` | `unidadeId uuid`; `diaSemana smallint`; `horarioInicial`, `horarioFinal time`; `legado boolean`. Todos obrigatórios. Cada linha representa um intervalo de atendimento. | PK composta `(unidadeId, diaSemana, horarioInicial, horarioFinal)`; FK `unidadeId → unidades.unidadeId`. |

O endereço fica diretamente em `unidades`, sem tabela própria e sem `complemento`. `numero` e `cep` são textos para preservar sua representação. Contatos e horários ficam em relações 1:N, permitindo vários contatos e intervalos para a mesma unidade.

### Integridade e compatibilidade

- `CHECK (prazoAnaliseHoras > 0)`: prazo obrigatório para toda a unidade. Ele corresponde ao campo de mesmo nome da consulta interna; `prazoAnalise` é a denominação conceitual do documento 00.
- `ativa` tem `DEFAULT true`: a unidade cadastrada já entra operacional. A saída de participação usa `ativa = false`, preservando o cadastro e as referências históricas mantidas por outros serviços.
- `diaSemana` usa 1 a 7, de segunda-feira a domingo, com `CHECK` desse intervalo. As PKs dos detalhes impedem contatos e intervalos exatamente duplicados.
- Em `horarios_unidade`, `CHECK (horarioInicial < horarioFinal)` impede duração nula, inversão e passagem pela meia-noite (`24:00` também é recusado). `EXCLUDE` por unidade e dia impede sobreposição, com períodos semiabertos `[inicial, final)`, que permitem consecutivos. Usa a extensão `btree_gist`.
- Períodos anteriores às regras que as violem são preservados e marcados com `legado boolean` (padrão `false`), fora das duas constraints. Deixam de existir quando os horários da unidade são substituídos por um conjunto válido.
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

Referências externas sem FK: `unidadeId → Unidades`; `reservaId → Reservas`; `sagaId → Orquestrador`; `retiradaId → Retiradas`; `atorId → identidade externa`. O vínculo de `itemId` é interno a Estoque, inclusive por meio da FK composta para `saldos`.

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
| `historico_reserva` | `historicoId`, `reservaId uuid`; `statusPosterior text`; `ocorridoEm timestamptz`, obrigatórios. `statusAnterior`, `atorId`, `justificativa`, `motivo text`; `sagaId`, `eventId`, `retiradaId uuid`, opcionais quando não aplicáveis. | PK `historicoId`; FK `reservaId → reservas.reservaId`. |

`historico_reserva` preserva as transições, os atores, a justificativa de cancelamento profissional e as referências à retirada ou à execução quando aplicável. `sagaId` é uma referência externa ao Orquestrador. `retiradaId` referencia Retiradas e `eventId` identifica o fato consumido. Essas referências não têm FK entre bancos.

### Estados e transações locais

`reservas.status` e os estados do histórico usam o conjunto do documento 00: `SOLICITADA`, `EM_CONFIRMACAO`, `CONFIRMADA`, `CANCELAMENTO_EM_ANDAMENTO`, `CANCELADA`, `REJEITADA`, `EXPIRADA`, `FALHA_CONFIRMACAO` e `RETIRADA`. O estado anterior do histórico é nulo no registro inicial.

- `quantidade > 0`, `prazoAnaliseHoras > 0` e `decisaoAte = criadaEm + prazoAnaliseHoras` em horas. A reserva preserva o prazo aplicado na criação.
- `decisao` admite `ACEITAR` ou `REJEITAR` e é gravada com ator e instante. Expiração só atua em `SOLICITADA`.
- Reservas registra cada transição, a auditoria e o resultado idempotente do comando na mesma transação local. Atualização condicional ou bloqueio da linha protege a máquina de estados. A gravação de `CONFIRMADA` é o ponto de compromisso.
- No evento de retirada, Reservas deduplica na Inbox e grava `RETIRADA` e a auditoria na mesma transação local. O encerramento técnico do cancelamento ocorre no banco do Orquestrador.

Referências externas adicionais sem FK: `unidadeId → Unidades`, `itemId → Estoque` e identificadores de ator para o provedor de identidade.

### Índices necessários

- `reservas(unidadeId, status, criadaEm)` para a fila de análise da unidade.
- `reservas(cidadaoId, criadaEm)` para acompanhamento das próprias solicitações.
- Índice parcial em `reservas(decisaoAte)` para `SOLICITADA`, para expiração.
- `historico_reserva(reservaId, ocorridoEm)` para auditoria da reserva.

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

Referências externas sem FK em `autorizacoes`: `reservaId → Reservas`, `sagaId → Orquestrador`, `unidadeId → Unidades`, `itemId → Estoque`. Em `retiradas`, `atorId` referencia a identidade externa; `correlationId` é correlação, não relacionamento de domínio. A retirada obtém os identificadores do conteúdo entregue pela FK interna para sua autorização.

As PKs e os UNIQUE atendem às consultas por autorização e reserva e à detecção de entrega anterior. Não há consulta adicional definida que justifique outro índice neste banco.

## 6. Banco do Orquestrador

O Orquestrador grava suas execuções e os comandos recuperáveis em PostgreSQL próprio. `reservaId` é uma referência externa sem FK para Reservas. Os vínculos entre uma execução e suas etapas são FKs locais.

| Tabela | Campos e uso | Chaves e vínculos locais |
|---|---|---|
| `saga_execucoes` | `sagaId`, `reservaId`, `correlationId uuid`; `tipo`, `estado text`; `versao bigint`; `createdAt`, `updatedAt timestamptz`. Quando aplicável, `etapaAtual`, `encerradaEm`, `motivoEncerramento`, `resultado`, `eventId` e `retiradaId`. | PK `sagaId`. Índice único parcial por `reservaId` nos estados ativos. |
| `saga_etapas` | `sagaId uuid`; `etapaId`, `operacao`, `destino`, `idempotencyKey`, `estadoTecnico text`; `dadosComando jsonb`; `tentativas integer` não negativo; `createdAt`, `updatedAt timestamptz`. Conforme o progresso, `ultimaTentativaEm`, `proximoRetryEm`, `resultado jsonb` e `erroTecnico` sanitizado. | PK `(sagaId, etapaId)`. FK para `saga_execucoes`. Cada etapa lógica tem chave própria e todas as suas repetições a reutilizam. |
| `saga_pedidos_cancelamento` | `sagaIdSolicitado`, `reservaId`, `correlationId uuid`; referência opcional à confirmação ativa; contexto mínimo do ator e justificativa quando exigida; instante do pedido, fase de admissão e resultado quando conhecido. Se houver transição a recuperar antes da ativação, referencia a intenção persistida na execução ativa. | PK `sagaIdSolicitado`. A confirmação vinculada, se presente, referencia uma execução local. O pedido não conta como execução ativa. |
| `inbox` | Deduplicação por consumidor e `eventId` da entrega concluída. | PK `(consumer, eventId)`. O efeito de reconciliação é persistido na mesma transação local. |

### Estados, exclusão e retomada

- `tipo` distingue `CONFIRMACAO` e `CANCELAMENTO`. Os estados ativos são `EM_EXECUCAO`, `COMPENSANDO`, `COMPENSACAO_PENDENTE`, `CANCELANDO` e `CANCELAMENTO_PENDENTE`. Os terminais são `INTERROMPIDA`, `CONCLUIDA`, `COMPENSADA` e `CANCELADA`. O índice único parcial impede duas execuções ativas para a mesma reserva.
- O controle transacional e a versão serializam a seleção de trabalho e o avanço por reserva. Uma réplica que perde a posse não registra uma nova etapa. Outra réplica pode recuperar e repetir a intenção persistida usando a chave e o conteúdo originais.
- Se o cancelamento puder substituir a confirmação, a intenção de consultar ou solicitar a transição em Reservas fica registrada antes da chamada. Enquanto o resultado da transição estiver incerto, a recuperação repete a mesma intenção. Se Reservas aceitar, uma transação do Orquestrador encerra a confirmação como `INTERROMPIDA`, ativa a execução de cancelamento com o novo `sagaId` e preserva os efeitos conhecidos a reverter. Em caso de recusa conclusiva, o pedido é encerrado e a confirmação pode prosseguir.
- Depois de cada chamada, a resposta conclusiva é persistida antes de selecionar novo trabalho. Após reinício, recuperam-se as execuções ativas e os pedidos pendentes com suas etapas e intenções. Índices por `reservaId` e pelo próximo instante de retry atendem à auditoria e à retomada.
- Se Retiradas confirmar que a entrega venceu, o Orquestrador preserva a evidência disponível e encerra o cancelamento como `INTERROMPIDA`. A Inbox pode reconciliar esse desfecho. A liberação de alocação depende do resultado durável da revogação em Retiradas ou de confirmação de que a autorização nunca existiu.

O registro armazena identificadores e dados mínimos para repetir a operação. Credenciais e tokens ficam fora das intenções, respostas e erros persistidos. Os detalhes de mensagens e projeção estão em [11 - Outbox e Inbox](./11-outbox.md) e [12 - CQRS](./12-cqrs.md).
