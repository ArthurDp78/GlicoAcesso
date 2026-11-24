# GlicoAcesso - Consistência eventual e dual write

**Referências:** [decisões compartilhadas](./00-decisoes-compartilhadas.md), [fluxo de reservas](./05-fluxo-reservas.md), [SAGA](./06-saga.md) e [bancos](./09-bancos.md).

## 1. Limite das transações

Cada serviço garante ACID apenas dentro do próprio PostgreSQL. A comunicação entre serviços ocorre por REST ou RabbitMQ, sem transação ACID distribuída e sem 2PC. Uma confirmação local não significa que todos os serviços já foram atualizados.

## 2. Consistência imediata/local

| Serviço | Operações na mesma transação local |
|---|---|
| Estoque | Criar/liberar/consumir a alocação e atualizar `saldos`. No consumo, registrar também a movimentação física e a futura publicação de `estoque.retirada-baixada.v1`. |
| Retiradas | Registrar o uso da autorização, a retirada e a futura publicação de `retirada.concluida.v1` na Outbox. Revalidar a autorização e serializar entrega e revogação, para que apenas uma vença. |
| Reservas | Gravar o estado de negócio, a auditoria e o resultado idempotente na mesma transação. No aceite, grava a decisão e `EM_CONFIRMACAO`. No consumo da retirada, grava `RETIRADA` e a Inbox. |
| Orquestrador | Gravar o pedido de confirmação, sua execução e a intenção inicial na mesma transação. Também grava resultados de etapas e reconcilia a retirada localmente com a Inbox. |

Estoque valida disponibilidade e permissão no modelo de escrita, com controle de concorrência sobre o saldo. A projeção CQRS não autoriza a alocação. Nos consumidores, deduplicação por `eventId` e efeitos locais são confirmados juntos; a mensagem só é confirmada após essa persistência.

## 3. Consistência eventual e defasagem

| Propagação | Intervalo de divergência esperado |
|---|---|
| Escrita de Estoque → projeção CQRS de disponibilidade | A consulta pode mostrar valores anteriores ao saldo canônico até processar os eventos. |
| Retiradas → Reservas por `retirada.concluida.v1` | Retiradas já conhece a entrega; Reservas ainda pode exibir `CONFIRMADA` ou `CANCELAMENTO_EM_ANDAMENTO` até consumir o evento e passar a `RETIRADA`. |
| Retiradas → Estoque pelo mesmo evento | Estoque ainda mantém o físico e a alocação anteriores até validar e processar a retirada. A quantidade permanece alocada nesse intervalo. |
| Retiradas → Orquestrador pelo mesmo evento | O fato pode chegar antes ou depois da resposta à revogação. O Orquestrador reconcilia o cancelamento em seu banco. |
| Orquestrador ↔ participantes por HTTP | A execução pode estar persistida antes do aceite em Reservas. Após o commit de um efeito, o Orquestrador pode manter a etapa pendente até recuperar o resultado. |

Reservas, Estoque e Orquestrador recebem cópias por filas duráveis independentes. O encerramento técnico do cancelamento no Orquestrador e a transição da reserva são transações distintas. Depois da baixa local, Estoque publica `estoque.retirada-baixada.v1` pela Outbox para atualizar a projeção.

No processamento válido da retirada, Estoque reduz `estoqueFisicoAtual` e `quantidadeAlocada` pela mesma quantidade. Exemplo: físico 10 e alocado 3 dão disponibilidade 7; ao consumir as 3 unidades alocadas, físico 7 e alocado 0 continuam dando disponibilidade 7. A retirada não reduz a disponibilidade duas vezes: a alocação já havia descontado essa quantidade.

A projeção CQRS tem como meta operacional defasagem de até aproximadamente **5 segundos em condições normais**. As respostas de disponibilidade expõem `atualizadoEm`, que permite ao cliente identificar a idade da projeção. Essa meta não é garantia absoluta durante falhas ou acúmulo de mensagens.

## 4. Dual write e tratamento dos riscos

Alterar PostgreSQL e publicar diretamente no RabbitMQ são duas operações independentes. Por exemplo, Retiradas pode confirmar a retirada no banco e a publicação falhar: a entrega existe, mas os três consumidores deixam de receber o fato. Inverter a ordem também é inseguro: o evento pode ser publicado e a transação do banco falhar.

