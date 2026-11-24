# GlicoAcesso - SAGA de confirmação: falha ao preparar autorização

Neste cenário, a autorização nunca foi criada. Se o resultado recuperado confirmar sua criação, a revogação deve preceder qualquer liberação.

[Especificação da SAGA](../06-saga.md) · [Recuperação e compensações](../08-saga.md)

```mermaid
sequenceDiagram
    participant O as Orquestrador
    participant R as Reservas
    participant E as Estoque
    participant T as Retiradas
    Note over O,T: Aceite em EM_CONFIRMACAO registrado
    O->>E: AlocarEstoque
    E-->>O: Alocação confirmada
    O->>T: PrepararAutorizacao
    alt Rejeição definitiva na primeira resposta
        T-->>O: Nenhuma autorização criada
    else Resultado incerto
        Note over O,T: Resultado desconhecido após timeout
        O->>T: Repetir com mesma chave e conteúdo
        T-->>O: Resultado conclusivo sem autorização
    end
    O->>O: Registrar falha definitiva e intenção de compensar
    O->>E: LiberarAlocacao com chave própria
    E-->>O: Liberação confirmada
    O->>R: Solicitar FALHA_CONFIRMACAO
    R-->>O: Falha gravada
    O->>O: Gravar COMPENSADA
```
