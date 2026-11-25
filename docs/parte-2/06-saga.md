# GlicoAcesso - SAGA de confirmação e cancelamento

**Etapa:** 2 — Arquitetura\
**Documento:** 06 - SAGA\
**Versão:** 1.1\
**Última revisão:** 24 de novembro de 2026

## 1. Objetivo e escopo

A confirmação coordena o aceite, a alocação e a preparação da autorização. O cancelamento reverte efeitos distribuídos aplicáveis. Os estados e as regras seguem o [contrato central](./00-decisoes-compartilhadas.md), em especial as seções 8 e 9. A retirada física ocorre depois da confirmação, conforme o [fluxo de reservas](./05-fluxo-reservas.md).

## 2. Decisão arquitetural e participantes

A SAGA é **orquestrada**. A ordem dos efeitos e a recuperação de falhas ficam explícitas em uma única execução durável. Na coreografia, a decisão sobre quando avançar e compensar ficaria distribuída entre os consumidores de eventos.

| Serviço | Responsabilidade |
|---|---|
| Orquestrador | Recebe o pedido do BFF, persiste a execução em seu PostgreSQL e coordena chamadas, recuperação e compensações. |
| Reservas | Valida o ator, o prazo e as transições. Grava o aceite, os estados de negócio e o histórico no próprio banco. |
| Estoque | Aloca e libera a quantidade usando o modelo de escrita canônico. |
| Retiradas | Prepara e revoga a autorização. Serializa a revogação com o registro da entrega. |

A confirmação atravessa Reservas, Estoque e Retiradas. O Orquestrador envia comandos HTTP internos. RabbitMQ propaga fatos, incluindo a entrega que pode auxiliar na reconciliação de um cancelamento.

## 3. Identificadores e unicidade

`reservaId` vincula os dados dos participantes. O Orquestrador cria um `sagaId` por execução de confirmação ou cancelamento e garante uma execução ativa por reserva. Uma etapa repetida mantém `sagaId`, chave e conteúdo. Uma compensação tem chave própria. `correlationId` permite rastrear as chamadas da mesma operação.

## 4. SAGA de confirmação

### 4.1 Pré-condições

O BFF Unidade encaminha o aceite do profissional autenticado ao Orquestrador. Reservas valida o vínculo com a unidade, o prazo e a transição de `SOLICITADA` para `EM_CONFIRMACAO`, que disputa com rejeição, expiração e cancelamento local.

### 4.2 Ordem dos passos

| Ordem | Responsável | Efeito confirmado |
|---:|---|---|
| 0 | Orquestrador | Persiste o pedido idempotente, a execução e a intenção do primeiro comando. |
| 1 | Reservas | `AceitarReserva` grava o aceite e `EM_CONFIRMACAO` em sua própria transação. |
| 2 | Estoque | `AlocarEstoque` cria uma alocação para a reserva após validar a quantidade canônica. |
| 3 | Retiradas | `PrepararAutorizacao` grava a autorização vinculada à reserva. |
| 4 | Reservas | `FinalizarConfirmacao` grava `CONFIRMADA`, o ponto de compromisso. |
| 5 | Orquestrador | Após obter o resultado conclusivo da finalização, grava `CONCLUIDA` em seu banco. |

Se Reservas rejeitar o aceite conclusivamente, o Orquestrador encerra a execução como `INTERROMPIDA`, preserva o estado de negócio e deixa de chamar Estoque e Retiradas.

### 4.3 Compensações

Antes do ponto de compromisso, uma falha definitiva exige resolver os efeitos já produzidos. Quando a autorização existe, o Orquestrador solicita `CancelarAutorizacao` e confirma a revogação antes de solicitar `LiberarAlocacao`. Se houver evidência conclusiva de que a autorização nunca foi criada, pode liberar a alocação diretamente. Só depois dos efeitos aplicáveis resolvidos solicita a Reservas a gravação de `FALHA_CONFIRMACAO` e registra `COMPENSADA`.

