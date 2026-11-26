CREATE TABLE movimentacoes (
    movimentacao_id uuid PRIMARY KEY,
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL,
    variacao_fisica integer NOT NULL CHECK (variacao_fisica <> 0),
    ocorrida_em timestamptz NOT NULL,
    alocacao_id uuid REFERENCES alocacoes (alocacao_id),
    retirada_id uuid UNIQUE,
    ator_id text,
    motivo text,
    FOREIGN KEY (unidade_id, item_id) REFERENCES saldos (unidade_id, item_id),
    -- Uma baixa de retirada exige a alocação consumida e variação negativa.
    CHECK (retirada_id IS NULL OR (alocacao_id IS NOT NULL AND variacao_fisica < 0))
);

CREATE INDEX movimentacoes_do_saldo ON movimentacoes (unidade_id, item_id, ocorrida_em);

-- Retiradas que não puderam ser baixadas, para reconciliação e reprocessamento.
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
