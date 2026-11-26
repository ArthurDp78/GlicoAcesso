-- Mantém os movimentos da main e sua versão de estoque. Os novos movimentos da
-- branch podem omitir a versão, que continua registrada no saldo e nos eventos.
ALTER TABLE movimentacoes
    ALTER COLUMN estoque_version DROP NOT NULL,
    ALTER COLUMN ator_id DROP NOT NULL,
    ALTER COLUMN motivo DROP NOT NULL,
    ADD COLUMN alocacao_id uuid REFERENCES alocacoes (alocacao_id),
    ADD COLUMN retirada_id uuid UNIQUE;

-- A Outbox da main vincula o movimento e a retirada que originou a baixa.
UPDATE movimentacoes AS m
SET alocacao_id = a.alocacao_id, retirada_id = a.retirada_id
FROM outbox AS o
JOIN alocacoes AS a ON a.reserva_id::text = o.payload->>'reservaId'
WHERE o.event_type = 'estoque.retirada-baixada.v1'
  AND o.aggregate_type = 'MovimentacaoEstoque'
  AND o.aggregate_id = m.movimentacao_id::text
  AND a.retirada_id::text = o.payload->>'retiradaId';

ALTER TABLE movimentacoes ADD CHECK (
    retirada_id IS NULL OR (alocacao_id IS NOT NULL AND variacao_fisica < 0)
);

CREATE INDEX movimentacoes_do_saldo ON movimentacoes (unidade_id, item_id, ocorrida_em);

CREATE TABLE ocorrencias_retirada (
    event_id uuid PRIMARY KEY,
    reserva_id uuid NOT NULL,
    retirada_id uuid NOT NULL,
    motivo text NOT NULL,
    evento jsonb NOT NULL,
    tentativas integer NOT NULL DEFAULT 1,
    registrada_em timestamptz NOT NULL DEFAULT now(),
    resolvida_em timestamptz
);

INSERT INTO inbox (consumer, event_id, processed_at)
SELECT 'baixa-retirada', event_id, processed_at FROM inbox
WHERE consumer = 'estoque.retirada-concluida'
ON CONFLICT DO NOTHING;
