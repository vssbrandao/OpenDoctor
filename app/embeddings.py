"""Cliente de embeddings (OpenAI). Trocável por config (EMBEDDING_MODEL)."""
import httpx

from . import config


def embed(texts):
    """Recebe lista de strings, devolve lista de vetores (list[float])."""
    if not texts:
        return []
    r = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {config.require_openai()}",
                 "Content-Type": "application/json"},
        json={"model": config.EMBEDDING_MODEL, "input": texts},
        timeout=60,
    )
    if r.status_code != 200:
        raise SystemExit(f"Embeddings {r.status_code}: {r.text[:300]}")
    data = r.json()["data"]
    # a API devolve na mesma ordem do input
    return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]
