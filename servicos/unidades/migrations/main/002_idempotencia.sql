-- O esquema de idempotência da main é equivalente. A migração 004 instala
-- o novo índice de identidade ao final desta mesma transação.
DROP INDEX unidades_cadastro_unico;
