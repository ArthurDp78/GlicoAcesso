CREATE TABLE retiradas (
    retirada_id uuid PRIMARY KEY,
    autorizacao_id uuid NOT NULL UNIQUE REFERENCES autorizacoes (autorizacao_id),
    realizada_em timestamptz NOT NULL,
    ator_id text NOT NULL,
    correlation_id uuid NOT NULL
);

CREATE TABLE outbox (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    event_version integer NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    correlation_id uuid NOT NULL,
    causation_id uuid,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    status text NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE', 'PUBLICADO')),
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_retry_at timestamptz NOT NULL DEFAULT now(),
    last_error text,
    CHECK ((status = 'PUBLICADO') = (published_at IS NOT NULL))
);

CREATE INDEX outbox_pendentes ON outbox (next_retry_at) WHERE status = 'PENDENTE';
