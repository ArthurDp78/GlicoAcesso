CREATE TABLE inbox (
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, event_id)
);

ALTER TABLE reservas ADD COLUMN retirada_id uuid UNIQUE;