A decisão é usar **Transactional Outbox** sempre que um efeito persistido precisar gerar evento: alteração de negócio e registro para futura publicação são atômicos no banco do produtor. A publicação ocorre depois, sem exigir que o RabbitMQ participe da transação.

| Risco | Tratamento |
|---|---|
| Retirada confirmada sem evento para os três consumidores, ou evento sem retirada confirmada | Retirada, uso da autorização e Outbox na mesma transação de Retiradas. |
| Saldo/alocação alterados sem evento para a projeção, ou evento sem alteração confirmada | Alterações de Estoque e Outbox na mesma transação, inclusive na baixa da retirada. |
| Broker ou consumidor indisponível; estados e projeção atrasados | Preservar eventos pendentes, retomar publicação/processamento e monitorar atraso. Falhas persistentes ficam observáveis para reconciliação e reprocessamento, sem descarte silencioso. |
| Reenvio ou entrega duplicada de evento | Entrega pelo menos uma vez, consumidores idempotentes e deduplicação atômica com os efeitos locais, evitando repetir baixa ou transição. |
| Evento de retirada incompatível com a alocação | Validar reserva, unidade, item e quantidade; não aplicar baixa parcial ou arbitrária. Registrar a divergência para reconciliação e reprocessamento. |

O modelo de Outbox está detalhado em [11-outbox.md](./11-outbox.md), incluindo persistência, publicação, retry e deduplicação. A projeção de disponibilidade e sua atualização por eventos estão detalhadas em [12-cqrs.md](./12-cqrs.md). Este documento consolida os riscos de dual write e as fronteiras de consistência descritas nesses documentos.

## 5. Recuperação entre bancos da SAGA

Persistir a execução e gravar o aceite são operações em bancos diferentes. A ordem das gravações permite recuperar cada intervalo:

| Interrupção | Recuperação |
|---|---|
| Orquestrador cai após persistir a execução e antes de enviar o aceite. | Retomar a intenção inicial com a chave e o conteúdo persistidos. |
| Reservas grava `EM_CONFIRMACAO`, mas a resposta se perde. | Repetir o aceite original. Reservas devolve o resultado gravado com o efeito. Alocação começa após confirmação conclusiva. |
| Participante confirma o efeito e o Orquestrador cai antes de registrar o resultado. | Repetir o comando original. O participante recupera o resultado sem reaplicar o efeito. |
| Reservas grava `CONFIRMADA`, mas o Orquestrador ainda não gravou `CONCLUIDA`. | Recuperar a finalização com a mesma chave e conteúdo, gravar `CONCLUIDA` e preservar os efeitos confirmados. |
| Reservas registra o início do cancelamento durante a confirmação, mas o Orquestrador cai antes de trocar a execução ativa. | Recuperar o resultado do comando de transição e concluir a troca das execuções em uma única transação do Orquestrador. |

A estratégia usa intenções duráveis e comandos HTTP idempotentes. A Outbox cobre a publicação de eventos, enquanto o registro de etapas cobre a recuperação da chamada HTTP e de seu resultado.

## 6. Consulta síncrona antes da entrega

Antes da entrega física, Retiradas consulta `GET /internal/v1/reservas/{reservaId}/estado` na fonte canônica de Reservas e exige o mesmo identificador com estado `CONFIRMADA`. Timeout, indisponibilidade ou outro estado impedem a entrega naquele momento; uma nova tentativa exige nova consulta.

Essa dependência síncrona é deliberada: aceita-se depender da disponibilidade de Reservas naquele momento para evitar sincronização adicional de estado e mecanismo de ativação da autorização. A consulta não bloqueia a reserva; se um cancelamento começar depois, entrega e revogação disputam a autorização local em Retiradas, conforme o documento 00, seção 9.8.

Timeout de comando da SAGA não prova ausência de efeito remoto. O Orquestrador persiste o progresso e repete o mesmo comando com a mesma `Idempotency-Key` e conteúdo para recuperar o resultado original, mantendo a etapa pendente enquanto não houver resposta conclusiva. `GET /internal/v1/autorizacoes/{reservaId}` existe para a agregação operacional do BFF Unidade; não substitui o replay idempotente do comando. Não há uma consulta de resultado de alocação no contrato de Estoque, pois a recuperação da alocação também usa replay idempotente.
