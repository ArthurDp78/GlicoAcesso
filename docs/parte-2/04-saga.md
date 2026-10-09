# GlicoAcesso — SAGA de confirmação e cancelamento

**Etapa:** 2 — Arquitetura  
**Documento:** 04 — SAGA  
**Versão:** 1.0  
**Responsável:** Pessoa 1 — arquitetura e fluxo  
**Documento normativo:** [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md)  
**Fluxo de negócio:** [03 — Fluxo de reservas](./03-fluxo-reservas.md)  
**Diagramas:** [sucesso](./diagramas/saga-sucesso.md) e [falha](./diagramas/saga-falha.md)  
**Última revisão:** 9 de outubro de 2026

> Este documento especifica como Reservas coordena efeitos distribuídos ao confirmar ou cancelar uma reserva. Não há transação compartilhada entre bancos: cada participante altera somente o próprio banco. Em caso de divergência, prevalecem as regras do documento 00.

## 1. Objetivo e escopo

A SAGA cobre:

1. a confirmação iniciada quando um profissional aceita uma solicitação;
2. o cancelamento de uma confirmação em andamento ou já concluída, desde que a entrega física ainda não tenha sido registrada.

A retirada física não é uma etapa da SAGA de confirmação. Ela acontece posteriormente em Retiradas e é comunicada por `retirada.concluida.v1`. Reservas e Estoque consomem esse evento independentemente, conforme os documentos 00 e 03.

## 2. Decisão arquitetural e participantes

A SAGA é **orquestrada por Reservas**. Reservas persiste o processo, escolhe a próxima etapa e inicia compensações quando necessário. Estoque e Retiradas executam comandos locais e idempotentes; não chamam um ao outro nem coordenam o processo global.

| Participante | Responsabilidade | Dados que altera |
|---|---|---|
| Reservas — coordenador | Mantém o estado durável da execução, envia comandos, decide continuar ou compensar e atualiza o estado de negócio. | Banco de Reservas. |
| Estoque | Valida o saldo canônico, cria uma alocação ou libera a alocação pertencente à reserva. | Banco de Estoque. |
| Retiradas | Prepara ou cancela a autorização de balcão sem registrar entrega física. | Banco de Retiradas. |

Unidades fornece o prazo de análise na criação da solicitação, mas não participa da SAGA. A aceitação profissional inicia o processo; o profissional não coordena suas etapas.

## 3. Identificadores, execuções e unicidade

| Identificador | Regra |
|---|---|
| `reservaId` | Liga a solicitação, a SAGA, a alocação e a autorização. É criado por Reservas. |
| `sagaId` | Identifica uma execução. Confirmação e cancelamento são execuções distintas, vinculadas ao mesmo `reservaId`. Retentativas da mesma execução reutilizam o mesmo `sagaId`. |
| `correlationId` | Permite localizar chamadas e logs do fluxo. É propagado aos participantes. |
| `idempotencyKey` | Identifica o comando lógico de uma etapa. Retentativas reutilizam a chave; operações diferentes usam chaves diferentes. |
| `eventId` | Identifica eventos assíncronos e é usado por consumidores para deduplicação. Não coordena a confirmação. |

Só pode existir **uma execução ativa por `reservaId`**. Atualizações de estado em Reservas devem ser condicionais para impedir duas confirmações ou dois cancelamentos ativos ao mesmo tempo.

## 4. SAGA de confirmação

### 4.1 Pré-condições

Reservas inicia a confirmação somente quando:

- a reserva existe e está em `SOLICITADA`;
- o aceite foi feito por profissional autenticado e autorizado para a unidade da reserva;
- o aceite venceu a concorrência com a expiração, antes de `decisaoAte`;
- não há outra execução ativa para o `reservaId`;
- a transação local de Reservas que grava o aceite e a SAGA foi confirmada.

Se uma condição falhar, nenhum participante é chamado. Durante o processamento, o estado de negócio da reserva é `EM_CONFIRMACAO`; aceite pela unidade não significa confirmação.

### 4.2 Ordem dos passos

