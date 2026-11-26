-- Unidades com mesmo nome e endereço são conflitantes, ignorando maiúsculas e espaços excedentes.
CREATE FUNCTION normalizar_cadastro(valor text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT lower(btrim(regexp_replace(valor, '\s+', ' ', 'g'))) $$;

-- O resumo mantém a chave do índice pequena, qualquer que seja o tamanho dos campos.
CREATE FUNCTION identidade_unidade(nome text, logradouro text, numero text, bairro text, cidade text, estado text, cep text)
    RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT md5(jsonb_build_array(
        normalizar_cadastro(nome), normalizar_cadastro(logradouro), normalizar_cadastro(numero),
        normalizar_cadastro(bairro), normalizar_cadastro(cidade), normalizar_cadastro(estado), normalizar_cadastro(cep)
    )::text) $$;

ALTER TABLE unidades
    ADD COLUMN identidade text GENERATED ALWAYS AS (
        identidade_unidade(nome, logradouro, numero, bairro, cidade, estado, cep)
    ) STORED,
    ADD COLUMN duplicidade_legada boolean NOT NULL DEFAULT false,
    ADD COLUMN prazo_legado boolean NOT NULL DEFAULT false;

-- Duplicatas e prazos anteriores às regras são preservados; a unidade mais antiga ocupa a identidade.
UPDATE unidades SET duplicidade_legada = true
WHERE unidade_id IN (
    SELECT unidade_id FROM (
        SELECT unidade_id, row_number() OVER (PARTITION BY identidade ORDER BY created_at, unidade_id) AS ordem FROM unidades
    ) AS numeradas WHERE ordem > 1
);
UPDATE unidades SET prazo_legado = true WHERE prazo_analise_horas > 720;

CREATE UNIQUE INDEX unidade_identidade_unica ON unidades (identidade) WHERE NOT duplicidade_legada;
ALTER TABLE unidades ADD CONSTRAINT unidade_prazo_maximo CHECK (prazo_legado OR prazo_analise_horas <= 720);
