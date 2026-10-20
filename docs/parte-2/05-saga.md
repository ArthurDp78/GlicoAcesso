# GlicoAcesso — Especificação complementar da SAGA

**Etapa:** 2 — Arquitetura
**Documento:** 05 — SAGA
**Escopo:** confirmação orquestrada de uma reserva
**Documento normativo:** [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md)
**Especificação existente:** [04 — SAGA de confirmação e cancelamento](./04-saga.md)
**Fluxo de negócio:** [03 — Fluxo de reservas](./03-fluxo-reservas.md)
**Contratos:** [Reservas](./api/reserva.yaml), [Estoque](./api/estoque.yaml) e [Retiradas](./api/retirada.yaml)

> Este documento organiza os requisitos de avaliação da SAGA de confirmação em uma especificação complementar. O documento 04 continua sendo a referência detalhada para cancelamento, estados duráveis, concorrência e operação. Em caso de divergência, prevalecem as decisões compartilhadas do documento 00 e os contratos OpenAPI vigentes.

## 1. Objetivo e limites

A SAGA coordena a confirmação de uma solicitação aceita pela unidade. Reservas inicia e persiste a execução, Estoque aloca a quantidade solicitada, Retiradas prepara a autorização de balcão e Reservas finaliza a reserva somente depois de confirmar as etapas obrigatórias.

A transação não realiza a entrega física. A retirada ocorre posteriormente pelo fluxo de Retiradas e pelo evento `retirada.concluida.v1`. Disponibilidade consultada é uma informação potencialmente defasada; a alocação no modelo de escrita de Estoque é a validação efetiva.

Não existe transação ACID distribuída. Cada serviço grava apenas no próprio banco. RabbitMQ e Outbox propagam fatos e atualizam projeções, mas não substituem os comandos nem a decisão explícita do orquestrador.

## 2. Participantes e escolha da orquestração

| Participante | Papel nesta confirmação |
|---|---|
| Profissional da unidade | Aceita a solicitação por meio da operação pública de decisão. Não coordena as etapas distribuídas. |
| Reservas | Orquestrador: registra a execução, escolhe e ordena as etapas, interpreta respostas, reconcilia incertezas e inicia compensações. |
| Estoque | Valida o saldo canônico e cria ou libera a alocação vinculada a `reservaId`. |
| Retiradas | Prepara ou revoga a autorização vinculada à reserva; não registra entrega durante a SAGA de confirmação. |

A variante orquestrada é adequada porque o fluxo possui ordem explícita e um ponto claro de decisão: uma autorização só deve ser preparada depois da alocação, e a reserva só pode ser confirmada depois de ambas. Um coordenador em Reservas mantém o progresso recuperável e decide quando continuar, repetir, reconciliar ou compensar. Na coreografia, cada participante teria de reagir a eventos para determinar o próximo passo, distribuindo a política de conclusão e falha entre serviços.

Esta escolha não concede a Reservas acesso aos bancos dos participantes. Cada serviço continua responsável pela integridade local dos próprios dados.

## 3. Pré-condições, sequência e resultados

### 3.1 Pré-condições

Reservas só inicia a confirmação quando a solicitação existe e está `SOLICITADA`, o profissional pode decidir pela unidade correspondente, a decisão vence a concorrência com a expiração e não há outra execução ativa para `reservaId`. O aceite, a transição para `EM_CONFIRMACAO` e a criação durável da execução devem ser confirmados na transação local de Reservas antes de qualquer comando remoto.

### 3.2 Caminho de confirmação

| Etapa | Operação | Resultado necessário para avançar |
|---|---|---|
| 0 — Iniciar | Reservas aceita a decisão `ACEITAR`, grava `EM_CONFIRMACAO` e cria a execução `EM_EXECUCAO`. | Persistência local confirmada. |
| 1 — Alocar | Reservas envia a Estoque os dados da reserva e a chave idempotente. | Estoque confirma a alocação no próprio banco. |
| 2 — Autorizar | Reservas envia a Retiradas os dados da reserva e a chave idempotente. | Retiradas confirma a autorização no próprio banco. |
| 3 — Finalizar | Reservas grava `CONFIRMADA` e `CONCLUIDA` em transação local. | Persistência local confirmada após as duas respostas de sucesso. |