| Ordem | Serviço | Comando ou ação | Condição para avançar |
|---:|---|---|---|
| 0 | Reservas | Registra o aceite, muda `SOLICITADA` para `EM_CONFIRMACAO`, cria `sagaId` e persiste a execução como `EM_EXECUCAO`. | A transação local foi confirmada. Se não foi, não envia comandos. |
| 1 | Reservas → Estoque | `AlocarEstoque`(`reservaId`, `unidadeId`, `itemId`, quantidade). | Estoque confirma uma alocação ativa no próprio banco. |
| 2 | Reservas → Retiradas | `PrepararAutorizacao`(`reservaId`, `unidadeId`, `itemId`, quantidade). Só ocorre após confirmação da alocação. | Retiradas confirma uma autorização utilizável no balcão, vinculada à reserva. |
| 3 | Reservas | Grava `CONFIRMADA` e a execução `CONCLUIDA` em transação local. | Só após a confirmação local a reserva é apresentada como confirmada. |

Os comandos internos são síncronos e versionados pelos contratos internos. Uma resposta de sucesso significa que o participante confirmou o efeito em seu próprio banco, não que Reservas alterou o banco dele.

### 4.3 Efeitos e compensações

| Efeito confirmado | Compensação | Regra |
|---|---|---|
| Alocação ativa em Estoque | `LiberarAlocacao`(`reservaId`) | Libera somente a alocação dessa reserva. Repetir a liberação ou liberar uma alocação já inexistente é idempotente e não altera outras reservas. |
| Autorização preparada em Retiradas | `CancelarAutorizacao`(`reservaId`) | Revoga a autorização sem apagar o histórico. Repetir o cancelamento mantém o mesmo resultado. |

As compensações ocorrem na ordem inversa dos efeitos: cancelar a autorização em Retiradas e depois liberar a alocação em Estoque. Não liberar o estoque enquanto a autorização ainda puder ser usada.

### 4.4 Resultado de negócio, erro técnico e timeout

| Resposta/situação | Interpretação | Ação de Reservas |
|---|---|---|
| Estoque rejeita por regra de negócio, como saldo insuficiente | Não houve alocação. | Não chama Retiradas. Finaliza a SAGA como `COMPENSADA` e a reserva como `FALHA_CONFIRMACAO`. |
| Retiradas rejeita por regra de negócio após a alocação | A alocação existe; autorização não foi criada. | Libera a alocação. Após confirmação, finaliza como `COMPENSADA`/`FALHA_CONFIRMACAO`. |
| Erro temporário do participante | O processo pode continuar. | Mantém execução ativa e aplica retry; não marca falha final apenas por erro temporário. |
| Timeout, conexão interrompida ou resposta perdida | O comando pode ter sido confirmado sem que Reservas receba a resposta. | Trata como resultado desconhecido. Consulta pelo `reservaId` se houver consulta contratada ou reenvia o mesmo comando idempotente. Não compensa às cegas. |
| Falha temporária ao persistir a finalização em Reservas | Efeitos dos participantes podem estar confirmados, mas o estado local não. | Repete a finalização local. Não inicia compensação por falha temporária de banco. |

`FALHA_CONFIRMACAO` só é final depois que todos os efeitos confirmados tiverem sido compensados. Enquanto uma etapa ou compensação estiver pendente, a reserva permanece `EM_CONFIRMACAO` e a SAGA não é terminal.

## 5. Cancelamento distribuído

O cancelamento é uma execução distinta da confirmação: usa novo `sagaId` e o mesmo `reservaId`. Pode ser solicitado pelo cidadão proprietário ou por profissional autorizado da unidade. Para profissional, a justificativa não vazia é obrigatória e fica na auditoria.

### 5.1 Reserva em `SOLICITADA`

Nenhum efeito da SAGA existe. Reservas valida o ator, verifica condicionalmente o estado e registra `CANCELADA` localmente. Não chama Estoque nem Retiradas.

### 5.2 Reserva em `EM_CONFIRMACAO`

