# GlicoAcesso — SAGA: compensação após falha de finalização

**Referências:** [05 — Especificação complementar da SAGA](../05-saga.md), [04 — SAGA de confirmação e cancelamento](../04-saga.md) e contratos OpenAPI de [Reservas](../api/reserva.yaml), [Estoque](../api/estoque.yaml) e [Retiradas](../api/retirada.yaml).

Este cenário considera alocação e autorização confirmadas, mas uma falha definitiva na finalização local da reserva. Reservas primeiro reconcilia que `CONFIRMADA` não foi persistida, registra a compensação e desfaz os efeitos na ordem inversa. Se a preparação da autorização for rejeitada definitivamente antes de criar autorização, não há autorização a cancelar: Reservas libera a alocação e só conclui após confirmar essa liberação.

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
    R->>DBR: Transação local: gravar EM_CONFIRMACAO e SAGA EM_EXECUCAO
    DBR-->>R: Commit confirmado
    R-->>B: 200 — decisão registrada; confirmação em andamento
    B-->>G: Resultado da decisão
    G-->>P: Reserva em EM_CONFIRMACAO

    R->>E: POST /internal/v1/alocacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    E->>DBE: Validar saldo canônico e persistir alocação
    DBE-->>E: Commit local confirmado
    E-->>R: 201 — alocação criada/confirmada
    R->>DBR: Persistir efeito de alocação confirmado
    DBR-->>R: Commit confirmado

    R->>T: POST /internal/v1/autorizacoes (sagaId, reservaId, unidadeId, itemId, quantidade, idempotencyKey)
    T->>DBT: Persistir autorização vinculada à reserva
    DBT-->>T: Commit local confirmado
    T-->>R: 201 — autorização criada
    R->>DBR: Persistir efeito de autorização confirmado
    DBR-->>R: Commit confirmado

    R->>DBR: Tentar finalizar reserva CONFIRMADA e SAGA CONCLUIDA
    DBR-->>R: Falha definitiva de persistência
    R->>DBR: Reconciliar estado local e confirmar que CONFIRMADA não foi gravada
    DBR-->>R: Reserva segue EM_CONFIRMACAO; confirmação não persistida
    R->>DBR: Persistir SAGA COMPENSANDO e etapa CancelarAutorizacao
    DBR-->>R: Compensação registrada

    R->>T: POST /internal/v1/autorizacoes/{reservaId}/cancelar (X-Idempotency-Key)
    alt Retiradas confirma cancelamento
        T->>DBT: Revogar autorização, preservando histórico
        DBT-->>T: Commit da revogação confirmado
        T-->>R: 200 — autorização revogada
        R->>DBR: Persistir cancelamento confirmado e próxima etapa LiberarAlocacao
        DBR-->>R: Commit confirmado
        R->>E: DELETE /internal/v1/alocacoes/{reservaId} (X-Idempotency-Key)
        E->>DBE: Liberar somente a alocação desta reserva
        DBE-->>E: Commit da liberação confirmado
        E-->>R: 204 — alocação liberada
        R->>DBR: Persistir liberação confirmada; SAGA COMPENSADA; reserva FALHA_CONFIRMACAO
        DBR-->>R: Commit confirmado
        R-->>B: Resultado final FALHA_CONFIRMACAO
        B-->>G: Resultado conforme representação pública
        G-->>P: Confirmação não concluída
    else Cancelamento temporariamente indisponível ou resultado incerto
        T--xR: Sem resposta conclusiva ou falha transitória
        R->>DBR: Persistir COMPENSACAO_PENDENTE e tentativa de cancelamento
        DBR-->>R: Pendência durável; reserva continua EM_CONFIRMACAO
        Note over R,E: Não liberar estoque enquanto o cancelamento não estiver confirmado.
        R->>T: Repetir POST cancelar com a mesma X-Idempotency-Key
        T->>DBT: Confirmar/repetir revogação idempotente
        DBT-->>T: Revogação confirmada
        T-->>R: 200 — autorização revogada
        R->>DBR: Persistir cancelamento confirmado e próxima etapa LiberarAlocacao
        DBR-->>R: Commit confirmado
        R->>E: DELETE /internal/v1/alocacoes/{reservaId} (X-Idempotency-Key)
        E->>DBE: Liberar somente a alocação desta reserva
        DBE-->>E: Commit da liberação confirmado
        E-->>R: 204 — alocação liberada
        R->>DBR: Persistir liberação confirmada; SAGA COMPENSADA; reserva FALHA_CONFIRMACAO
        DBR-->>R: Commit confirmado
        R-->>B: Resultado final FALHA_CONFIRMACAO
        B-->>G: Resultado conforme representação pública
        G-->>P: Confirmação não concluída
    end
```

Timeout ou perda de resposta em qualquer comando deixa o resultado incerto. Reservas não presume que a operação falhou nem inicia a etapa seguinte sem reconciliação. A repetição usa a mesma chave idempotente, conforme a regra arquitetural cuja implementação precisa ser confirmada nos participantes; os contratos atuais não definem endpoint de consulta do resultado por `reservaId`. A reserva só passa de `EM_CONFIRMACAO` para `FALHA_CONFIRMACAO` depois que os resultados relevantes estiverem resolvidos e as compensações obrigatórias tiverem sido confirmadas. A entrega física não faz parte deste fluxo.
