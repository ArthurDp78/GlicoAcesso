# GlicoAcesso — SAGA: falha e compensação

**Referência:** [04 — SAGA de confirmação e cancelamento](../04-saga.md)

O diagrama mostra falhas definitivas possíveis. Timeout ou falha transitória não inicia compensação enquanto o resultado estiver incerto: Reservas consulta o participante ou repete o mesmo comando idempotente.

```mermaid
sequenceDiagram
    actor Profissional
    participant R as Reservas (coordenador)
    participant E as Estoque
    participant T as Retiradas

    Profissional->>R: Aceitar reserva
    R->>R: Persistir EM_CONFIRMACAO e SAGA EM_EXECUCAO
    R->>E: AlocarEstoque(reservaId, ...)
    alt Estoque rejeita por regra de negócio
        E-->>R: Rejeição definitiva (ex.: saldo insuficiente)
        R->>R: Reserva FALHA_CONFIRMACAO; SAGA COMPENSADA
    else Estoque confirma alocação
        E-->>R: Alocação confirmada
        R->>T: PrepararAutorizacao(reservaId, ...)
        alt Retiradas rejeita definitivamente
            T-->>R: Preparação rejeitada
            R->>E: LiberarAlocacao(reservaId)
            E->>E: Liberar somente a alocação desta reserva
            E-->>R: Liberação confirmada
            R->>R: Reserva FALHA_CONFIRMACAO; SAGA COMPENSADA
        else Retiradas confirma autorização
            T-->>R: Autorização confirmada
            R->>R: Finalização local falha de forma definitiva
            R->>T: CancelarAutorizacao(reservaId)
            T->>T: Revogar autorização sem apagar histórico
            T-->>R: Cancelamento confirmado
            R->>E: LiberarAlocacao(reservaId)
            E-->>R: Liberação confirmada
            R->>R: Reserva FALHA_CONFIRMACAO; SAGA COMPENSADA
        end
    end
```

Se uma compensação falhar ou tiver resultado incerto, Reservas mantém a execução pendente como `COMPENSACAO_PENDENTE`, persiste a etapa e tenta reconciliar/repetir. Não marca `FALHA_CONFIRMACAO` enquanto um efeito confirmado ainda não tiver sido compensado.