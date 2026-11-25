CREATE TABLE movimentacoes (
    movimentacao_id uuid PRIMARY KEY,
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL,
    variacao_fisica integer NOT NULL CHECK (variacao_fisica <> 0),
    estoque_version bigint NOT NULL CHECK (estoque_version > 0),
    ocorrida_em timestamptz NOT NULL,
    ator_id text NOT NULL,
    motivo text NOT NULL,
    FOREIGN KEY (unidade_id, item_id) REFERENCES saldos (unidade_id, item_id)
);
