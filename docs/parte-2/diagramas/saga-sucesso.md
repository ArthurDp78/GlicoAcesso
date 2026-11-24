# GlicoAcesso - SAGA de confirmação: caminho de sucesso

A aceitação do pedido para processamento antecede o resultado consultado em Reservas. Cada etapa usa uma intenção durável e resultado idempotente.

[Especificação da SAGA](../06-saga.md) · [Recuperação e compensações](../08-saga.md)

```mermaid
sequenceDiagram
    participant B as BFF Unidade
    participant O as Orquestrador
    participant R as Reservas
    participant E as Estoque
    participant T as Retiradas
    B->>R: Consultar decisão idempotente para ACEITAR
    R-->>B: ACEITE_ENCAMINHAR sem alterar a reserva
    B->>O: Encaminhar aceite do profissional
    O->>O: Persistir execução e intenção do primeiro comando
    O-->>B: Pedido registrado para processamento
    O->>R: AceitarReserva
    R-->>O: Aceite gravado em EM_CONFIRMACAO
    O->>E: AlocarEstoque
    E-->>O: Alocação confirmada
    O->>T: PrepararAutorizacao
    T-->>O: Autorização confirmada
    O->>R: FinalizarConfirmacao
    R->>R: Gravar CONFIRMADA como ponto de compromisso
    R-->>O: Finalização confirmada
    O->>O: Gravar CONCLUIDA
```