1. Reservas valida o ator e registra, em transação local, `CANCELAMENTO_EM_ANDAMENTO`, ator, instante e justificativa quando aplicável.
2. A transição impede o início de etapas novas da confirmação.
3. Se houver comando em voo ou resultado desconhecido, Reservas primeiro reconcilia o resultado no participante com `reservaId` e a mesma chave idempotente. Não presume que o comando falhou.
4. A execução de confirmação passa para `INTERROMPIDA` após Reservas reconciliar todas as chamadas em voo ou com resultado desconhecido. Nenhuma nova etapa de confirmação pode ser iniciada. Os efeitos confirmados permanecem registrados.
5. Depois que a execução de confirmação deixa de estar ativa, Reservas inicia uma execução de cancelamento com novo `sagaId`.
6. A execução de cancelamento compensa apenas efeitos confirmados, na ordem inversa: cancela autorização, se existente; depois libera alocação, se existente.
7. Após confirmar todas as operações aplicáveis, Reservas grava `CANCELADA` e conclui a execução de cancelamento.

Se nenhum participante produziu efeito, o cancelamento pode terminar localmente. Ainda assim, comandos em voo ou com resultado incerto precisam ser resolvidos antes de declarar `CANCELADA`.

### 5.3 Reserva em `CONFIRMADA`

1. Reservas valida o ator e inicia uma execução de cancelamento.
2. Reservas grava `CANCELAMENTO_EM_ANDAMENTO`.
3. Reservas envia `CancelarAutorizacao`(`reservaId`) a Retiradas.
4. Depois que Retiradas confirmar o cancelamento, Reservas envia `LiberarAlocacao`(`reservaId`) a Estoque.
5. Só após as confirmações aplicáveis Reservas grava `CANCELADA`.

Retiradas serializa `CancelarAutorizacao` e `RegistrarRetirada`: somente uma operação pode vencer. Se a entrega já foi registrada, Retiradas recusa o cancelamento; Reservas processa `retirada.concluida.v1` e atualiza a reserva para RETIRADA. Se o cancelamento vencer, a autorização não pode ser usada.

### 5.4 Falha durante o cancelamento

Indisponibilidade ou timeout não conclui nem desfaz automaticamente o cancelamento. Reservas mantém `CANCELAMENTO_EM_ANDAMENTO`, registra a etapa pendente e repete usando a mesma chave idempotente. Não apresenta `CANCELADA` enquanto existir autorização utilizável ou alocação a liberar.

Se Retiradas confirmou a revogação, mas Estoque ainda não confirmou a liberação, a execução permanece pendente na etapa de Estoque. Repetir `CancelarAutorizacao` não reativa a autorização; repetir `LiberarAlocacao` atua somente sobre o `reservaId` correspondente.

## 6. Estados duráveis da execução

O estado da SAGA não substitui o estado de negócio da reserva. Uma execução pendente nunca deve ser apresentada como concluída ou como falha final.

| Estado da SAGA | Significado | Estado de negócio da reserva |
|---|---|---|
| `EM_EXECUCAO` | Há etapa a executar, em processamento ou com resultado técnico desconhecido. | `EM_CONFIRMACAO` |
| `COMPENSANDO` | Ocorreu falha definitiva após efeito confirmado; compensações estão em curso. | `EM_CONFIRMACAO` |
| `COMPENSACAO_PENDENTE` | Uma compensação não foi confirmada; retry/reconciliação pendente. | `EM_CONFIRMACAO` |
| `CANCELANDO` | Cancelamento solicitado está revertendo efeitos distribuídos. | `CANCELAMENTO_EM_ANDAMENTO` |
| `CANCELAMENTO_PENDENTE` | Operação aplicável do cancelamento não foi confirmada. | `CANCELAMENTO_EM_ANDAMENTO` |
| `INTERROMPIDA` | Execução de confirmação foi parada por cancelamento; chamadas em voo foram reconciliadas e não haverá novas etapas nela. | `CANCELAMENTO_EM_ANDAMENTO` enquanto a execução distinta de cancelamento continua |
| `CONCLUIDA` | Alocação e autorização foram confirmadas e a reserva foi finalizada localmente. | `CONFIRMADA` |
| `COMPENSADA` | Efeitos da confirmação foram desfeitos após falha definitiva. | `FALHA_CONFIRMACAO` |
| `CANCELADA` | Efeitos aplicáveis foram desfeitos após solicitação de cancelamento. | `CANCELADA` |

