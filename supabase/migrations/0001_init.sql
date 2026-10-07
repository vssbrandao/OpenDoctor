-- OpenDoctor — schema inicial do RAG (spec §3.2)
-- Alvo: Postgres (Supabase) com a extensão pgvector.
--
-- Dimensão do embedding = 1536 (OpenAI text-embedding-3-small, multilíngue, barato).
-- Trocar de modelo de embedding depois exige migração desta coluna. Ver README.

create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- documents: um registro por documento-fonte (artigo, diretriz, protocolo)
-- ---------------------------------------------------------------------------
create table if not exists documents (
  id               bigserial primary key,
  source           text        not null,                 -- ex.: 'pubmed', 'conitec'
  source_type      text        not null
                     check (source_type in ('guideline','article','protocol')),
  title            text,
  url              text,
  language         text,                                  -- 'portuguese' | 'english' | ...
  publication_date date,
  last_updated     date,
  license          text,
  raw_path         text,                                  -- arquivo bruto guardado p/ reprocessar
  content_hash     text        not null,                  -- idempotência da ingestão
  ingested_at      timestamptz not null default now(),
  unique (source, content_hash)
);

-- ---------------------------------------------------------------------------
-- chunks: pedaços recuperáveis de cada documento
--   embedding -> busca vetorial (pgvector)
--   tsv       -> busca full-text; preenchido pela ingestão com
--                to_tsvector(<config por idioma>, text), por isso NÃO é GENERATED
-- ---------------------------------------------------------------------------
create table if not exists chunks (
  id            bigserial primary key,
  document_id   bigint not null references documents(id) on delete cascade,
  section_title text,
  chunk_index   int    not null,
  text          text   not null,
  embedding     vector(1536),
  tsv           tsvector,
  unique (document_id, chunk_index)
);

-- ---------------------------------------------------------------------------
-- índices (spec §8.5): HNSW p/ vetor (cosseno) + GIN p/ full-text
-- ---------------------------------------------------------------------------
create index if not exists chunks_embedding_hnsw
  on chunks using hnsw (embedding vector_cosine_ops);

create index if not exists chunks_tsv_gin
  on chunks using gin (tsv);

create index if not exists chunks_document_id_idx
  on chunks (document_id);

create index if not exists documents_source_type_idx
  on documents (source_type);
