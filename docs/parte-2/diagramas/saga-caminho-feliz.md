# GlicoAcesso - SAGA: caminho feliz da confirmação

**Referências:** [08 - Especificação complementar da SAGA](../08-saga.md), [06 - SAGA de confirmação e cancelamento](../06-saga.md) e contratos OpenAPI de [Reservas](../api/reserva.yaml), [Estoque](../api/estoque.yaml) e [Retiradas](../api/retirada.yaml).

O profissional aceita uma solicitação `SOLICITADA`. Reservas registra a execução e coordena os comandos internos. A reserva só fica `CONFIRMADA` após Estoque confirmar a alocação, Retiradas persistir a autorização e Reservas gravar a finalização. A autorização criada não basta para entregar: no balcão, Retiradas consulta o estado canônico de Reservas e exige `CONFIRMADA`. Este diagrama mostra somente a SAGA de confirmação.

```mermaid
sequenceDiagram
    actor P as Profissional da unidade
    participant G as API Gateway
    participant B as BFF Unidade
    participant R as Reservas (orquestrador)
    participant DBR as Banco de Reservas
    participant E as Estoque
    participant DBE as Banco de Estoque
    participant T as Retiradas
    participant DBT as Banco de Retiradas

    P->>G: POST /api/unidade/v1/reservas/{reservaId}/decisao
    G->>B: Encaminhar decisão autorizada
    B->>R: POST decisão, corpo {decisao: ACEITAR}
    R->>DBR: Transação local: validar SOLICITADA#59; gravar EM_CONFIRMACAO e SAGA EM_EXECUCAO
    DBR-->>R: Commit confirmado
    R-->>B: 200 — decisão registrada#59; confirmação em andamento
    B-->>G: Resultado da decisão
    G-->>P: Reserva em EM_CONFIRMACAO

    R->>E: POST /internal/v1/alocacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    E->>DBE: Validar saldo canônico e persistir alocação
    DBE-->>E: Commit local confirmado
    E-->>R: 201 — alocação criada/confirmada
    R->>DBR: Persistir etapa e efeito de alocação confirmados
    DBR-->>R: Commit confirmado

    R->>T: POST /internal/v1/autorizacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    T->>DBT: Persistir autorização vinculada à reserva (entrega exige consulta posterior)
    DBT-->>T: Commit local confirmado
    T-->>R: 201 — autorização criada
    R->>DBR: Persistir etapa e efeito de autorização confirmados
    DBR-->>R: Commit confirmado

    R->>DBR: Transação local: gravar reserva CONFIRMADA e SAGA CONCLUIDA
    DBR-->>R: Commit confirmado
    R-->>B: Resultado final CONFIRMADA
    B-->>G: Resposta conforme representação pública da reserva
    G-->>P: Reserva CONFIRMADA
```

Cada persistência ocorre no banco do serviço proprietário; não há transação compartilhada. Timeout nos comandos é resultado incerto e exige repetição idempotente para reconciliar os efeitos. O GET de estado de Reservas valida a entrega posterior e não consulta os resultados de alocação ou autorização nos participantes.
