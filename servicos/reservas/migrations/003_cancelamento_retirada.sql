ALTER TABLE historico_reserva
    ADD COLUMN motivo text,
    ADD COLUMN event_id uuid,
    ADD COLUMN retirada_id uuid;

CREATE TABLE inbox (
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL,
    PRIMARY KEY (consumer, event_id)
);

-- Índices previstos na documentação; o índice por unidade passa a cobrir também a ordem de criação.
DROP INDEX reservas_unidade_status;
CREATE INDEX reservas_unidade_status ON reservas (unidade_id, status, criada_em);
CREATE INDEX reservas_cidadao ON reservas (cidadao_id, criada_em);
CREATE INDEX historico_da_reserva ON historico_reserva (reserva_id, ocorrido_em);
