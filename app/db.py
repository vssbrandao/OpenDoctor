"""Camada de banco (Supabase/Postgres + pgvector)."""
import psycopg
from pgvector.psycopg import register_vector

from . import config

# config de full-text por idioma do documento
_TS = {"english": "english", "portuguese": "portuguese"}


def connect():
    """Conexão avulsa (usada por scripts one-shot, ex.: ingestão)."""
    conn = psycopg.connect(config.require_db())
    register_vector(conn)
    return conn


# --- pool para o servidor (evita reconectar ~3s por request) ---
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            config.require_db(), min_size=1, max_size=5, open=True,
            kwargs={"connect_timeout": 15},
            configure=register_vector,
        )
    return _pool


def connection():
    """Context manager que empresta uma conexão do pool."""
    return get_pool().connection()


def upsert_document(conn, *, source, source_type, title, url, language,
                    publication_date, license, raw_path, content_hash):
    """Insere o documento; se já existir (source+content_hash), devolve (id, created=False)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into documents
              (source, source_type, title, url, language, publication_date, license, raw_path, content_hash)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (source, content_hash) do nothing
            returning id
            """,
            (source, source_type, title, url, language, publication_date, license, raw_path, content_hash),
        )
        row = cur.fetchone()
        if row:
            return row[0], True
        cur.execute(
            "select id from documents where source=%s and content_hash=%s",
            (source, content_hash),
        )
        return cur.fetchone()[0], False


def insert_chunks(conn, document_id, language, chunks, embeddings):
    """chunks: [(section_title, text)]; embeddings: list[list[float]] alinhado a chunks."""
    ts = _TS.get((language or "").lower(), "simple")
    with conn.cursor() as cur:
        for idx, ((section, text), emb) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                f"""
                insert into chunks (document_id, section_title, chunk_index, text, embedding, tsv)
                values (%s,%s,%s,%s,%s, to_tsvector('{ts}', %s))
                on conflict (document_id, chunk_index) do nothing
                """,
                (document_id, section, idx, text, emb, text),
            )
    conn.commit()


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from documents")
        d = cur.fetchone()[0]
        cur.execute("select count(*) from chunks")
        c = cur.fetchone()[0]
    return d, c
