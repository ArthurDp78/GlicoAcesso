# GlicoAcesso - Transactional Outbox, Inbox e eventos

**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fluxo de reservas](./05-fluxo-reservas.md), [bancos](./09-bancos.md) e [consistência](./10-consistencia.md).

## 1. Tabelas técnicas por serviço

| Serviço | Inbox | Outbox | Fluxo atual |
|---|---|---|---|
| Unidades | Não | Não | Nenhum evento produzido ou consumido neste escopo. |
| Reservas | `inbox` | Não | Consome `retirada.concluida.v1`. |
| Estoque | `inbox` | `outbox` | Consome a retirada e publica os eventos da projeção CQRS; a projeção também consome esses eventos. |
| Retiradas | Não | `outbox` | Produz `retirada.concluida.v1`. |
| Orquestrador | `inbox` | Não | Consome `retirada.concluida.v1` para reconciliar cancelamentos. Seus comandos HTTP usam o registro durável de etapas. |

Cada tabela fica no PostgreSQL do próprio serviço. Cada produtor usa um worker para consultar sua Outbox e publicar no RabbitMQ. A entrega é pelo menos uma vez.

## 2. Estrutura mínima da Outbox

Na mesma transação local que altera o domínio, o serviço grava o evento em `outbox`. Se a transação falhar, ambos são desfeitos; após o commit, o evento fica disponível ao worker. Isso evita confirmar a alteração no banco sem preservar a intenção de publicá-la.

| Campo | Tipo e finalidade |
|---|---|
| `eventId` | `uuid`, PK; identidade estável da mensagem, preservada nos retries. |
| `eventType` | `text`; nome do fato conforme o catálogo abaixo. |
| `eventVersion` | `integer`; versão do contrato, `1` para os eventos deste catálogo. |
| `aggregateType`, `aggregateId` | `text`; tipo e identificador estável do agregado de origem. |
| `correlationId` | `uuid`; correlação do fluxo. |
| `causationId` | `uuid`, opcional; identificador do comando ou evento causador, quando disponível. |
| `occurredAt` | `timestamptz`; instante do fato no envelope canônico. |
| `payload` | `jsonb`; conteúdo de negócio capturado na transação de origem. |
| `status` | `text`; `PENDENTE` ou `PUBLICADO`, inicialmente `PENDENTE`. |
| `createdAt` | `timestamptz`; instante de inclusão na Outbox. |
| `publishedAt` | `timestamptz`, inicialmente nulo; instante em que a confirmação de publicação foi registrada. |
| `attempts` | `integer >= 0`, inicialmente zero; tentativas de publicação iniciadas. |
| `nextRetryAt` | `timestamptz`; próxima tentativa elegível, inicialmente `createdAt`. |
| `lastError` | `text`, opcional; último erro sanitizado, sem credenciais ou dados pessoais. |

Os campos são obrigatórios, exceto os indicados como opcionais ou inicialmente nulos. Um índice parcial em `nextRetryAt` para `status = PENDENTE` atende à busca do worker. `PUBLICADO` exige `publishedAt`; um evento pendente não tem esse instante preenchido.

O envelope publicado contém `eventId`, `eventType`, `eventVersion`, `occurredAt`, `aggregateType`, `aggregateId`, `correlationId`, `causationId` e `payload`, conforme o documento 00. `causationId` fica nulo quando indisponível; não se inventa um identificador causal. Os campos de controle da publicação ficam apenas na tabela. Identidade, instante do fato e conteúdo do evento não mudam entre tentativas.

## 3. Fluxo de publicação

1. O worker consulta eventos `PENDENTE` com `nextRetryAt <= agora`, já confirmados pela transação de origem.
2. Registra o início da tentativa em `attempts` e publica o envelope no RabbitMQ.
3. O worker usa publisher confirms e trata mensagens sem rota como falha de publicação. Após confirmação do broker e verificação de que não houve retorno por falta de rota, marca `PUBLICADO` e preenche `publishedAt`. A topologia deve declarar todos os vínculos esperados. A confirmação do broker não comprova processamento por consumidor.
4. Em falha ou timeout, o evento permanece `PENDENTE`, com `lastError` sanitizado e `nextRetryAt` adiado por backoff. Se o worker cair, os registros pendentes continuam recuperáveis.

Se o broker receber o evento e o worker cair antes de marcar a publicação, haverá reenvio com o mesmo `eventId`. Portanto, consumidores precisam ser idempotentes. A publicação pode chegar fora de ordem; a projeção usa `estoqueVersion` para evitar regressão. O registro não é descartado por falha de publicação.

## 4. Inbox e atomicidade do consumo

`inbox` registra eventos processados por consumidor, com apenas três campos obrigatórios:

| Campo | Tipo e finalidade |
|---|---|
| `consumer` | `text`; identidade estável do consumidor lógico, distinguindo a baixa de Estoque da atualização da projeção. |
| `eventId` | `uuid`; identidade recebida no envelope. |
| `processedAt` | `timestamptz`; instante de processamento local. |

A PK composta `(consumer, eventId)` impede reaplicar a mesma mensagem naquele consumidor, inclusive em entregas concorrentes. Na mesma transação local, o consumidor insere a Inbox e aplica os efeitos. Uma duplicata já confirmada não reaplica o efeito; uma falha desfaz tanto os efeitos quanto a inserção. A mensagem só recebe ACK após o commit ou após constatar processamento anterior confirmado. Receber a mensagem, por si só, não significa que foi processada.

