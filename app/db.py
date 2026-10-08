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


def upsert_documents_bulk(conn, rows):
    """rows: tuplas (source, source_type, title, url, language, publication_date,
    license, raw_path, content_hash). 1 round-trip. Devolve {content_hash: id} dos NOVOS."""
    if not rows:
        return {}
    ph = ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(rows))
    sql = ("insert into documents (source, source_type, title, url, language, "
           "publication_date, license, raw_path, content_hash) values " + ph +
           " on conflict (source, content_hash) do nothing returning content_hash, id")
    flat = [v for r in rows for v in r]
    with conn.cursor() as cur:
        cur.execute(sql, flat)
        return {h: i for (h, i) in cur.fetchall()}


def insert_chunks_bulk(conn, rows, language="english"):
    """rows: (document_id, section_title, chunk_index, text, embedding). 1 round-trip."""
    if not rows:
        return
    ts = _TS.get((language or "").lower(), "simple")
    unit = "(%s,%s,%s,%s,%s, to_tsvector('" + ts + "', %s))"
    ph = ",".join([unit] * len(rows))
    sql = ("insert into chunks (document_id, section_title, chunk_index, text, embedding, tsv) "
           "values " + ph + " on conflict (document_id, chunk_index) do nothing")
    flat = []
    for (doc_id, section, idx, text, emb) in rows:
        flat += [doc_id, section, idx, text, emb, text]
    with conn.cursor() as cur:
        cur.execute(sql, flat)
    conn.commit()


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from documents")
        d = cur.fetchone()[0]
        cur.execute("select count(*) from chunks")
        c = cur.fetchone()[0]
    return d, c


# ===== usuários + tokens de calendário (Fase B, multiusuário) =====

def _row_to_user(row):
    if not row:
        return None
    return {"id": str(row[0]), "email": row[1], "name": row[2], "picture": row[3]}


def upsert_user(email, name=None, picture=None, google_sub=None):
    """Cria ou atualiza o usuário pela conta Google; devolve o dict do usuário."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into users (email, name, picture, google_sub, last_login)
                values (%s,%s,%s,%s, now())
                on conflict (email) do update set
                  name = coalesce(excluded.name, users.name),
                  picture = coalesce(excluded.picture, users.picture),
                  google_sub = coalesce(excluded.google_sub, users.google_sub),
                  last_login = now()
                returning id, email, name, picture
                """,
                (email, name, picture, google_sub),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_user(row)


def get_user(user_id):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select id, email, name, picture from users where id = %s", (user_id,))
            return _row_to_user(cur.fetchone())


def set_token(user_id, provider, *, access_token, refresh_token, expires_at, scope, account_email):
    """Grava/atualiza o token de calendário do usuário. Não apaga o refresh_token
    existente se o provedor não mandar um novo nesta troca."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into oauth_tokens
                  (user_id, provider, access_token, refresh_token, expires_at, scope, account_email, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s, now())
                on conflict (user_id, provider) do update set
                  access_token = excluded.access_token,
                  refresh_token = coalesce(excluded.refresh_token, oauth_tokens.refresh_token),
                  expires_at = excluded.expires_at,
                  scope = excluded.scope,
                  account_email = coalesce(excluded.account_email, oauth_tokens.account_email),
                  updated_at = now()
                """,
                (user_id, provider, access_token, refresh_token, expires_at, scope, account_email),
            )
        conn.commit()


def get_token(user_id, provider):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select access_token, refresh_token, expires_at, scope, account_email
                   from oauth_tokens where user_id = %s and provider = %s""",
                (user_id, provider),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"access_token": row[0], "refresh_token": row[1], "expires_at": row[2],
            "scope": row[3], "account_email": row[4]}


def update_access_token(user_id, provider, access_token, expires_at, refresh_token=None):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """update oauth_tokens set access_token=%s, expires_at=%s,
                   refresh_token=coalesce(%s, refresh_token), updated_at=now()
                   where user_id=%s and provider=%s""",
                (access_token, expires_at, refresh_token, user_id, provider),
            )
        conn.commit()


def delete_token(user_id, provider):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from oauth_tokens where user_id=%s and provider=%s",
                        (user_id, provider))
        conn.commit()


def connected_providers(user_id):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select provider, account_email from oauth_tokens where user_id=%s",
                (user_id,))
            return {p: email for (p, email) in cur.fetchall()}
