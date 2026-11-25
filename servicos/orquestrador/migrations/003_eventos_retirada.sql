CREATE TABLE inbox (
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_id)
);

CREATE TABLE entregas_observadas (
    reserva_id uuid PRIMARY KEY,
    retirada_id uuid NOT NULL UNIQUE,
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL,
    quantidade integer NOT NULL CHECK (quantidade > 0),
    ocorrida_em timestamptz NOT NULL,
    correlation_id uuid NOT NULL
);