- **Reservas:** Inbox, transição para `RETIRADA` quando aplicável e auditoria são atômicas.
- **Orquestrador:** Inbox e o efeito local de reconciliação são atômicos. Se houver execução de cancelamento afetada, registra a evidência da entrega e reconcilia seu encerramento como `INTERROMPIDA`. Se a execução já estiver encerrada, preserva o resultado terminal. A segurança da liberação continua dependendo do resultado durável da revogação em Retiradas.
- **Estoque:** valida a alocação por reserva, unidade, item e quantidade; grava Inbox, baixa física, consumo da alocação, nova `estoqueVersion` e Outbox de `estoque.retirada-baixada.v1` na mesma transação. Reduz físico e alocado pela mesma quantidade, sem descontar a disponibilidade novamente. Divergências não recebem baixa arbitrária nem são marcadas como processadas com sucesso; permanecem observáveis para reconciliação.
- **Projeção CQRS em Estoque:** Inbox e atualização da projeção são atômicas. Eventos com versão antiga não substituem o estado mais novo; podem ser registrados como tratados sem alterar a projeção.

Quando o processamento falhar, o consumidor não confirma sucesso. Falhas transitórias são reprocessadas com backoff. Falhas persistentes ficam observáveis para tratamento e reprocessamento, por fila de erro ou mecanismo operacional equivalente. O reprocessamento preserva o `eventId` e a identidade do consumidor.

## 5. Catálogo mínimo de eventos

### Retirada física

| Evento | Produtor → consumidores | Payload obrigatório |
|---|---|---|
| `retirada.concluida.v1` | Retiradas → Reservas, Estoque e Orquestrador | `retiradaId`, `reservaId`, `unidadeId`, `itemId` e `quantidade` positiva. |

Retiradas grava entrega, uso da autorização e Outbox atomicamente. O RabbitMQ encaminha o evento a três filas duráveis independentes. O evento não contém dados pessoais do cidadão.

| Fila lógica | Consumidor | Efeito local |
|---|---|---|
| Retirada em Reservas | Reservas | Atualiza estado e auditoria da reserva. |
| Retirada em Estoque | Estoque | Baixa o saldo físico e encerra a alocação como consumida. |
| Retirada no Orquestrador | Orquestrador | Reconcilia o cancelamento distribuído. |

### Estoque e projeção CQRS

Todos os eventos abaixo são produzidos por Estoque. A projeção de disponibilidade os consome por fila durável própria, separada da fila de baixa física. Além do envelope, o payload sempre contém `unidadeId`, `itemId`, `estoqueVersion` e o estado resultante completo do saldo: `estoqueFisicoAtual`, `quantidadeAlocada` e `permiteReserva`.

| Evento | Fato que o produz | Campos adicionais do payload |
|---|---|---|
| `estoque.alocacao-criada.v1` | Criação da alocação e aumento da quantidade alocada. | `alocacaoId`, `reservaId`, `quantidade` positiva. |
| `estoque.alocacao-liberada.v1` | Liberação da alocação e redução da quantidade alocada. | `alocacaoId`, `reservaId`, `quantidade` positiva. |
| `estoque.entrada-registrada.v1` | Entrada física registrada no saldo e nas movimentações. | `movimentacaoId`, `variacaoFisica` positiva. |
| `estoque.ajustado.v1` | Ajuste físico registrado no saldo e nas movimentações. | `movimentacaoId`, `variacaoFisica` assinada e diferente de zero. |
| `estoque.retirada-baixada.v1` | Processamento válido da retirada, reduzindo físico e alocado. | `retiradaId`, `reservaId`, `quantidadeBaixada` positiva, preservando o contrato existente. |
| `estoque.permissao-reserva-alterada.v1` | Alteração de `permiteReserva`. | Nenhum além do estado comum. |

O nome `estoque.alocacao-criada.v1` reaproveita o exemplo de envelope do documento 00, em lugar de introduzir `estoque.alocado.v1` para o mesmo fato. Os nomes e payloads já estabelecidos de retirada foram preservados. Uma repetição idempotente sem novo efeito não gera novo evento de negócio.

### Versão e estado resultante

`estoqueVersion` é monotônica por `(unidadeId, itemId)` e incrementada junto da alteração canônica, sob o controle de concorrência local já definido para `saldos`. A Outbox captura a versão e o estado resultante nessa mesma transação; o worker não consulta o saldo novamente para reconstruir o payload.

A projeção só substitui seu estado por uma versão maior para o mesmo par. Assim, duplicatas ou eventos fora de ordem não fazem a leitura regredir. Os campos quantitativos de cada fato preservam seu significado de negócio, mas a projeção aplica o estado resultante completo, sem acumular deltas. `eventVersion` versiona o contrato; `estoqueVersion` ordena mudanças do saldo. O algoritmo completo da projeção fica para o documento de CQRS.


### Propagação executável da retirada

Retiradas publica `retirada.concluida.v1` com confirmação do RabbitMQ. Antes de publicar, declara os três destinos duráveis, `reservas.retirada-concluida`, `estoque.retirada-concluida` e `orquestrador.retirada-concluida`. Cada destino possui uma fila `.erros` própria para mensagens inválidas ou incompatíveis com o estado do domínio.

Reservas grava `RETIRADA` e o histórico na mesma transação da Inbox. Estoque reduz o saldo físico e o alocado, grava a movimentação e publica `estoque.retirada-baixada.v1` pela própria Outbox, preservando a correlação e ligando o evento de origem por `causationId`. O Orquestrador grava a evidência por reserva para reconciliar a disputa com a revogação. O resultado durável de Retiradas continua governando a decisão de liberar estoque.

Os consumidores confirmam a mensagem após o commit. A Inbox impede repetir o efeito do mesmo `eventId`. A reserva, a alocação e a evidência também guardam o identificador da retirada para reconhecer o mesmo fato quando ele chega com outro `eventId`.
