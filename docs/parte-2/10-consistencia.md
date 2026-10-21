# GlicoAcesso - Consistência eventual e dual write

**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fluxo de reservas](./05-fluxo-reservas.md), [SAGA](./06-saga.md) e [bancos](./09-bancos.md).

## 1. Limite das transações

Cada serviço garante ACID apenas dentro do próprio PostgreSQL. A comunicação entre serviços ocorre por REST ou RabbitMQ, sem transação ACID distribuída e sem 2PC. Uma confirmação local não significa que todos os serviços já foram atualizados.

## 2. Consistência imediata/local

| Serviço | Operações na mesma transação local |
|---|---|
| Estoque | Criar/liberar/consumir a alocação e atualizar `saldos`. No consumo, registrar também a movimentação física e a futura publicação de `estoque.retirada-baixada.v1`. |
| Retiradas | Registrar o uso da autorização, a retirada e a futura publicação de `retirada.concluida.v1` na Outbox. Revalidar a autorização e serializar entrega e revogação, para que apenas uma vença. |
| Reservas | Manter coerentes as alterações de estado, a auditoria e a persistência necessária da SAGA. Por exemplo, aceite, transição para `EM_CONFIRMACAO` e criação da execução são atômicos. |

Estoque valida disponibilidade e permissão no modelo de escrita, com controle de concorrência sobre o saldo. A projeção CQRS não autoriza a alocação. Nos consumidores, deduplicação por `eventId` e efeitos locais são confirmados juntos; a mensagem só é confirmada após essa persistência.

## 3. Consistência eventual e defasagem

| Propagação | Intervalo de divergência esperado |
|---|---|
| Escrita de Estoque → projeção CQRS de disponibilidade | A consulta pode mostrar valores anteriores ao saldo canônico até processar os eventos. |
| Retiradas → Reservas por `retirada.concluida.v1` | Retiradas já conhece a entrega; Reservas ainda pode exibir `CONFIRMADA` ou `CANCELAMENTO_EM_ANDAMENTO` até consumir o evento e passar a `RETIRADA`. Se a entrega venceu o cancelamento, encerra essa execução como `INTERROMPIDA`, com auditoria. |
| Retiradas → Estoque pelo mesmo evento | Estoque ainda mantém o físico e a alocação anteriores até validar e processar a retirada. A quantidade permanece alocada nesse intervalo. |

Reservas e Estoque recebem o evento por filas duráveis independentes; ambos precisam processá-lo. Depois da baixa local, Estoque publica `estoque.retirada-baixada.v1` pela Outbox para atualizar a projeção.

No processamento válido da retirada, Estoque reduz `estoqueFisicoAtual` e `quantidadeAlocada` pela mesma quantidade. Exemplo: físico 10 e alocado 3 dão disponibilidade 7; ao consumir as 3 unidades alocadas, físico 7 e alocado 0 continuam dando disponibilidade 7. A retirada não reduz a disponibilidade duas vezes: a alocação já havia descontado essa quantidade.

A projeção CQRS tem como meta operacional defasagem de até aproximadamente **5 segundos em condições normais**. As respostas de disponibilidade expõem `atualizadoEm`, que permite ao cliente identificar a idade da projeção. Essa meta não é garantia absoluta durante falhas ou acúmulo de mensagens.

## 4. Dual write e tratamento dos riscos

Alterar PostgreSQL e publicar diretamente no RabbitMQ são duas operações independentes. Por exemplo, Retiradas pode confirmar a retirada no banco e a publicação falhar: a entrega existe, mas Reservas e Estoque não recebem o evento. Inverter a ordem também é inseguro: o evento pode ser publicado e a transação do banco falhar.

A decisão é usar **Transactional Outbox** sempre que um efeito persistido precisar gerar evento: alteração de negócio e registro para futura publicação são atômicos no banco do produtor. A publicação ocorre depois, sem exigir que o RabbitMQ participe da transação.

| Risco | Tratamento |
|---|---|
| Retirada confirmada sem evento para Reservas e Estoque, ou evento sem retirada confirmada | Retirada, uso da autorização e Outbox na mesma transação de Retiradas. |
| Saldo/alocação alterados sem evento para a projeção, ou evento sem alteração confirmada | Alterações de Estoque e Outbox na mesma transação, inclusive na baixa da retirada. |
| Broker ou consumidor indisponível; estados e projeção atrasados | Preservar eventos pendentes, retomar publicação/processamento e monitorar atraso. Falhas persistentes ficam observáveis para reconciliação e reprocessamento, sem descarte silencioso. |
| Reenvio ou entrega duplicada de evento | Entrega pelo menos uma vez, consumidores idempotentes e deduplicação atômica com os efeitos locais, evitando repetir baixa ou transição. |
| Evento de retirada incompatível com a alocação | Validar reserva, unidade, item e quantidade; não aplicar baixa parcial ou arbitrária. Registrar a divergência para reconciliação e reprocessamento. |

O detalhamento da Outbox ficará em `11-outbox.md`. Estruturas completas de Outbox/Inbox, publicador, catálogo de eventos e algoritmo do CQRS ficam para os próximos documentos.

## 5. Consulta síncrona antes da entrega e limites da SAGA

Antes da entrega física, Retiradas consulta `GET /internal/v1/reservas/{reservaId}/estado` na fonte canônica de Reservas e exige o mesmo identificador com estado `CONFIRMADA`. Timeout, indisponibilidade ou outro estado impedem a entrega naquele momento; uma nova tentativa exige nova consulta.

Essa dependência síncrona é deliberada: aceita-se depender da disponibilidade de Reservas naquele momento para evitar sincronização adicional de estado e mecanismo de ativação da autorização. A consulta não bloqueia a reserva; se um cancelamento começar depois, entrega e revogação disputam a autorização local em Retiradas, conforme o documento 00, seção 9.8.

Timeout de comando da SAGA não prova ausência de efeito remoto. Permanecem as decisões de persistir o progresso, reutilizar a chave idempotente e manter resultados incertos pendentes de reconciliação. As consultas de resultados de alocação/autorização ainda ausentes dos contratos continuam como pendência de alinhamento; este documento não define novos endpoints nem mecanismos de recuperação.