**Pós-condição de sucesso:** há uma alocação ativa e uma autorização persistida vinculadas à reserva; Reservas registra `status = CONFIRMADA` e execução concluída. No momento da entrega, Retiradas ainda exige consulta canônica de `CONFIRMADA` e revalida a autorização local, conforme o documento 00, seção 9.8.

**Pós-condição de falha definitiva:** a reserva só pode passar de `EM_CONFIRMACAO` para `FALHA_CONFIRMACAO` quando todos os resultados relevantes estiverem resolvidos e todos os efeitos distribuídos confirmados tiverem sido compensados. Se não houve efeito distribuído, não há operação remota a compensar; aplica-se a convenção canônica de encerrar a SAGA como `COMPENSADA` e a reserva como `FALHA_CONFIRMACAO`. Se houver efeito, a execução permanece não terminal até a respectiva compensação ser confirmada.

Falhas podem ocorrer ao persistir a inicialização, alocar, preparar a autorização, receber respostas, persistir o resultado remoto no registro da SAGA ou finalizar localmente. Falha técnica, timeout e perda de conexão não demonstram, por si sós, que a operação remota não ocorreu.

### 3.3 Operações locais e distribuídas

- **Locais a Reservas:** decisão e transições da reserva; criação e atualização do registro da execução; registro de tentativas, resultados, efeitos e compensações; finalização.
- **Remotas entre limites de serviço:** `AlocarEstoque`, `PrepararAutorizacao` e, quando necessário, as compensações `CancelarAutorizacao` e `LiberarAlocacao`.
- **Locais aos participantes:** gravação da alocação em Estoque e da autorização em Retiradas. Nenhum participante grava no banco de Reservas.

## 4. Contratos usados e limites das garantias

Os caminhos abaixo são os declarados nos OpenAPI atuais. Os nomes das operações são rótulos explicativos, não endpoints adicionais.

| Operação | Contrato e método | Dados documentados | Respostas documentadas |
|---|---|---|---|
| Aceitar solicitação | Reservas: `POST /api/unidade/v1/reservas/{reservaId}/decisao` | Path `reservaId`; corpo com `decisao: ACEITAR` ou `REJEITAR` | `200`; `403` se o profissional não pertence à unidade |
| Alocar estoque | Estoque: `POST /internal/v1/alocacoes` | `sagaId`, `reservaId`, `unidadeId`, `itemId`, `quantidade`, `idempotencyKey` | `201`; `409` para saldo insuficiente ou conflito |
| Liberar alocação | Estoque: `DELETE /internal/v1/alocacoes/{reservaId}` | Path `reservaId`; header `X-Idempotency-Key` | `204` |
| Preparar autorização | Retiradas: `POST /internal/v1/autorizacoes` | `sagaId`, `reservaId`, `unidadeId`, `itemId`, `quantidade`, `idempotencyKey` | `201` |
| Cancelar autorização | Retiradas: `POST /internal/v1/autorizacoes/{reservaId}/cancelar` | Path `reservaId`; header `X-Idempotency-Key` | `200`; `409` se a entrega já foi registrada |
| Consultar estado para retirada (fora da SAGA) | Reservas: `GET /internal/v1/reservas/{reservaId}/estado` | Path `reservaId`; identidade de serviço de Retiradas; `X-Correlation-Id` opcional; sem chave idempotente | `200` com `reservaId` e `status`; `401`; `403`; `404`; `503` |

**O que o OpenAPI declara:** caminhos, métodos, campos de entrada e códigos/resumos de resposta listados acima. Os schemas atuais não especificam corpos detalhados de resposta para todos os comandos nem descrevem integralmente a semântica de repetição.

