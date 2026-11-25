CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE trechos_conhecimento (
    id text PRIMARY KEY,
    versao integer NOT NULL CHECK (versao > 0),
    caminho text NOT NULL,
    titulo text NOT NULL,
    secao text NOT NULL,
    conteudo text NOT NULL,
    fontes jsonb NOT NULL,
    modelo text NOT NULL,
    resumo text NOT NULL,
    embedding vector(1536) NOT NULL
);
