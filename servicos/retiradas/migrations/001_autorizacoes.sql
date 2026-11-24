CREATE TABLE autorizacoes (
    autorizacao_id uuid PRIMARY KEY,
    reserva_id uuid NOT NULL UNIQUE,
    saga_id uuid NOT NULL,
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL,
    quantidade integer NOT NULL CHECK (quantidade > 0),
    idempotency_key text NOT NULL,
    correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    cancelada_em timestamptz
);

CREATE TABLE idempotencia_comandos (
    operacao text NOT NULL,
    principal_id text NOT NULL,
    chave text NOT NULL,
    request_hash text NOT NULL,
    http_status integer NOT NULL,
    resposta jsonb NOT NULL,
    criada_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (operacao, principal_id, chave)
);