O registro durável deve permitir recuperar, no mínimo: `sagaId`, `reservaId`, tipo da execução (confirmação ou cancelamento), estado, etapa atual, efeitos confirmados, compensações concluídas, tentativas, próximo instante elegível para retry, erro técnico sanitizado, `correlationId`, timestamps de criação/atualização e controle de concorrência. Não deve armazenar tokens, credenciais ou dados pessoais desnecessários.

## 7. Persistência e recuperação

1. A decisão de aceite, a mudança para `EM_CONFIRMACAO` e a criação da execução são gravadas na mesma transação local de Reservas.
2. Antes de enviar um comando, Reservas persiste a etapa a executar e sua chave idempotente.
3. Após a confirmação de um participante, Reservas persiste o efeito confirmado e a próxima etapa. O fluxo não depende somente da memória do servidor nem da conexão HTTP original.
4. Após falha ou reinício, Reservas busca no próprio banco as execuções não terminais e retoma a partir do último estado durável.
5. Se a resposta não chegou, consulta o estado por `reservaId` quando o contrato interno suportar essa consulta. Caso contrário, reenvia o comando original com a mesma chave idempotente.
6. Se o banco de Reservas estiver indisponível antes de gravar o aceite, nenhum comando é enviado. Se ficar indisponível depois de um participante confirmar, o coordenador reconcilia a etapa após a recuperação.
7. O histórico de tentativas, efeitos e compensações é preservado. Correções operacionais são auditáveis.

Backoff, limite de tentativas automáticas, alertas e procedimento de fila de falhas serão definidos na documentação operacional/Outbox. Atingir um limite de tentativas não converte resultado incerto em falha de negócio: a execução continua pendente para reconciliação.

## 8. Idempotência e concorrência

- Cada comando é idempotente por operação e `reservaId`. A mesma chave e o mesmo conteúdo retornam o resultado original; a mesma chave com conteúdo diferente é conflito.
- Estoque permite no máximo uma alocação ativa por `reservaId`. Repetir a alocação retorna a mesma alocação, sem reservar quantidade novamente.
- `LiberarAlocacao`(`reservaId`) não afeta outras reservas. Liberar alocação já liberada ou inexistente é idempotente.
- Retiradas mantém no máximo uma autorização por reserva. Repetir a preparação retorna a autorização existente; cancelar repetidamente não apaga histórico nem reativa a autorização.
- Reservas aplica transições condicionais de estado para impedir decisões incompatíveis concorrentes.
- Retry técnico da mesma execução reutiliza `sagaId` e a chave idempotente da etapa. Cancelamento posterior usa outro `sagaId`.
- Consumidores de eventos deduplicam por `eventId`. `retirada.concluida.v1` é evento posterior, publicado pela Outbox de Retiradas, não comando da SAGA.

## 9. Matriz de falhas e tratamento

| Ponto da falha | Efeitos confirmados | Tratamento | Resultado após resolução |
|---|---|---|---|
| Antes de persistir o aceite | Nenhum | Não chama participantes. Só permite nova tentativa se a reserva continuar `SOLICITADA`. | Estado original ou `EM_CONFIRMACAO` se a transação foi confirmada. |
| Estoque rejeita por saldo/regra de negócio | Nenhum | Encerra sem chamar Retiradas. | `FALHA_CONFIRMACAO`; SAGA `COMPENSADA`. |
| Resposta de Estoque perdida | Desconhecido | Consulta por `reservaId` ou reenvia alocação idempotente; não libera às cegas. | `EM_CONFIRMACAO` até resolução. |
| Retiradas rejeita após alocação | Alocação | Libera a alocação em Estoque e aguarda confirmação. | Após liberar: `FALHA_CONFIRMACAO`; SAGA `COMPENSADA`. |
| Timeout ao preparar autorização | Alocação; autorização possivelmente criada | Consulta ou repete preparação idempotente. Se não puder preparar, cancela eventual autorização e libera alocação. | Pendente até reconciliação; depois `CONFIRMADA` ou `FALHA_CONFIRMACAO`. |
| Falha temporária ao finalizar em Reservas | Alocação e autorização | Repete a finalização local. | Pendente enquanto transitória; após falha definitiva e compensação, `FALHA_CONFIRMACAO`. |
| Retiradas indisponível ao cancelar | Autorização possivelmente ativa | Mantém `CANCELAMENTO_EM_ANDAMENTO`; não libera estoque antes de resolver a autorização. | `CANCELADA` após confirmar operações aplicáveis. |
| Estoque indisponível ao liberar alocação | Autorização cancelada; alocação possivelmente ativa | Mantém cancelamento pendente e repete liberação idempotente. | `CANCELADA` após liberação confirmada. |
| Retirada vence a corrida contra cancelamento | Entrega registrada | Retiradas recusa cancelamento; Reservas e Estoque processam o evento de retirada. | RETIRADA após Reservas consumir o evento. |