**O que as decisões arquiteturais estabelecem:** os comandos devem ser idempotentes; a alocação e a autorização são únicas por reserva; repetir uma liberação ou cancelamento não duplica efeitos; timeout é resultado incerto; compensações seguem ordem inversa. Essas são regras arquiteturais do documento 00 e da especificação 04, não evidência de implementação executável.

**O que requer implementação ou confirmação da Pessoa 2:** persistir e aplicar as chaves idempotentes no serviço, devolver resultado compatível em retries, detectar chave igual com conteúdo divergente e harmonizar o uso de `idempotencyKey` no corpo dos comandos de criação com `X-Idempotency-Key` nas compensações. Os YAMLs mostram esses campos, mas não comprovam que o comportamento está implementado.

Os YAMLs não especificam consulta do resultado de alocação em Estoque ou de autorização em Retiradas por `reservaId`; após timeout desses comandos, a recuperação depende da repetição idempotente. O GET de estado em Reservas valida a entrega e não reconcilia esses efeitos remotos.

## 5. Estados de negócio e estados da execução

O `status` da reserva é estado de negócio visível e segue o contrato e as decisões compartilhadas. O estado da execução é interno a Reservas e descreve o progresso técnico da coordenação. Um não substitui o outro.

| Situação da execução | Estado de negócio associado |
|---|---|
| Confirmação em execução, inclusive com resultado remoto incerto | `EM_CONFIRMACAO` |
| Compensação em andamento ou pendente | `EM_CONFIRMACAO` |
| Confirmação concluída | `CONFIRMADA` |
| Falha definitiva com todos os efeitos resolvidos e compensações concluídas | `FALHA_CONFIRMACAO` |

Os estados internos documentados em `04-saga.md` incluem `EM_EXECUCAO`, `COMPENSANDO`, `COMPENSACAO_PENDENTE`, `CONCLUIDA` e `COMPENSADA`. O documento também define estados para o fluxo de cancelamento. Esta especificação não cria novos estados canônicos.

Estados de negócio da reserva incluem `SOLICITADA`, `EM_CONFIRMACAO`, `CONFIRMADA`, `CANCELAMENTO_EM_ANDAMENTO`, `CANCELADA`, `REJEITADA`, `EXPIRADA`, `FALHA_CONFIRMACAO` e `RETIRADA`. A lista oficial é a do contrato de Reservas. A execução de confirmação não leva a `RETIRADA`; esse estado depende do processo posterior de entrega.

## 6. Persistência, retomada e idempotência

O registro local da SAGA deve permitir recuperar `sagaId`, `reservaId`, tipo e estado da execução, etapa atual, comandos enviados, resultados confirmados, efeitos existentes, compensações concluídas ou pendentes, tentativas, instante da última atualização e dados de correlação. Credenciais e dados pessoais desnecessários não devem ser armazenados nesse registro.

1. Reservas persiste a decisão e a execução antes de enviar comandos.
2. Antes de chamar um participante, registra a etapa e a chave idempotente que usará.
3. Depois de confirmar um efeito remoto, persiste essa evidência antes de avançar.
4. Após reinício, recupera as execuções não terminais do seu próprio banco e reconcilia a etapa pendente.
5. O envio de uma chamada não é evidência de sucesso. Só resposta conclusiva ou reconciliação idempotente permite registrar o efeito.

Retries da mesma etapa reutilizam a chave idempotente da operação. A decisão arquitetural exige que a repetição com a mesma chave e conteúdo não duplique efeitos e que uma chave igual com conteúdo diferente resulte em conflito. Esse comportamento precisa ser implementado e verificado nos participantes; sua presença nos campos OpenAPI não basta para comprová-lo.

Estoque deve proteger a quantidade no próprio modelo de escrita com operação local atômica ou mecanismo equivalente. O orquestrador sozinho não impede duas reservas concorrentes de alocarem acima do saldo.

## 7. Matriz de falhas e compensações

Uma compensação neutraliza um efeito de negócio já confirmado. Não apaga seu histórico e não equivale a desfazer atomicamente bancos independentes.

