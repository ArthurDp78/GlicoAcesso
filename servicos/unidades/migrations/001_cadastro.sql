CREATE TABLE unidades (
    unidade_id uuid PRIMARY KEY,
    nome text NOT NULL CHECK (btrim(nome) <> ''),
    logradouro text NOT NULL,
    numero text NOT NULL,
    bairro text NOT NULL,
    cidade text NOT NULL,
    estado text NOT NULL,
    cep text NOT NULL,
    orientacoes_retirada text NOT NULL CHECK (btrim(orientacoes_retirada) <> ''),
    prazo_analise_horas integer NOT NULL CHECK (prazo_analise_horas > 0),
    ativa boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contatos_unidade (
    unidade_id uuid NOT NULL REFERENCES unidades (unidade_id),
    tipo text NOT NULL,
    valor text NOT NULL,
    PRIMARY KEY (unidade_id, tipo, valor)
);

CREATE TABLE horarios_unidade (
    unidade_id uuid NOT NULL REFERENCES unidades (unidade_id),
    dia_semana smallint NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),
    horario_inicial time NOT NULL,
    horario_final time NOT NULL,
    PRIMARY KEY (unidade_id, dia_semana, horario_inicial, horario_final)
);
