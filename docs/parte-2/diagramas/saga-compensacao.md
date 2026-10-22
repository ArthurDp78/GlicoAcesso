
# GlicoAcesso - SAGA: compensação após falha de finalização

**Referências:** [08 - Especificação complementar da SAGA](../08-saga.md), [06 - SAGA de confirmação e cancelamento](../06-saga.md) e contratos OpenAPI de [Reservas](../api/reserva.yaml), [Estoque](../api/estoque.yaml) e [Retiradas](../api/retirada.yaml).

Este cenário considera alocação e autorização confirmadas, mas uma falha definitiva na finalização local da reserva. Reservas primeiro reconcilia que `CONFIRMADA` não foi persistida, registra a compensação e desfaz os efeitos na ordem inversa.

Se a preparação da autorização for rejeitada definitivamente antes de criar autorização, não há autorização a cancelar: Reservas libera a alocação e só conclui após confirmar essa liberação.

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

    Note over P,DBR: Etapa 1 - Inicio da confirmacao

    P->>G: POST /api/unidade/v1/reservas/:reservaId/decisao
    G->>B: Encaminhar decisao autorizada
    B->>R: Decisao ACEITAR
    R->>DBR: Gravar EM_CONFIRMACAO e SAGA EM_EXECUCAO
    DBR-->>R: Commit local confirmado
    R-->>B: 200 - Decisao registrada
    B-->>G: Confirmacao em andamento
    G-->>P: Reserva EM_CONFIRMACAO

    Note over R,DBE: Etapa 2 - Alocacao de estoque

    R->>E: POST /internal/v1/alocacoes
    Note over R,E: Comando com sagaId, reservaId, itemId, unidadeId, quantidade e Idempotency-Key
    E->>DBE: Validar saldo e persistir alocacao
    DBE-->>E: Commit local confirmado
    E-->>R: 201 - Alocacao confirmada
    R->>DBR: Persistir efeito de alocacao
    DBR-->>R: Commit confirmado

    Note over R,DBT: Etapa 3 - Preparacao da autorizacao

    R->>T: POST /internal/v1/autorizacoes
    Note over R,T: Comando com sagaId, reservaId, itemId, unidadeId, quantidade e Idempotency-Key
    T->>DBT: Persistir autorizacao vinculada a reserva
    DBT-->>T: Commit local confirmado
    T-->>R: 201 - Autorizacao criada
    R->>DBR: Persistir efeito de autorizacao
    DBR-->>R: Commit confirmado

    Note over R,DBR: Etapa 4 - Falha definitiva na finalizacao

    R->>DBR: Tentar gravar CONFIRMADA e SAGA CONCLUIDA
    DBR-->>R: Falha definitiva de persistencia
    R->>DBR: Reconciliar estado local
    DBR-->>R: CONFIRMADA nao foi persistida
    R->>DBR: Registrar SAGA COMPENSANDO
    DBR-->>R: Compensacao registrada

    Note over R,DBT: Etapa 5 - Compensar autorizacao

    R->>T: POST /internal/v1/autorizacoes/:reservaId/cancelar
    Note over R,T: Comando com Idempotency-Key propria

    alt Cancelamento confirmado
        T->>DBT: Revogar autorizacao e preservar historico
        DBT-->>T: Commit local confirmado
        T-->>R: 200 - Autorizacao revogada
    else Cancelamento temporariamente indisponivel
        T--xR: Sem resposta conclusiva
        R->>DBR: Persistir COMPENSACAO_PENDENTE
        DBR-->>R: Reserva permanece EM_CONFIRMACAO

        Note over R,E: Nao liberar estoque antes de confirmar a revogacao

        R->>T: Repetir cancelamento com mesma Idempotency-Key
        T->>DBT: Recuperar resultado ou concluir revogacao
        DBT-->>T: Revogacao confirmada
        T-->>R: 200 - Autorizacao revogada
    end

    Note over R,DBE: Etapa 6 - Compensar alocacao

    R->>DBR: Registrar cancelamento confirmado e proxima etapa
    DBR-->>R: Commit confirmado
    R->>E: DELETE /internal/v1/alocacoes/:reservaId
    Note over R,E: Comando com Idempotency-Key propria
    E->>DBE: Liberar somente a alocacao desta reserva
    DBE-->>E: Commit local confirmado
    E-->>R: 204 - Alocacao liberada

    Note over R,DBR: Etapa 7 - Finalizar compensacao

    R->>DBR: Gravar SAGA COMPENSADA e FALHA_CONFIRMACAO
    DBR-->>R: Commit local confirmado

    Note over P,R: Consulta posterior da reserva

    P->>G: GET /api/unidade/v1/painel/reservas/:reservaId
    G->>B: Consultar reserva
    B->>R: Consultar estado
    R-->>B: Reserva FALHA_CONFIRMACAO
    B-->>G: Reserva FALHA_CONFIRMACAO
    G-->>P: Confirmacao nao concluida
```

Timeout ou perda de resposta em qualquer comando deixa o resultado incerto. Reservas não presume que a operação falhou nem inicia a etapa seguinte sem reconciliação: repete o mesmo comando com a mesma `Idempotency-Key` e conteúdo para recuperar status e corpo originais.

Se uma compensação permanecer pendente, a reserva continua `EM_CONFIRMACAO`. A transição para `FALHA_CONFIRMACAO` só ocorre após a confirmação de todas as compensações obrigatórias.

A entrega física não faz parte deste fluxo.
