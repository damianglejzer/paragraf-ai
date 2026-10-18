"""Database schema. Embedding dimension comes from settings, so the DDL is built in code."""


def schema_sql(embedding_dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS acts (
    code              text PRIMARY KEY,
    name              text NOT NULL,
    eli               text NOT NULL,
    title             text NOT NULL,
    announcement_date date
);

CREATE TABLE IF NOT EXISTS provisions (
    id               text PRIMARY KEY,
    act_code         text NOT NULL REFERENCES acts(code) ON DELETE CASCADE,
    level            text NOT NULL,
    article          text NOT NULL,
    unit             text,
    parent_id        text,
    hierarchy        text[] NOT NULL DEFAULT '{{}}',
    hierarchy_titles text[] NOT NULL DEFAULT '{{}}',
    citation         text NOT NULL,
    full_path        text NOT NULL,
    text             text NOT NULL,
    repealed         boolean NOT NULL DEFAULT false,
    is_chunk         boolean NOT NULL,
    ord              integer NOT NULL,
    -- full-text search over Polish lemmas, indexed with the language-agnostic 'simple' config
    lemmas           text,
    tsv              tsvector
                     GENERATED ALWAYS AS (to_tsvector('simple', coalesce(lemmas, ''))) STORED,
    embedding        vector({embedding_dim})
);
CREATE INDEX IF NOT EXISTS provisions_act_idx ON provisions (act_code, ord);
CREATE INDEX IF NOT EXISTS provisions_parent_idx ON provisions (parent_id);
CREATE INDEX IF NOT EXISTS provisions_tsv_idx ON provisions USING gin (tsv);

CREATE TABLE IF NOT EXISTS provision_refs (
    source_id  text NOT NULL REFERENCES provisions(id) ON DELETE CASCADE,
    target_id  text NOT NULL,
    raw        text NOT NULL,
    PRIMARY KEY (source_id, target_id)
);
CREATE INDEX IF NOT EXISTS provision_refs_target_idx ON provision_refs (target_id);

-- Baseline for the ablation study: fixed-size chunks, vectors only
CREATE TABLE IF NOT EXISTS naive_chunks (
    id         serial PRIMARY KEY,
    act_code   text NOT NULL REFERENCES acts(code) ON DELETE CASCADE,
    text       text NOT NULL,
    provision_ids text[] NOT NULL,
    embedding  vector({embedding_dim})
);
"""


VECTOR_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS provisions_embedding_idx
    ON provisions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS naive_chunks_embedding_idx
    ON naive_chunks USING hnsw (embedding vector_cosine_ops);
"""
