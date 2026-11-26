CREATE TABLE idempotencia_comandos (
    operacao text NOT NULL,
    principal_id text NOT NULL,
    chave text NOT NULL,
    request_hash text NOT NULL,
    http_status integer NOT NULL,
    resposta jsonb NOT NULL,
    criada_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (operacao, principal_id, chave)
);
