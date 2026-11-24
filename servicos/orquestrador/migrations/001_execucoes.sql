CREATE TABLE saga_execucoes (
    saga_id uuid PRIMARY KEY,
    reserva_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('CONFIRMACAO', 'CANCELAMENTO')),
    estado text NOT NULL CHECK (estado IN (
        'EM_EXECUCAO', 'COMPENSANDO', 'COMPENSACAO_PENDENTE', 'CANCELANDO', 'CANCELAMENTO_PENDENTE',
        'INTERROMPIDA', 'CONCLUIDA', 'COMPENSADA', 'CANCELADA'
    )),
    versao bigint NOT NULL DEFAULT 0,
    -- Contexto mínimo do ator delegado; credenciais nunca são gravadas.
    ator_id text NOT NULL,
    ator_unidade_id uuid,
    etapa_atual text,
    encerrada_em timestamptz,
    motivo_encerramento text,
    resultado jsonb,
    criada_em timestamptz NOT NULL,
    atualizada_em timestamptz NOT NULL
);

-- Impede duas execuções ativas para a mesma reserva.
CREATE UNIQUE INDEX saga_execucao_ativa_por_reserva ON saga_execucoes (reserva_id)
    WHERE estado IN ('EM_EXECUCAO', 'COMPENSANDO', 'COMPENSACAO_PENDENTE', 'CANCELANDO', 'CANCELAMENTO_PENDENTE');

CREATE TABLE saga_etapas (
    saga_id uuid NOT NULL REFERENCES saga_execucoes (saga_id),
    etapa_id text NOT NULL,
    operacao text NOT NULL,
    destino text NOT NULL,
    idempotency_key text NOT NULL,
    estado_tecnico text NOT NULL CHECK (estado_tecnico IN ('PENDENTE', 'CONCLUIDA', 'FALHOU')),
    dados_comando jsonb NOT NULL,
    tentativas integer NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    ultima_tentativa_em timestamptz,
    proximo_retry_em timestamptz,
    resultado jsonb,
    erro_tecnico text,
    criada_em timestamptz NOT NULL,
    atualizada_em timestamptz NOT NULL,
    PRIMARY KEY (saga_id, etapa_id)
);

CREATE INDEX saga_etapas_pendentes ON saga_etapas (proximo_retry_em) WHERE estado_tecnico = 'PENDENTE';

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
