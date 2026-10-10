"""Configuração via .env (carregado sem dependências)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=None):
    path = path or os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env()


def _req(name):
    v = os.environ.get(name, "").strip()
    if not v:
        raise SystemExit(f"Config faltando: defina {name} no .env (veja .env.example).")
    return v


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip()
# modelo barato p/ chamadas auxiliares (planejamento, extração, follow-ups)
OPENAI_FAST_MODEL = os.environ.get("OPENAI_FAST_MODEL", "gpt-4o-mini").strip()
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small").strip()
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))

# E-utilities: opcional, mas recomendado p/ rate limit maior
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "").strip()


def require_db():
    # RuntimeError (não SystemExit): chamado em runtime; SystemExit mataria o processo.
    if not DATABASE_URL:
        raise RuntimeError("Config faltando: defina DATABASE_URL no .env (Supabase > Database).")
    return DATABASE_URL


def require_openai():
    if not OPENAI_API_KEY:
        raise RuntimeError("Config faltando: defina OPENAI_API_KEY no .env.")
    return OPENAI_API_KEY
