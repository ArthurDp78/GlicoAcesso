# GlicoAcesso - CQRS no serviço Estoque

**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [bancos](./09-bancos.md), [consistência](./10-consistencia.md) e [Outbox e eventos](./11-outbox.md).

## 1. Escopo e escolha arquitetural

CQRS aplica-se somente ao serviço Estoque. Disponibilidade é uma consulta frequente; uma projeção própria simplifica essa leitura sem expor saldo, alocações, movimentações e regras de concorrência a cada busca.

Escrita e leitura ficam no **mesmo PostgreSQL de Estoque**, em tabelas distintas. CQRS separa responsabilidades e modelos, sem exigir bancos físicos diferentes. Uma infraestrutura separada não traz benefício suficiente para o escopo atual.

## 2. Modelo de escrita canônico

| Tabela | Responsabilidade |
|---|---|
| `itens` | Catálogo canônico de medicamentos e insumos. |
| `saldos` | Estoque físico, quantidade alocada, permissão de reserva e versão por unidade/item. É a fonte de verdade operacional. |
| `alocacoes` | Quantidades vinculadas às reservas e seu consumo ou liberação. |
| `movimentacoes` | Histórico das entradas, ajustes e saídas físicas. |

Comandos validam o saldo canônico e mantêm suas invariantes com transações locais e controle de concorrência, conforme o documento de bancos. Uma consulta de disponibilidade não reserva quantidade nem garante que uma alocação posterior será aceita. `permiteReserva` na projeção também é informativo; o comando revalida a permissão canônica.

## 3. Modelo de leitura

A tabela `disponibilidade` mantém uma linha por `(unidadeId, itemId)`, com PK composta nesses campos e todos os campos obrigatórios:

| Campo | Tipo e uso |
|---|---|
| `unidadeId` | `uuid`; identifica a unidade da consulta. |
| `itemId` | `uuid`; identifica o item da consulta. |
| `quantidadeDisponivel` | `integer`; resultado de `estoqueFisicoAtual - quantidadeAlocada`. |
| `permiteReserva` | `boolean`; permissão refletida pelo estado aplicado. |
| `atualizadoEm` | `timestamptz`; instante do estado refletido, obtido de `occurredAt` do evento aplicado ou de `saldos.updatedAt` na reconstrução. |
| `estoqueVersion` | `bigint`; versão do saldo refletido, usada internamente para controlar a atualização. |

O endpoint existente `GET /api/cidadao/v1/estoque/disponibilidade` lê essa projeção. Nomes e demais dados de apresentação agregados pelos BFFs não precisam ser duplicados nela. A versão é interna à projeção; o contrato HTTP atual não a expõe.

## 4. Atualização assíncrona e defasagem

O fluxo é: **alteração canônica + Outbox na mesma transação → worker → RabbitMQ → consumidor da projeção → `disponibilidade`**. A transação de domínio não atualiza diretamente a projeção; a atualização assíncrona demonstra a consistência eventual planejada, mesmo com os dois modelos no mesmo PostgreSQL.

O consumidor usa os seis eventos de Estoque definidos em `11-outbox.md`: `estoque.alocacao-criada.v1`, `estoque.alocacao-liberada.v1`, `estoque.entrada-registrada.v1`, `estoque.ajustado.v1`, `estoque.retirada-baixada.v1` e `estoque.permissao-reserva-alterada.v1`.

Cada evento traz `unidadeId`, `itemId`, `estoqueVersion` e o estado resultante: `estoqueFisicoAtual`, `quantidadeAlocada` e `permiteReserva`. O consumidor calcula a disponibilidade e grava o estado correspondente, sem acumular deltas. A projeção não baixa estoque diretamente ao receber `retirada.concluida.v1`: esse evento primeiro provoca o processamento canônico da retirada em Estoque, que produz `estoque.retirada-baixada.v1`.