| Operação original / cenário | Efeito conhecido | Ação de negócio | Critério para concluir |
|---|---|---|---|
| Início falha antes de persistir a execução | Nenhum efeito remoto deve ter sido enviado | Não chamar participantes; reconciliar a persistência local antes de permitir nova tentativa se o resultado local for incerto | Confirmar se a transação de início foi aceita |
| Estoque rejeita alocação definitivamente por saldo/regra | Nenhuma alocação confirmada | Não chamar Retiradas; sem efeito distribuído, nenhuma compensação remota é necessária | Após resolver o resultado, encerrar conforme a convenção: SAGA `COMPENSADA`, reserva `FALHA_CONFIRMACAO` |
| Estoque confirma e etapa posterior falha definitivamente; não há autorização criada | Alocação ativa | `DELETE /internal/v1/alocacoes/{reservaId}` com chave idempotente | Resposta de liberação confirmada; liberar somente a alocação da reserva |
| Autorização preparada e falha posterior definitiva | Alocação e autorização persistidas | Primeiro cancelar autorização em Retiradas. Só após confirmação, liberar alocação em Estoque | Confirmar cada operação na ordem inversa dos efeitos |
| Preparação da autorização tem resultado incerto | Alocação confirmada; autorização pode existir | Repetir `POST /internal/v1/autorizacoes` com a mesma chave para reconciliar. Se a decisão final for abandonar, cancelar eventual autorização e depois liberar estoque | Não liberar estoque antes de confirmar a revogação da autorização eventualmente criada |
| Cancelamento da autorização falha temporariamente ou fica incerto | Autorização pode continuar sem revogação; alocação ativa | Manter compensação pendente e repetir/reconciliar o cancelamento com a mesma chave. Não chamar a liberação do Estoque ainda | Confirmar a revogação antes de prosseguir |
| Cancelamento da autorização confirmado; liberação do estoque falha ou fica incerta | Autorização revogada; alocação pode continuar ativa | Repetir a liberação idempotente em Estoque | Confirmar a liberação antes de declarar compensação concluída |
| Finalização local falha com resultado incerto | Alocação e autorização confirmadas; `CONFIRMADA` pode já ter sido gravada | Consultar o próprio estado local após recuperar conectividade e repetir a finalização se necessário; não compensar às cegas | Coerência entre reserva e execução após reconciliação |
| Qualquer compensação permanece indisponível | Efeito original pode continuar ativo | Registrar pendência, erro e tentativa; agendar nova tentativa com a mesma chave | Não registrar `COMPENSADA` nem `FALHA_CONFIRMACAO` enquanto faltar confirmação |

Para qualquer compensação:

1. Executá-la somente quando o efeito original tiver sido confirmado ou reconciliado.
2. Identificar o efeito pelo `reservaId`, `sagaId` e chave da operação conforme o comando aplicável.
3. Repetir a mesma compensação com a mesma chave; a garantia arquitetural exige que o serviço proprietário não duplique efeitos nem afete outras reservas.
4. Considerar sucesso somente após resposta conclusiva ou reconciliação idempotente.
5. Tratar timeout como resultado incerto, mantendo a compensação pendente.
6. Registrar erro técnico sanitizado, número de tentativa, horário e próximo retry. Backoff, limite operacional e alertas são parâmetros a definir pela equipe.
7. Encaminhar para reconciliação operacional quando a pendência persistir além do limite definido ou quando houver conflito que não possa ser resolvido por retry. A intervenção deve usar operação auditada do serviço proprietário, nunca escrita direta no banco de outro serviço.

`COMPENSADA` não pode ser registrada enquanto houver resultado relevante desconhecido ou compensação obrigatória sem confirmação. A reserva não pode passar de `EM_CONFIRMACAO` para `FALHA_CONFIRMACAO` até esses resultados serem resolvidos.

## 8. Recuperação dos principais cenários

### Timeout ou perda de resposta

Timeout, conexão interrompida ou resposta perdida nos comandos da SAGA significam resultado desconhecido. Reservas não presume falha nem compensa às cegas: repete o comando idempotente para reconciliar os efeitos em Estoque ou Retiradas. O GET de estado da Reserva não substitui essa recuperação. Se a consulta falhar no balcão, Retiradas não registra a entrega e uma nova tentativa exige nova consulta.