Após `CONFIRMADA`, o Orquestrador recupera a execução até gravar `CONCLUIDA`. Um pedido posterior de reversão segue o fluxo de cancelamento com outro `sagaId`.

### 4.4 Resultado de negócio, erro técnico e timeout

Timeout, conexão interrompida ou queda após um envio deixam o resultado desconhecido. O Orquestrador repete o comando com a mesma `Idempotency-Key` e conteúdo para recuperar o resultado original. A regra vale para todos os passos, inclusive o aceite, a finalização e as compensações. Um resultado ainda incerto mantém a execução pendente.

### 4.5 Validação posterior no balcão

O BFF Unidade registra a entrega diretamente em Retiradas. Retiradas exige o estado canônico `CONFIRMADA` por consulta a Reservas e revalida a autorização na transação local. A confirmação termina sem aguardar a entrega.

## 5. Cancelamento distribuído

### 5.1 Reserva em `SOLICITADA`

Reservas valida e grava o cancelamento local condicionalmente. Se o aceite vencer e Reservas devolver `CANCELAMENTO_DISTRIBUIDO`, o BFF encaminha o pedido ao Orquestrador. A mesma chave recupera a decisão de encaminhamento, conforme os [contratos dos BFFs](./04-bffs.md).

### 5.2 Reserva em `EM_CONFIRMACAO`

O Orquestrador valida o solicitante em Reservas, persiste o pedido com novo `sagaId` e devolve `202`. A execução de cancelamento aguarda a confirmação concluir ou compensar seus comandos. A confirmação e o cancelamento executam comandos em série para a mesma reserva. Ao assumir a vez, o cancelamento revalida o estado com Reservas e segue a seção 5.3. Se a confirmação chegou a um estado terminal sem confirmar a reserva, o cancelamento é encerrado com `INTERROMPIDA`.

### 5.3 Reserva em `CONFIRMADA` e disputa com a entrega

O Orquestrador inicia o cancelamento e solicita a Reservas `CANCELAMENTO_EM_ANDAMENTO`. Depois solicita a revogação da autorização. Retiradas serializa revogação e entrega no mesmo registro de autorização. Uma consulta anterior a `CONFIRMADA` permite que uma entrega já em andamento concorra com a revogação.

- **Revogação vence:** o resultado durável de Retiradas permite ao Orquestrador liberar a alocação. Após confirmar a liberação, solicita `CANCELADA` a Reservas e conclui a execução.
- **Entrega vence:** Retiradas informa que a entrega foi registrada. O Orquestrador encerra o cancelamento como `INTERROMPIDA` e preserva a alocação para a baixa física. Reservas deduplica sua cópia de `retirada.concluida.v1` e grava `RETIRADA` na transação de negócio. Estoque baixa o físico em sua transação. A Inbox do Orquestrador ajuda a reconciliar a execução em outra transação, independentemente da ordem de consumo.

### 5.4 Falha durante o cancelamento

Se a revogação tiver resultado incerto, o Orquestrador mantém o cancelamento pendente e repete o comando original. Liberação exige uma revogação confirmada ou evidência conclusiva de que nunca houve autorização. Se a liberação ou a finalização ficar incerta, o Orquestrador retoma a etapa correspondente. Respostas tardias e eventos repetidos preservam o resultado terminal.

## 6. Estados duráveis da execução

Os estados técnicos ficam no Orquestrador e seguem a seção 9.4 do contrato central. O estado de negócio é consultado em Reservas. Como as gravações são independentes, o estado técnico pode ficar temporariamente defasado.

