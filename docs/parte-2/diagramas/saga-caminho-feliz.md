# GlicoAcesso — SAGA: caminho feliz da confirmação

**Referências:** [05 — Especificação complementar da SAGA](../05-saga.md), [04 — SAGA de confirmação e cancelamento](../04-saga.md) e contratos OpenAPI de [Reservas](../api/reserva.yaml), [Estoque](../api/estoque.yaml) e [Retiradas](../api/retirada.yaml).

O profissional aceita uma solicitação `SOLICITADA`. Reservas registra a execução e coordena os comandos internos. A reserva só fica `CONFIRMADA` após Estoque confirmar a alocação, Retiradas confirmar a autorização e Reservas persistir a finalização. Este fluxo não inclui a entrega física.

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
    R->>DBR: Transação local: validar SOLICITADA; gravar EM_CONFIRMACAO e SAGA EM_EXECUCAO
    DBR-->>R: Commit confirmado
    R-->>B: 200 — decisão registrada; confirmação em andamento
    B-->>G: Resultado da decisão
    G-->>P: Reserva em EM_CONFIRMACAO

    R->>E: POST /internal/v1/alocacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    E->>DBE: Validar saldo canônico e persistir alocação
    DBE-->>E: Commit local confirmado
    E-->>R: 201 — alocação criada/confirmada
    R->>DBR: Persistir etapa e efeito de alocação confirmados
    DBR-->>R: Commit confirmado

    R->>T: POST /internal/v1/autorizacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    T->>DBT: Persistir autorização vinculada à reserva
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

Cada persistência ocorre no banco do serviço proprietário; não há transação compartilhada. Se uma chamada interna expirar ou perder a resposta, Reservas trata o resultado como incerto, não avança a etapa e não compensa às cegas. A recuperação depende de repetir o mesmo comando com a chave idempotente estável conforme as decisões arquiteturais e a implementação dos participantes; os contratos atuais não definem endpoint de consulta de estado por `reservaId`.