### Queda e reinício do orquestrador

Após reiniciar, Reservas carrega execuções não terminais do próprio banco. Para uma etapa marcada como enviada sem resultado persistido, considera o efeito incerto e repete o comando idempotente correspondente somente conforme a garantia arquitetural implementada pelo participante. Não avança nem compensa apenas com base no registro de que a chamada foi enviada.

### Falha temporária na compensação

Reservas preserva a execução em compensação pendente, o efeito original e a compensação ainda necessária. A ordem é cancelar autorização em Retiradas, confirmar o cancelamento, liberar a alocação em Estoque e confirmar a liberação. Se o cancelamento estiver incerto ou pendente, Estoque não é liberado. Enquanto isso, a reserva continua `EM_CONFIRMACAO`; não se publica falha final nem estado `COMPENSADA`. Pendências persistentes devem ser observáveis e permitir intervenção operacional auditada.

### Confirmações concorrentes

Reservas permite no máximo uma execução ativa por reserva e usa transições condicionais para concorrência sobre a mesma solicitação. Para reservas diferentes que disputam o mesmo saldo, Estoque deve serializar ou condicionar a atualização no seu modelo de escrita, de modo que a quantidade não fique negativa. A projeção de disponibilidade não é autoridade para alocação.

### Falha ao finalizar localmente

Se a persistência falhar conclusivamente antes de gravar a confirmação, Reservas mantém a execução recuperável e tenta novamente. Se a resposta da persistência for incerta, reconcilia seu próprio registro antes de decidir. Se `CONFIRMADA` já estiver persistida, não inicia compensações que liberariam uma reserva confirmada; se não estiver, continua a finalização ou, diante de falha definitiva, compensa os efeitos confirmados na ordem definida.

## 9. Observabilidade

Reservas deve correlacionar cada execução por `reservaId`, `sagaId` e `correlationId` e registrar etapa, operação, número e instante da tentativa, resultado ou timeout observado, efeito confirmado, estado de compensação, erro técnico sanitizado e timestamps de transição. Isso permite localizar execuções não terminais, participante aguardado, compensações pendentes e casos que precisam de reconciliação.

Detalhes internos, credenciais, stack traces e dados pessoais desnecessários não devem aparecer nas APIs públicas. O cidadão acompanha o estado de negócio da reserva; a operação interna da SAGA é consultada por mecanismos autorizados da equipe.

## 10. Pendências de alinhamento

- **Pessoa 1:** confirmar que este complemento permanece subordinado ao documento normativo 00 e alinhado ao fluxo e aos diagramas existentes.
- **Pessoa 2:** confirmar a semântica e a implementação da idempotência dos comandos; avaliar consultas dos resultados de alocação/autorização, ainda ausentes nos contratos dos participantes; harmonizar `idempotencyKey` no corpo das criações com `X-Idempotency-Key` nas compensações. O GET de estado de Reservas é exclusivo da validação de entrega. O conteúdo concatenado do YAML do BFF Unidade continua pendente de revisão.
- **Pessoa 4:** confirmar como o serviço de Reservas persistirá execução, efeitos confirmados, chaves idempotentes, tentativas, compensações pendentes e retomada após reinício.

## 11. Referências e diagramas complementares

- [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md): fronteiras, estados e identificadores canônicos.
- [03 — Fluxo de reservas](./03-fluxo-reservas.md): fluxo de negócio e estados da reserva.
- [04 — SAGA de confirmação e cancelamento](./04-saga.md): especificação detalhada vigente, inclusive cancelamento distribuído.
- [Diagrama de sucesso existente](./diagramas/saga-sucesso.md) e [diagrama de falha existente](./diagramas/saga-falha.md): representações atuais preservadas.
- [Novo diagrama de caminho feliz](./diagramas/saga-caminho-feliz.md) e [novo diagrama de compensação](./diagramas/saga-compensacao.md): visões focadas nos requisitos desta entrega.
