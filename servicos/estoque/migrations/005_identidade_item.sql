-- Itens com mesmo nome e tipo são conflitantes, ignorando maiúsculas e espaços excedentes.
CREATE FUNCTION normalizar_cadastro(valor text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT lower(btrim(regexp_replace(valor, '\s+', ' ', 'g'))) $$;

-- O resumo mantém a chave do índice pequena, qualquer que seja o tamanho do nome.
CREATE FUNCTION identidade_item(nome text, tipo text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT md5(jsonb_build_array(normalizar_cadastro(nome), tipo)::text) $$;

ALTER TABLE itens
    ADD COLUMN identidade text GENERATED ALWAYS AS (identidade_item(nome, tipo)) STORED,
    ADD COLUMN duplicidade_legada boolean NOT NULL DEFAULT false;

-- Duplicatas anteriores são preservadas; a mais antiga ocupa a identidade.
UPDATE itens SET duplicidade_legada = true
WHERE item_id IN (
    SELECT item_id FROM (
        SELECT item_id, row_number() OVER (PARTITION BY identidade ORDER BY created_at, item_id) AS ordem FROM itens
    ) AS numerados WHERE ordem > 1
);

CREATE UNIQUE INDEX item_identidade_unica ON itens (identidade) WHERE NOT duplicidade_legada;
