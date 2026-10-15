"""Os testes nunca falam com o banco de produção, com a OpenAI nem com o Resend.

Isto roda antes de qualquer import do app: DATABASE_URL, OPENAI_API_KEY e RESEND_API_KEY ficam vazios
(o .env não sobrescreve um valor já definido). Um acesso esquecido dá erro em vez de mexer em
prontuário real, gastar crédito ou mandar e-mail.

Teste que precisa de banco usa a fixture `test_db`: ela aponta para o projeto Supabase de TESTES
(TEST_DATABASE_URL, no .env) e só roda se o banco tiver a marca de ambiente de teste — criada por
`python -m scripts.setup_test_db`, que se recusa a marcar um banco com dados reais.
"""
import os

os.environ["DATABASE_URL"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["RESEND_API_KEY"] = ""

import pytest  # noqa: E402

from app import config, db  # noqa: E402

TEST_MARKER = "ambiente_de_teste"     # tabela que só existe no banco de testes


def _test_db_url():
    return os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.fixture
def test_db(monkeypatch):
    url = _test_db_url()
    if not url:
        pytest.skip("sem TEST_DATABASE_URL (banco de testes) — veja scripts/setup_test_db.py")
    import psycopg
    with psycopg.connect(url, connect_timeout=15) as c:
        marked = c.execute("select to_regclass(%s) is not null", (f"public.{TEST_MARKER}",)).fetchone()[0]
    if not marked:
        pytest.fail("TEST_DATABASE_URL não tem a marca de banco de testes — recusando (pode ser produção)")
    monkeypatch.setattr(config, "DATABASE_URL", url)
    db._pool = None
    yield url
    if db._pool is not None:
        db._pool.close()
        db._pool = None


def pytest_runtest_logreport(report):
    """No GitHub Actions, cada falha vira anotação do commit (lida sem acesso de administrador ao log)."""
    if os.environ.get("GITHUB_ACTIONS") and report.failed:
        msg = str(report.longrepr)[-1800:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"\n::error title={report.nodeid}::{msg}", flush=True)


def pytest_collectreport(report):
    if os.environ.get("GITHUB_ACTIONS") and report.failed:
        msg = str(report.longrepr)[-1800:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"\n::error title=coleta {report.nodeid}::{msg}", flush=True)
