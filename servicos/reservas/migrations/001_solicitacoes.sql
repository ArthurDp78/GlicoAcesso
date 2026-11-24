CREATE TABLE reservas (
    reserva_id uuid PRIMARY KEY,
    cidadao_id text NOT NULL,
    unidade_id uuid NOT NULL,
    item_id uuid NOT NULL,
    quantidade integer NOT NULL CHECK (quantidade > 0),
    status text NOT NULL CHECK (status IN (
        'SOLICITADA', 'EM_CONFIRMACAO', 'CONFIRMADA', 'CANCELAMENTO_EM_ANDAMENTO',
        'CANCELADA', 'REJEITADA', 'EXPIRADA', 'FALHA_CONFIRMACAO', 'RETIRADA'
    )),
    prazo_analise_horas integer NOT NULL CHECK (prazo_analise_horas > 0),
    criada_em timestamptz NOT NULL,
    decisao_ate timestamptz NOT NULL,
    atualizada_em timestamptz NOT NULL,
    idempotency_key text NOT NULL,
    decisao text CHECK (decisao IN ('ACEITAR', 'REJEITAR')),
    decisao_ator_id text,
    decidida_em timestamptz
);

CREATE TABLE historico_reserva (
    historico_id uuid PRIMARY KEY,
    reserva_id uuid NOT NULL REFERENCES reservas (reserva_id),
    status_anterior text,
    status_posterior text NOT NULL,
    ocorrido_em timestamptz NOT NULL,
    ator_id text,
    justificativa text
);

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

CREATE INDEX reservas_unidade_status ON reservas (unidade_id, status);
CREATE INDEX reservas_solicitadas_prazo ON reservas (decisao_ate) WHERE status = 'SOLICITADA';