A meta operacional é aplicar mudanças à projeção em até aproximadamente **5 segundos em condições normais**. Falhas ou acúmulo de mensagens podem aumentar o atraso; não há garantia absoluta desse prazo. As respostas de disponibilidade devem preservar `atualizadoEm`, inclusive quando agregadas pelos BFFs. Esse campo não é substituído pelo horário da consulta: representa o estado exibido, que pode estar temporariamente defasado.

## 5. Duplicatas e eventos fora de ordem

O consumidor combina dois controles locais:

- **`eventId`:** a Inbox, com chave `(consumer, eventId)`, evita reaplicar a mesma mensagem. Inbox e efeito na projeção são confirmados na mesma transação; o ACK ocorre após o commit, ou após constatar processamento anterior confirmado.
- **`estoqueVersion`:** a atualização por `(unidadeId, itemId)` só ocorre se a versão recebida for maior que a armazenada, com comparação e gravação atômicas. Isso também protege contra consumidores concorrentes. Uma linha ainda inexistente é criada com o estado recebido.

Se a projeção está na versão **18**, um evento de versão **17** não altera seus valores nem `atualizadoEm`; um de versão **19** aplica o estado resultante. Eventos com versão menor ou igual podem ser registrados como tratados na Inbox, sem alterar a projeção. Não é necessário aguardar todas as versões intermediárias, pois cada evento carrega o estado completo necessário à leitura. A ordem é por saldo, sem ordenação global entre unidades e itens.

## 6. Retirada sem desconto duplicado

| Estado | Estoque físico | Quantidade alocada | Disponibilidade |
|---|---:|---:|---:|
| Antes da retirada | 10 | 2 | 8 |
| Após a retirada de 2 unidades | 8 | 0 | 8 |

A alocação já retirou as duas unidades da disponibilidade. Ao consumir a alocação, Estoque reduz físico e alocado pela mesma quantidade; a projeção recalcula a diferença a partir do estado resultante. Descontar novamente a quantidade retirada da disponibilidade produziria um valor incorreto.

## 7. Reconstrução e diferença para Event Sourcing

Os eventos propagam alterações; não são a única fonte de verdade. Se a projeção precisar ser reconstruída, ela é recriada a partir de uma leitura consistente de `saldos`, calculando `quantidadeDisponivel` e copiando identificadores, permissão, versão e `updatedAt` para `atualizadoEm`.

Durante a recarga, pausa-se o consumidor da projeção após concluir os processamentos em andamento. Depois da recarga, ele retoma os eventos pendentes, preservando a Inbox. Eventos anteriores ao estado carregado não são reaplicados, pela comparação de versão; alterações ocorridas durante a recarga chegam pelo fluxo normal de Outbox/RabbitMQ. Assim, a reconstrução não depende de reproduzir eventos que a Inbox já marcou como processados.

Essa escolha mantém a recuperação baseada no estado canônico e dispensa retenção eterna ou replay de todo o histórico de eventos. O histórico de movimentações continua tendo sua finalidade de domínio; CQRS não transforma o projeto em Event Sourcing.

## 8. Verificação de `atualizadoEm` nos contratos

| Contrato | Situação atual |
|---|---|
| [API de Estoque](./api/estoque.yaml), schema `DisponibilidadeItem` | Declara `atualizadoEm` como `string/date-time`, mas não possui lista `required` para garantir sua presença. |
| [BFF Cidadão](./api/bff-cidadao.yaml), `GET /explorar` | Exibe disponibilidade pelo campo `disponivel`, mas não declara `atualizadoEm` nos itens da resposta. |
| [BFF Unidade](./api/bff-unidade.yaml), `GET /painel/estoque` | A resposta não define schema; não é possível confirmar a propagação de `atualizadoEm` caso exiba disponibilidade. |

A propagação contratual ainda não está completa. Esses pontos ficam sinalizados para alinhamento, sem alteração dos contratos neste documento.
