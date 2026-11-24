# GlicoAcesso — Resumo da arquitetura

O GlicoAcesso organiza a consulta de disponibilidade, a reserva e a retirada presencial de medicamentos e insumos em unidades públicas de saúde. Este resumo acompanha o [diagrama macro](./02-diagrama-arquitetura.md). As regras de referência estão nas [decisões compartilhadas](./00-decisoes-compartilhadas.md).

## 1. Componentes e propriedade dos dados

O API Gateway encaminha cada cliente ao BFF correspondente. Os BFFs chamam os serviços de domínio para consultas e operações locais e acionam o Orquestrador para confirmação ou cancelamento distribuído. O BFF Unidade registra a entrega diretamente em Retiradas.

| Serviço | Responsabilidade e dados próprios |
|---|---|
| Unidades | Cadastro, horários, orientações de retirada e prazo de análise da unidade. |
| Estoque | Catálogo, permissões, saldo, alocações, movimentações e projeção de disponibilidade. |
| Reservas | Solicitações, decisões, estados de negócio e histórico. |
| Retiradas | Autorizações e registro da entrega física. |
| Orquestrador da SAGA | Execuções, etapas, pedidos de cancelamento, tentativas e evidências de reconciliação. |

Cada serviço da tabela possui uma instância PostgreSQL independente. Identificadores entre serviços são referências lógicas. As integrações usam HTTP ou eventos via RabbitMQ.

## 2. Da solicitação à entrega

1. O cidadão consulta unidades e disponibilidade pelo BFF Cidadão. Reservas valida a unidade ativa, o prazo de análise e a permissão canônica de Estoque antes de gravar `SOLICITADA`.
2. O BFF Unidade encaminha o aceite ao Orquestrador. Ele persiste a execução e a intenção inicial. Reservas valida o aceite e grava `EM_CONFIRMACAO`.
3. O Orquestrador pede a Estoque que aloque a quantidade e a Retiradas que prepare a autorização. Quando ambos confirmam, pede a Reservas que grave `CONFIRMADA`. Essa gravação é o ponto de compromisso. O Orquestrador registra a conclusão técnica no próprio banco.
4. No balcão, Retiradas exige `CONFIRMADA` e revalida a autorização antes de registrar a entrega e o evento `retirada.concluida.v1` em sua Outbox.

## 3. Falhas e cancelamento

Uma resposta perdida deixa o resultado incerto. O Orquestrador repete a etapa com a mesma chave e conteúdo para recuperar a resposta original. Antes de `CONFIRMADA`, falhas definitivas podem exigir compensação em ordem inversa. Após `CONFIRMADA`, uma falha na comunicação exige recuperar a conclusão técnica.

Rejeição e cancelamento de solicitação pendente sem efeitos distribuídos são operações locais em Reservas. O cancelamento distribuído tem execução própria. Retiradas serializa revogação e entrega. Se a revogação vencer, sua confirmação permite liberar a alocação. Se a entrega vencer, o Orquestrador encerra o cancelamento como `INTERROMPIDA` e preserva a alocação para a baixa física.

## 4. Eventos e CQRS

Estoque e Retiradas gravam seus eventos pela Outbox junto do efeito local. RabbitMQ entrega cópias da retirada em três filas independentes. Reservas atualiza o estado para `RETIRADA`, Estoque baixa o saldo físico e o Orquestrador reconcilia eventual cancelamento. Cada consumidor deduplica o evento em sua Inbox.

Em Estoque, a escrita canônica valida alocações. A projeção de disponibilidade tem fila própria e aplica os eventos de Estoque por versão, em tabelas distintas da mesma instância PostgreSQL. A meta de atualização é de cerca de cinco segundos em condições normais. `atualizadoEm` informa o instante do estado exibido.

## 5. APIs e HATEOAS

Os BFFs mantêm as rotas públicas em `/api/cidadao/v1` e `/api/unidade/v1`. O [contrato do Orquestrador](./api/orquestrador.yaml) define as operações internas em `/internal/v1`. Os BFFs retornam `200` para decisão ou cancelamento concluído localmente e `202` com `Location` para pedidos distribuídos persistidos. O endereço permite acompanhar a reserva. Os [links HATEOAS](./07-hateoas.md) indicam as ações disponíveis para cada ator e estado.

## 6. Mapa da documentação

O índice abaixo usa os nomes reais dos arquivos atuais. O documento 00 é a base transversal; os documentos temáticos atuais vão de 01 a 12.

| Documento | O que responde |
|---|---|
| [00 — Decisões compartilhadas](./00-decisoes-compartilhadas.md) | Vocabulário, estados, fronteiras, eventos e regras comuns. |
| [01 — Microsserviços](./01-microsservicos.md) | Responsabilidades, propriedade dos dados e justificativa das fronteiras. |
| [02 — Diagrama de arquitetura](./02-diagrama-arquitetura.md) | Componentes, bancos e comunicação entre serviços. |
| [03 — API Gateway](./03-api-gateway.md) | Rotas externas e internas, autenticação e papel do Gateway. |
| [04 — BFFs](./04-bffs.md) | Agregações e diferenças entre as visões do cidadão e da unidade. |
| [05 — Fluxo de reservas](./05-fluxo-reservas.md) | Jornada da solicitação, decisão, cancelamento e retirada. |
| [06 — SAGA](./06-saga.md) | Orquestração, compensações, cancelamento e recuperação. |
| [07 — HATEOAS](./07-hateoas.md) | Links e ações do recurso Reserva por estado e ator. |
| [08 — SAGA complementar](./08-saga.md) | Detalhes complementares de recuperação e falhas da SAGA. |
| [09 — Bancos](./09-bancos.md) | Estruturas, integridade e isolamento dos cinco bancos. |
| [10 — Consistência](./10-consistencia.md) | Consistência local e eventual, dual write e riscos. |
| [11 — Outbox e Inbox](./11-outbox.md) | Persistência, publicação, consumo e catálogo de eventos. |
| [12 — CQRS](./12-cqrs.md) | Projeção de disponibilidade, defasagem e reconstrução. |

[Contratos OpenAPI](./api/) · [Diagramas de sequência](./diagramas/)

## 7. Estado da implementação

Os documentos e contratos especificam a arquitetura da Parte 2. A aplicação executável e as demonstrações das etapas seguintes ainda precisam ser entregues. A configuração física do Gateway, as credenciais entre serviços, os detalhes de implantação e os parâmetros operacionais de retomada ficam para a implementação.
