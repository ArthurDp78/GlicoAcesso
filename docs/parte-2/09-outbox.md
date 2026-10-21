# GlicoAcesso — Transactional Outbox, Inbox e eventos

**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fluxo de reservas](./03-fluxo-reservas.md), [bancos](./07-bancos.md) e [consistência](./08-consistencia.md).

## 1. Tabelas técnicas por serviço

| Serviço | Inbox | Outbox | Fluxo atual |
|---|---|---|---|
| Unidades | Não | Não | Nenhum evento produzido ou consumido neste escopo. |
| Reservas | `inbox` | Não | Consome `retirada.concluida.v1`. |
| Estoque | `inbox` | `outbox` | Consome a retirada e publica os eventos da projeção CQRS; a projeção também consome esses eventos. |
| Retiradas | Não | `outbox` | Produz `retirada.concluida.v1`. |

Cada tabela fica no PostgreSQL do próprio serviço. A solução usa um worker próprio para consultar a Outbox e publicar no RabbitMQ, com entrega **at-least-once**.

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
3. Somente a confirmação conclusiva do broker para o destino previsto permite marcar `PUBLICADO` e preencher `publishedAt`. Isso confirma publicação, não processamento pelos consumidores.
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

- **Reservas:** Inbox, transição para `RETIRADA`, auditoria e eventual encerramento do cancelamento como `INTERROMPIDA` são atômicos.
- **Estoque:** valida a alocação por reserva, unidade, item e quantidade; grava Inbox, baixa física, consumo da alocação, nova `estoqueVersion` e Outbox de `estoque.retirada-baixada.v1` na mesma transação. Reduz físico e alocado pela mesma quantidade, sem descontar a disponibilidade novamente. Divergências não recebem baixa arbitrária nem são marcadas como processadas com sucesso; permanecem observáveis para reconciliação.
- **Projeção CQRS em Estoque:** Inbox e atualização da projeção são atômicas. Eventos com versão antiga não substituem o estado mais novo; podem ser registrados como tratados sem alterar a projeção.

## 5. Catálogo mínimo de eventos

### Retirada física

| Evento | Produtor → consumidores | Payload obrigatório |
|---|---|---|
| `retirada.concluida.v1` | Retiradas → Reservas e Estoque | `retiradaId`, `reservaId`, `unidadeId`, `itemId` e `quantidade` positiva. |

Retiradas grava entrega, uso da autorização e Outbox atomicamente. O RabbitMQ entrega cópias em **filas duráveis separadas** de Reservas e Estoque: os dois serviços precisam receber o fato. O evento não contém dados pessoais do cidadão.

### Estoque e projeção CQRS

Todos os eventos abaixo são produzidos por Estoque e consumidos pela sua projeção de disponibilidade. Além do envelope, o payload sempre contém `unidadeId`, `itemId`, `estoqueVersion` e o estado resultante completo do saldo: `estoqueFisicoAtual`, `quantidadeAlocada` e `permiteReserva`.

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
