ALTER TABLE historico_reserva
    ADD COLUMN motivo text,
    ADD COLUMN event_id uuid,
    ADD COLUMN retirada_id uuid;

UPDATE historico_reserva AS h
SET motivo = 'RETIRADA_CONCLUIDA', event_id = h.historico_id, retirada_id = r.retirada_id
FROM reservas AS r
WHERE h.reserva_id = r.reserva_id
  AND h.status_posterior = 'RETIRADA' AND h.ator_id = 'retiradas';

INSERT INTO inbox (consumer, event_id, processed_at)
SELECT 'retirada-concluida', event_id, processed_at FROM inbox
WHERE consumer = 'reservas.retirada-concluida'
ON CONFLICT DO NOTHING;

DROP INDEX reservas_unidade_status;
CREATE INDEX reservas_unidade_status ON reservas (unidade_id, status, criada_em);
CREATE INDEX reservas_cidadao ON reservas (cidadao_id, criada_em);
CREATE INDEX historico_da_reserva ON historico_reserva (reserva_id, ocorrido_em);
