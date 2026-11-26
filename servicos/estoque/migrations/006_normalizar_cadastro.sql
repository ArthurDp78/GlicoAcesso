-- Identidade de catálogo estável entre C e C.utf8: caixa não depende do locale e acentos são preservados.
-- O conjunto conserva nomes históricos: apenas escolhe uma linha canônica por identidade,
-- marcando as demais como duplicatas legadas antes de reinstalar a unicidade.
CREATE OR REPLACE FUNCTION normalizar_cadastro(valor text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT AS $$
        SELECT translate(
            lower(btrim(regexp_replace(normalize(valor, NFC), '\s+', ' ', 'g')) COLLATE "C"),
            'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ',
            'áàâãäéèêëíìîïóòôõöúùûüç'
        )
    $$;

DROP INDEX item_identidade_unica;
UPDATE itens SET duplicidade_legada = true;
-- Força a coluna gerada a ser recalculada depois de trocar a função imutável.
UPDATE itens SET nome = nome;

WITH classificados AS (
    SELECT item_id, row_number() OVER (PARTITION BY identidade ORDER BY created_at, item_id) AS ordem
    FROM itens
)
UPDATE itens AS i
SET duplicidade_legada = (c.ordem > 1)
FROM classificados AS c
WHERE c.item_id = i.item_id;

CREATE UNIQUE INDEX item_identidade_unica ON itens (identidade) WHERE NOT duplicidade_legada;
