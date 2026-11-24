CREATE TABLE itens (
    item_id uuid PRIMARY KEY,
    nome text NOT NULL CHECK (btrim(nome) <> ''),
    tipo text NOT NULL CHECK (tipo IN ('MEDICAMENTO', 'INSUMO')),
    descricao text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE saldos (
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL REFERENCES itens (item_id),
    estoque_fisico_atual integer NOT NULL CHECK (estoque_fisico_atual >= 0),
    quantidade_alocada integer NOT NULL DEFAULT 0,
    permite_reserva boolean NOT NULL,
    estoque_version bigint NOT NULL DEFAULT 0 CHECK (estoque_version >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (unidade_id, item_id),
    CHECK (quantidade_alocada BETWEEN 0 AND estoque_fisico_atual)
);

CREATE TABLE disponibilidade (
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL REFERENCES itens (item_id),
    estoque_fisico_atual integer NOT NULL CHECK (estoque_fisico_atual >= 0),
    quantidade_alocada integer NOT NULL,
    quantidade_disponivel integer GENERATED ALWAYS AS (
        estoque_fisico_atual - quantidade_alocada
    ) STORED,
    permite_reserva boolean NOT NULL,
    atualizado_em timestamptz NOT NULL,
    estoque_version bigint NOT NULL CHECK (estoque_version >= 0),
    PRIMARY KEY (unidade_id, item_id),
    CHECK (quantidade_alocada BETWEEN 0 AND estoque_fisico_atual)
);
