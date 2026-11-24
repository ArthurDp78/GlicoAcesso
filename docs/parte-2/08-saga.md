# GlicoAcesso - Especificação complementar da SAGA

**Etapa:** 2 — Arquitetura\
**Documento:** 08 - Recuperação e compensações\
**Última revisão:** 24 de novembro de 2026

A [especificação da SAGA](./06-saga.md) descreve a ordem dos comandos. Este complemento detalha a recuperação de resultados e os cenários de falha conforme a seção 9 do [contrato central](./00-decisoes-compartilhadas.md).

## 1. Evidência necessária para avançar

O Orquestrador persiste a intenção, o destino, o conteúdo e a chave antes de cada chamada, inclusive nos comandos a Reservas. Cada participante registra o efeito local e seu resultado idempotente na mesma transação. Uma resposta conclusiva, inclusive por repetição do comando, permite avançar. Uma falha de rede deixa a etapa com resultado desconhecido.

O aceite e a gravação de `CONFIRMADA` ocorrem no banco de Reservas. O início e a conclusão técnica da execução ocorrem no banco do Orquestrador. Por isso, existe um intervalo em que um participante já confirmou o efeito, mas o Orquestrador ainda precisa recuperar o resultado.

## 2. Contratos e limites

Os [contratos OpenAPI](./api/) especificam os caminhos abaixo. Os comandos de transição em Reservas partem do Orquestrador. A recepção do pedido pelo Orquestrador tem contrato próprio.

| Operação | Contrato e método | Dados documentados | Respostas documentadas |
|---|---|---|---|
| Iniciar confirmação ou cancelamento distribuído | Orquestrador: `POST /internal/v1/reservas/{reservaId}/confirmacoes` ou `/cancelamentos` sob o mesmo recurso | `reservaId`, ator delegado, `Idempotency-Key` e justificativa em cancelamento por profissional | `202` com `Location` interno de acompanhamento |
| Alterar estado da reserva | Reservas: `POST /internal/v1/reservas/{reservaId}/aceite`, `/confirmar`, `/falhar-confirmacao`, `/iniciar-cancelamento` ou `/finalizar-cancelamento` sob o mesmo recurso | `reservaId`, `sagaId`, `Idempotency-Key` e dados exigidos para cada transição | `200` após gravação local |
| Alocar estoque | Estoque: `POST /internal/v1/alocacoes` | Corpo: `sagaId`, `reservaId`, `unidadeId`, `itemId`, `quantidade`; cabeçalho `Idempotency-Key` | `201`; `409` para saldo insuficiente ou conflito |
| Liberar alocação | Estoque: `DELETE /internal/v1/alocacoes/{reservaId}` | Path `reservaId`; cabeçalhos `Idempotency-Key` e `X-Saga-Id` | `204` |
| Preparar autorização | Retiradas: `POST /internal/v1/autorizacoes` | Corpo: `sagaId`, `reservaId`, `unidadeId`, `itemId`, `quantidade`; cabeçalho `Idempotency-Key` | `201` |
| Cancelar autorização | Retiradas: `POST /internal/v1/autorizacoes/{reservaId}/cancelar` | Path `reservaId`; cabeçalhos `Idempotency-Key` e `X-Saga-Id` | `200` se revogada; `409` com `ENTREGA_JA_REGISTRADA` e `retiradaId` se a entrega venceu |
| Consultar estado para retirada (fora da SAGA) | Reservas: `GET /internal/v1/reservas/{reservaId}/estado` | Path `reservaId`; identidade de serviço de Retiradas; `X-Correlation-Id` opcional; sem chave idempotente | `200` com `reservaId` e `status`; `401`; `403`; `404`; `503` |

A semântica esperada de repetição segue o contrato central. Com a mesma chave, conteúdo e principal autenticado, o participante reproduz o resultado conclusivo. Com conteúdo divergente, devolve conflito de idempotência. O GET de autorização atende ao painel da unidade. O GET de estado da reserva valida a entrega. A recuperação do resultado de um comando usa sua chave e seu conteúdo originais.

