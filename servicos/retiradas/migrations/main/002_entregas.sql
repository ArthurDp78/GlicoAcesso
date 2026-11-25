ALTER TABLE entregas RENAME TO retiradas;
ALTER TABLE retiradas RENAME COLUMN profissional_id TO ator_id;
ALTER TABLE retiradas ADD COLUMN correlation_id uuid;

UPDATE retiradas AS r
SET correlation_id = COALESCE(
    (SELECT o.correlation_id FROM outbox AS o
     WHERE o.event_type = 'retirada.concluida.v1' AND o.aggregate_id = r.retirada_id::text
     ORDER BY o.created_at, o.event_id LIMIT 1),
    a.correlation_id,
    r.retirada_id
)
FROM autorizacoes AS a WHERE a.autorizacao_id = r.autorizacao_id;

ALTER TABLE retiradas ALTER COLUMN correlation_id SET NOT NULL;
