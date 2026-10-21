# GlicoAcesso - SAGA: caminho de sucesso

**Referência:** [06 - SAGA de confirmação e cancelamento](../06-saga.md)

Este diagrama mostra a confirmação após o profissional aceitar uma solicitação `SOLICITADA`. O estado só vira `CONFIRMADA` depois que Estoque confirma a alocação, Retiradas persiste a autorização e Reservas grava a finalização local. A autorização não permite entrega por si só: no balcão, Retiradas exige consulta canônica de `CONFIRMADA` e revalida a autorização local.

```mermaid
sequenceDiagram
    actor Profissional
    participant R as Reservas (coordenador)
    participant E as Estoque
    participant T as Retiradas

    Profissional->>R: Aceitar reserva (reservaId)
    R->>R: Transação local: EM_CONFIRMACAO + SAGA EM_EXECUCAO
    R->>E: AlocarEstoque(reservaId, unidadeId, itemId, quantidade)
    E->>E: Validar saldo canônico e criar alocação
    E-->>R: Alocação confirmada
    R->>T: PrepararAutorizacao(reservaId, unidadeId, itemId, quantidade)
    T->>T: Criar autorização de balcão
    T-->>R: Autorização confirmada
    R->>R: Transação local: reserva CONFIRMADA + SAGA CONCLUIDA
    R-->>Profissional: Confirmação concluída
```

AlocarEstoque e PrepararAutorizacao são comandos internos idempotentes. As chamadas e gravações pertencem aos serviços correspondentes; não existe transação compartilhada.