| Estado técnico | Significado |
|---|---|
| `EM_EXECUCAO` | Confirmação iniciada, com etapa a executar ou resultado pendente. |
| `COMPENSANDO` / `COMPENSACAO_PENDENTE` | Reversão após falha definitiva em andamento ou aguardando recuperação. |
| `AGUARDANDO_CONFIRMACAO` | Cancelamento admitido e aguardando a confirmação ativa terminar. |
| `CANCELANDO` / `CANCELAMENTO_PENDENTE` | Cancelamento distribuído em andamento ou aguardando recuperação. |
| `INTERROMPIDA` | Aceite inicial rejeitado ou cancelamento inviabilizado, conforme o desfecho registrado. |
| `CONCLUIDA` | Reservas gravou `CONFIRMADA` e o Orquestrador confirmou a finalização. |
| `COMPENSADA` | Efeitos aplicáveis revertidos e falha de confirmação gravada. |
| `CANCELADA` | Operações aplicáveis confirmadas e cancelamento gravado em Reservas. |

## 7. Persistência e recuperação

O Orquestrador persiste execução, intenção, chave e conteúdo **antes** de cada envio. O participante grava atomicamente o efeito e o resultado idempotente em seu próprio banco. O Orquestrador persiste o resultado e só então avança. Após reinício, restaura execuções não terminais e repete a intenção que ainda tiver resultado desconhecido.

O registro inclui `sagaId`, `reservaId`, tipo, estado, versão, etapa, efeitos, compensações, tentativas, próximo retry e correlação. O resultado conclusivo pode ser reobtido mesmo que a requisição original já tenha sido encerrada. Backoff reduz tentativas em falhas transitórias. Esgotar as tentativas automáticas deixa o trabalho pendente para reconciliação auditada.

## 8. Idempotência e concorrência

- Participantes deduplicam comandos por serviço, operação, principal autenticado e chave. A mesma chave e conteúdo reproduzem o resultado conclusivo. Conteúdo diferente retorna conflito.
- O Orquestrador usa controle transacional e versão para serializar o trabalho por reserva. Uma réplica que perdeu a posse deixa de avançar ou persistir passos. Repetições de intenção já registrada usam a mesma chave e conteúdo.
- Reservas usa transições condicionais. Estoque garante uma alocação ativa por reserva e protege o saldo canônico. Retiradas garante uma autorização por reserva e arbitra a corrida entre revogação e entrega.
- Reservas, Estoque e Orquestrador recebem cópias do evento de retirada em filas independentes e deduplicam por `eventId` nas próprias transações.

## 9. Matriz de falhas e tratamento

A [especificação complementar](./08-saga.md) reúne os pontos de interrupção, a evidência necessária para retomar e o efeito esperado em cada cenário.

## 10. Observabilidade e operação

Cada execução deve ser rastreável por `sagaId` e `reservaId`, com `correlationId` propagado às chamadas internas. O Orquestrador registra início e fim das etapas, tentativas, respostas de negócio, timeouts, compensações e resultado da reconciliação. Reservas mantém a auditoria das transições de negócio.

Logs e métricas não devem incluir tokens, credenciais ou dados pessoais desnecessários. Erros apresentados ao cidadão não revelam detalhes internos. A equipe autorizada deve localizar:

- execuções não terminais e há quanto tempo estão pendentes;
- etapa e participante aguardados;
- última tentativa e próximo retry previsto;
- compensações concluídas e pendentes;
- inconsistências que exigem reconciliação manual;
- reserva e execução relacionadas, sem alterar diretamente o banco de outro serviço.

Intervenção manual não grava diretamente nos bancos de Estoque ou Retiradas. A correção usa operações administrativas auditadas do serviço proprietário ou comandos idempotentes apropriados.

## 11. Diagramas de sequência

- [Confirmação](./diagramas/saga-sucesso.md) e [transações no caminho feliz](./diagramas/saga-caminho-feliz.md).
- [Falha ao preparar a autorização](./diagramas/saga-falha.md) e [falha definitiva antes do ponto de compromisso](./diagramas/saga-compensacao.md).
- [Cancelamento concorrente com a retirada](./diagramas/saga-cancelamento-retirada.md).
