# GlicoAcesso - SAGA de cancelamento: disputa com a retirada

O BFF do ator autorizado encaminha o pedido de cancelamento distribuído ao Orquestrador. O diagrama detalha a disputa em Retiradas. Os três consumidores recebem cópias independentes, sem ordem global de entrega. O evento pode chegar ao Orquestrador antes ou depois da resposta do comando.

[Especificação da SAGA](../06-saga.md) · [Recuperação e compensações](../08-saga.md)

```mermaid
sequenceDiagram
    participant B as BFF Unidade
    participant C as BFF do solicitante do cancelamento
    participant O as Orquestrador
    participant R as Reservas
    participant T as Retiradas
    participant E as Estoque
    participant Q as RabbitMQ
    B->>T: Solicitar registro da entrega
    T->>R: Consultar estado canônico
    R-->>T: CONFIRMADA
    Note over R,T: Consulta anterior ao cancelamento, sem lock remoto
    C->>R: Solicitar cancelamento com chave idempotente
    R-->>C: CANCELAMENTO_DISTRIBUIDO
    C->>O: Encaminhar cancelamento
    O->>O: Registrar pedido distribuído e intenção
    O-->>C: Pedido registrado para processamento
    O->>R: Solicitar início do cancelamento autorizado
    R-->>O: CANCELAMENTO_EM_ANDAMENTO
    alt Revogação vence a disputa local
        O->>T: CancelarAutorizacao
        T->>T: Revogar autorização na transação local
        T-->>O: Revogação confirmada
        T-->>B: Entrega recusada
        O->>E: LiberarAlocacao
        E-->>O: Liberação confirmada
        O->>R: Finalizar cancelamento
        R-->>O: CANCELADA
        O->>O: Registrar execução CANCELADA
    else Entrega vence a disputa local
        T->>T: Gravar entrega e Outbox na mesma transação
        T-->>B: Entrega registrada
        O->>T: CancelarAutorizacao
        T-->>O: ENTREGA_JA_REGISTRADA com retiradaId
        O->>O: Registrar INTERROMPIDA e preservar alocação
        T-->>Q: Publicar retirada.concluida.v1 pela Outbox
        Q-->>R: Cópia da fila de Reservas
        R->>R: Deduplicar e gravar RETIRADA
        Q-->>E: Cópia da fila de Estoque
        E->>E: Deduplicar, baixar saldo e consumir alocação
        Q-->>O: Cópia da fila do Orquestrador
        O->>O: Deduplicar e reconciliar o encerramento
    end
```