## 10. Observabilidade e operação

Cada execução deve ser rastreável por `sagaId` e `reservaId`, com `correlationId` propagado às chamadas internas. Reservas registra transições, início e fim das etapas, tentativas, respostas de negócio, timeouts, compensações e resultado da reconciliação.

Logs e métricas não devem incluir tokens, credenciais ou dados pessoais desnecessários. Erros apresentados ao cidadão não revelam detalhes internos. A equipe autorizada deve localizar:

- execuções não terminais e há quanto tempo estão pendentes;
- etapa e participante aguardados;
- última tentativa e próximo retry previsto;
- compensações concluídas e pendentes;
- inconsistências que exigem reconciliação manual;
- reserva e execução relacionadas, sem alterar diretamente o banco de outro serviço.

Intervenção manual não grava diretamente nos bancos de Estoque ou Retiradas. A correção usa operações administrativas auditadas do serviço proprietário ou comandos idempotentes apropriados.

## 11. Limites explícitos

- A SAGA não usa transação distribuída/2PC e não grava nos bancos dos participantes.
- RabbitMQ e eventos não substituem os comandos síncronos de confirmação nem transferem a orquestração para Estoque ou Retiradas.
- A SAGA de confirmação termina em `CONFIRMADA`; retirada física é fluxo posterior, comunicado por `retirada.concluida.v1`.
- Reservas não declara falha final enquanto houver resultado remoto incerto ou compensação não confirmada.
- Estoque não usa projeção de leitura como autoridade para alocação.
- Retiradas não registra a mesma entrega duas vezes nem permite confirmar cancelamento da autorização e entrega para a mesma autorização.

## 12. Critérios de conformidade

- Reservas é o único coordenador e mantém registro durável.
- A confirmação segue Reservas → Estoque → Retiradas → Reservas.
- A reserva só passa a `CONFIRMADA` após alocação e autorização confirmadas.
- Falhas definitivas compensam somente efeitos confirmados, em ordem inversa.
- Timeout é resultado incerto, tratado com consulta ou retry idempotente.
- Confirmação e cancelamento são execuções distintas, ligadas ao mesmo `reservaId`; ao cancelar durante a confirmação, a execução de confirmação é reconciliada e encerrada como `INTERROMPIDA` antes da execução de cancelamento.
- Só existe uma execução ativa por reserva.
- O cancelamento só termina depois de revogar autorização e liberar alocação, quando aplicável.
- Retiradas serializa cancelamento da autorização e registro da entrega.
- Execuções pendentes sobrevivem à queda de Reservas e podem ser recuperadas do banco local.
- Nenhum serviço grava no banco de outro serviço.
- Os diagramas de sucesso e falha representam estas mesmas regras.

## 13. Referências

- [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md): estados, comandos, compensações e identificadores canônicos.
- [01 — Decomposição e fronteiras dos microsserviços](./01-microsservicos.md): responsabilidades dos participantes.
- [02 — Diagrama de arquitetura](./02-diagrama-arquitetura.md): componentes e comunicações.
- [03 — Fluxo de reservas](./03-fluxo-reservas.md): fluxo de negócio e estados visíveis.
- [Diagrama de sucesso](./diagramas/saga-sucesso.md) e [diagrama de falha](./diagramas/saga-falha.md): sequências dos caminhos da SAGA.