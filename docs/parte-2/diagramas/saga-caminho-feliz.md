
# GlicoAcesso - SAGA: caminho feliz da confirmação

**Referências:** [08 - Especificação complementar da SAGA](../08-saga.md), [06 - SAGA de confirmação e cancelamento](../06-saga.md) e contratos OpenAPI de [Reservas](../api/reserva.yaml), [Estoque](../api/estoque.yaml) e [Retiradas](../api/retirada.yaml).

O profissional aceita uma solicitação `SOLICITADA`. Reservas registra a execução e coordena os comandos internos. A reserva só fica `CONFIRMADA` após Estoque confirmar a alocação, Retiradas persistir a autorização e Reservas gravar a finalização.

A autorização criada não basta para entregar: no balcão, Retiradas consulta o estado canônico de Reservas e exige `CONFIRMADA`.

Este diagrama mostra somente a SAGA de confirmação.

```mermaid
sequenceDiagram
    actor P as Profissional da unidade
    participant G as API Gateway
    participant B as BFF Unidade
    participant R as Reservas - Orquestrador
    participant DBR as Banco de Reservas
    participant E as Estoque
    participant DBE as Banco de Estoque
    participant T as Retiradas
    participant DBT as Banco de Retiradas

    P->>G: POST /api/unidade/v1/reservas/:reservaId/decisao
    G->>B: Encaminhar decisao autorizada
    B->>R: POST decisao ACEITAR

    Note over R,DBR: Inicio da SAGA
    R->>DBR: Validar SOLICITADA e registrar EM_CONFIRMACAO
    R->>DBR: Criar SAGA com estado EM_EXECUCAO
    DBR-->>R: Commit local confirmado

    R-->>B: 200 - Decisao registrada
    B-->>G: Confirmacao em andamento
    G-->>P: Reserva EM_CONFIRMACAO

    Note over R,DBE: Etapa 1 - Alocacao de estoque
    R->>E: POST /internal/v1/alocacoes
    Note right of R: Envia sagaId, reservaId, unidadeId, itemId, quantidade e Idempotency-Key
    E->>DBE: Validar saldo canonico e persistir alocacao
    DBE-->>E: Commit local confirmado
    E-->>R: 201 - Alocacao confirmada
    R->>DBR: Persistir alocacao confirmada
    DBR-->>R: Commit confirmado

    Note over R,DBT: Etapa 2 - Preparacao da autorizacao
    R->>T: POST /internal/v1/autorizacoes
    Note right of R: Envia sagaId, reservaId, unidadeId, itemId, quantidade e Idempotency-Key
    T->>DBT: Persistir autorizacao vinculada a reserva
    DBT-->>T: Commit local confirmado
    T-->>R: 201 - Autorizacao criada
    R->>DBR: Persistir autorizacao confirmada
    DBR-->>R: Commit confirmado

    Note over R,DBR: Etapa 3 - Finalizacao da SAGA
    R->>DBR: Gravar reserva CONFIRMADA e SAGA CONCLUIDA
    DBR-->>R: Commit local confirmado

    Note over P,R: Consulta posterior da reserva
    P->>G: GET /api/unidade/v1/painel/reservas/:reservaId
    G->>B: Consultar reserva
    B->>R: Consultar estado da reserva
    R-->>B: Reserva CONFIRMADA
    B-->>G: Reserva CONFIRMADA
    G-->>P: Reserva CONFIRMADA
```

Cada persistência ocorre no banco do serviço proprietário; não há transação compartilhada.

Timeout nos comandos é resultado incerto e exige repetição do mesmo comando com a mesma `Idempotency-Key` e conteúdo para recuperar o resultado original.

O GET de estado de Reservas valida a entrega posterior e não consulta os resultados dos comandos de alocação ou autorização.
