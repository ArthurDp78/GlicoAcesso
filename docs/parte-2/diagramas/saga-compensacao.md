# GlicoAcesso - SAGA de confirmação: compensação antes do ponto de compromisso

Este cenário exige evidência conclusiva de que a finalização falhou antes de gravar `CONFIRMADA`. Perda de resposta exige recuperação por repetição idempotente.

[Especificação da SAGA](../06-saga.md) · [Recuperação e compensações](../08-saga.md)

```mermaid
sequenceDiagram
    participant O as Orquestrador
    participant R as Reservas
    participant E as Estoque
    participant T as Retiradas
    Note over O,T: Alocação e autorização confirmadas
    O->>R: FinalizarConfirmacao
    R-->>O: Falha definitiva sem gravação de CONFIRMADA
    O->>O: Persistir falha e intenção de revogação
    O->>T: CancelarAutorizacao com chave de compensação
    opt Resultado da revogação incerto
        O->>O: Registrar COMPENSACAO_PENDENTE
        O->>T: Repetir revogação com mesma chave e conteúdo
    end
    T-->>O: Revogação confirmada
    O->>O: Persistir revogação e intenção de liberar
    O->>E: LiberarAlocacao com chave própria
    E-->>O: Liberação confirmada
    O->>R: Solicitar FALHA_CONFIRMACAO
    R-->>O: Falha gravada
    O->>O: Gravar COMPENSADA
```
