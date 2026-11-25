ALTER TABLE saga_execucoes
    ADD COLUMN ator_papel text NOT NULL DEFAULT 'PROFISSIONAL' CHECK (ator_papel IN ('CIDADAO', 'PROFISSIONAL')),
    ADD COLUMN event_id uuid,
    ADD COLUMN retirada_id uuid;

-- Pedido feito enquanto a confirmação está ativa. Não conta como execução ativa.
CREATE TABLE saga_pedidos_cancelamento (
    saga_id_solicitado uuid PRIMARY KEY,
    reserva_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    saga_confirmacao_id uuid NOT NULL REFERENCES saga_execucoes (saga_id),
    ator_papel text NOT NULL CHECK (ator_papel IN ('CIDADAO', 'PROFISSIONAL')),
    ator_id text NOT NULL,
    ator_unidade_id uuid,
    justificativa text,
    -- PENDENTE: aguarda a confirmação; EM_TRANSICAO: intenção gravada na confirmação ativa.
    fase text NOT NULL DEFAULT 'PENDENTE' CHECK (fase IN ('PENDENTE', 'EM_TRANSICAO', 'ATIVADO', 'RECUSADO')),
    motivo_encerramento text,
    solicitado_em timestamptz NOT NULL DEFAULT now(),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX pedido_cancelamento_aberto ON saga_pedidos_cancelamento (reserva_id)
    WHERE fase IN ('PENDENTE', 'EM_TRANSICAO');

CREATE INDEX saga_execucoes_reserva ON saga_execucoes (reserva_id);

CREATE TABLE inbox (
    consumer text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL,
    PRIMARY KEY (consumer, event_id)
);