## 3. Matriz de falhas e compensações

| Cenário | Evidência ou risco | Ação do Orquestrador |
|---|---|---|
| Falha antes de persistir a execução e a primeira intenção | O pedido pode ou não ter sido registrado. Nenhuma chamada deve partir sem intenção durável. | Recuperar o pedido idempotente e retomar a execução registrada ou iniciá-la se ainda não existir. |
| Aceite em Reservas recusado conclusivamente | Prazo vencido, ator sem permissão ou transição incompatível. | Encerrar a execução sem chamar Estoque ou Retiradas. Preservar o estado da reserva. |
| Resposta do aceite perdida | Reservas pode já ter gravado `EM_CONFIRMACAO`. | Repetir o aceite original antes de alocar. |
| Estoque rejeita a alocação | Nenhuma alocação foi criada. | Solicitar `FALHA_CONFIRMACAO` e concluir a execução sem chamar Retiradas. |
| Resposta de alocação perdida | A alocação pode existir. | Recuperar o resultado com a chave e o conteúdo da alocação. |
| Retiradas rejeita a preparação e confirma ausência de autorização | Existe alocação. | Confirmar a liberação e solicitar `FALHA_CONFIRMACAO`. |
| Resposta da preparação perdida | Existe alocação e a autorização pode existir. | Repetir a preparação original até obter resultado conclusivo. Se houver reversão, confirmar revogação antes de liberar. |
| Finalização recusada definitivamente antes de `CONFIRMADA` | Alocação e autorização foram gravadas. | Revogar a autorização, liberar a alocação e solicitar `FALHA_CONFIRMACAO`, confirmando cada efeito antes de avançar. |
| Resposta da finalização perdida | Reservas pode ter gravado `CONFIRMADA`. | Repetir a finalização original. Se recuperar confirmação, gravar `CONCLUIDA` e preservar os efeitos. |
| Revogação ou liberação sem resultado conclusivo | O efeito original pode persistir. | Manter a etapa pendente e repetir o comando correspondente. Enquanto a revogação estiver incerta, a alocação permanece protegida. |
| Entrega vence a revogação | Retiradas confirma entrega registrada. | Encerrar o cancelamento como `INTERROMPIDA`. A baixa fica a cargo do consumidor de Estoque. |

## 4. Retomada e concorrência

- **Reinício do Orquestrador.** Recupera as execuções não terminais e lê a última intenção e o último resultado persistidos. Repete somente o comando pendente com a chave original. A retomada independe da conexão do cliente.
- **Réplicas e pedidos concorrentes.** O banco do Orquestrador controla uma execução ativa por reserva e o avanço por versão. Reservas protege suas transições com atualização condicional. Estoque protege o saldo no modelo de escrita e garante a unicidade da alocação ativa.
- **Cancelamento durante a confirmação.** O Orquestrador resolve as chamadas em voo antes de assumir quais efeitos precisa reverter. Se o ponto de compromisso já ocorreu, conclui a confirmação e abre um cancelamento distinto. Se a confirmação ainda puder ser interrompida, o aceite da transição em Reservas precede a troca atômica da execução ativa no Orquestrador.
- **Entrega concorrente.** Retiradas serializa a revogação e a entrega. O resultado durável em Retiradas governa a liberação. A Inbox do Orquestrador ajuda a reconciliar o cancelamento e pode refletir a entrega em momento diferente das Inboxes de Reservas e Estoque.
- **Pendência persistente.** Compensação ou cancelamento permanece recuperável. A equipe acompanha tentativas, próximo retry, efeito confirmado, erro sanitizado e correlação, conforme a seção 10 do documento 06.

## 5. Diagramas complementares

- [Transações no caminho feliz](./diagramas/saga-caminho-feliz.md)
- [Compensação antes do ponto de compromisso](./diagramas/saga-compensacao.md)
- [Cancelamento concorrente com a retirada](./diagramas/saga-cancelamento-retirada.md)
