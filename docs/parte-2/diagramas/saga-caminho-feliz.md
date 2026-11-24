# GlicoAcesso - SAGA de confirmação: persistência e retomada

As gravações do Orquestrador e dos participantes ocorrem em transações separadas. A última etapa inclui a recuperação opcional de uma resposta perdida depois do ponto de compromisso.

[Especificação da SAGA](../06-saga.md) · [Recuperação e compensações](../08-saga.md)

```mermaid
sequenceDiagram
    participant B as BFF Unidade
    participant O as Orquestrador
    participant DB as PostgreSQL do Orquestrador
    participant R as Reservas
    participant E as Estoque
    participant T as Retiradas
    B->>O: Encaminhar aceite autenticado
    O->>DB: Gravar pedido, execução e intenção de aceite
    O-->>B: Pedido registrado para processamento
    O->>R: AceitarReserva com chave persistida
    R->>R: Gravar aceite, EM_CONFIRMACAO e resultado
    R-->>O: Aceite confirmado
    O->>DB: Gravar resultado e intenção de alocação
    O->>E: AlocarEstoque com chave persistida
    E->>E: Gravar alocação e resultado em transação local
    E-->>O: Alocação confirmada
    O->>DB: Gravar resultado e intenção de preparação
    O->>T: PrepararAutorizacao com chave persistida
    T->>T: Gravar autorização e resultado em transação local
    T-->>O: Autorização confirmada
    O->>DB: Gravar resultado e intenção de finalização
    O->>R: FinalizarConfirmacao com chave persistida
    R->>R: Gravar CONFIRMADA e resultado em transação local
    alt Resposta chega
        R-->>O: Finalização confirmada
    else Resposta perdida ou Orquestrador reiniciado
        O->>DB: Recuperar a intenção pendente
        O->>R: Repetir FinalizarConfirmacao com mesma chave e conteúdo
        R-->>O: Reproduzir resultado CONFIRMADA
    end
    O->>DB: Gravar resultado e CONCLUIDA
```
