"""Monta (ou atualiza) o banco de TESTES: aplica todas as migrações e põe a marca de ambiente de teste.

    python -m scripts.setup_test_db

Usa TEST_DATABASE_URL do .env — um projeto Supabase separado, só para testes, sem nenhum dado real.
Recusa-se a rodar se a URL for a de produção (mesmo projeto) ou se o banco já tiver usuários sem a
marca de teste (cara de banco real). Pode rodar de novo a cada migração nova: as migrações são
idempotentes ("if not exists").
"""
import os
import re
import sys
import urllib.parse

import psycopg

from app import config  # carrega o .env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS = os.path.join(ROOT, "supabase", "migrations")
TEST_MARKER = "ambiente_de_teste"


def _project(url):
    """Identificador do projeto Supabase na URL (db.<ref>.supabase.co ou usuário postgres.<ref>)."""
    u = urllib.parse.urlsplit(url)
    m = re.match(r"db\.([a-z0-9]+)\.supabase\.co$", u.hostname or "")
    if m:
        return m.group(1)
    m = re.match(r"postgres\.([a-z0-9]+)$", urllib.parse.unquote(u.username or ""))
    return m.group(1) if m else f"{u.hostname}:{u.port}/{u.path}"


def main():
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    prod_url = config.DATABASE_URL
    if not test_url:
        sys.exit("Defina TEST_DATABASE_URL no .env (connection string do projeto Supabase de testes).")
    if prod_url and _project(test_url) == _project(prod_url):
        sys.exit("TEST_DATABASE_URL aponta para o mesmo projeto do DATABASE_URL (produção). Nada foi feito.")

    with psycopg.connect(test_url, connect_timeout=15) as conn:
        marked = conn.execute("select to_regclass(%s) is not null", (f"public.{TEST_MARKER}",)).fetchone()[0]
        has_users = conn.execute("select to_regclass('public.users') is not null").fetchone()[0]
        if not marked and has_users and conn.execute("select count(*) from users").fetchone()[0] > 0:
            sys.exit("Este banco já tem usuários e não é um banco de testes. Nada foi feito.")

        for f in sorted(os.listdir(MIGRATIONS)):
            if f.endswith(".sql"):
                with open(os.path.join(MIGRATIONS, f), encoding="utf-8") as fh:
                    conn.execute(fh.read())
                conn.commit()
                print("aplicada", f)

        conn.execute(f"create table if not exists {TEST_MARKER} (criado_em timestamptz not null default now())")
        conn.execute(f"alter table {TEST_MARKER} enable row level security")
        conn.execute(f"comment on table {TEST_MARKER} is 'Banco de TESTES do OpenDoctor: sem dados reais.'")
        conn.commit()

        rows = conn.execute("""select c.relname, c.relrowsecurity from pg_class c
                               join pg_namespace n on n.oid = c.relnamespace
                               where n.nspname = 'public' and c.relkind = 'r' order by 1""").fetchall()
    print("\nbanco de testes pronto:", ", ".join(f"{t}{'' if rls else ' (SEM RLS!)'}" for t, rls in rows))


if __name__ == "__main__":
    main()
