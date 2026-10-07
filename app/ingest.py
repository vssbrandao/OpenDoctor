"""CLI de ingestão (spec §3.3): `python -m app.ingest --source pubmed --query "..."`."""
import sys
import argparse

from . import pubmed, chunking, embeddings, db


EMBED_BATCH = 100  # chunks por chamada de embeddings


def _dedupe(articles):
    seen, uniq = set(), []
    for a in articles:
        if a["content_hash"] in seen:
            continue
        seen.add(a["content_hash"])
        uniq.append(a)
    return uniq


def fetch_and_embed(terms, retmax=10):
    """Busca no PubMed, faz chunking e embeda — SEM tocar no banco.
    Devolve (per, vecs): per=[(article, [(section,text),...])]; vecs alinhado aos chunks."""
    articles = _dedupe(pubmed.fetch(pubmed.search(terms, retmax=retmax)))
    per = [(a, chunking.chunk_article(a)) for a in articles]
    texts = [t for (_, ch) in per for (_, t) in ch]
    vecs = []
    for i in range(0, len(texts), EMBED_BATCH):
        vecs += embeddings.embed(texts[i:i + EMBED_BATCH])
    return per, vecs


def persist(per, vecs):
    """Grava no banco (idempotente, em lote). Pode rodar em segundo plano."""
    if not per:
        return 0, 0
    with db.connection() as conn:
        rows = [("pubmed", "article", a["title"], a["url"], "english",
                 (f"{a['year']}-01-01" if a.get("year") else None),
                 "PubMed/PMC (verificar por artigo)", None, a["content_hash"]) for (a, _) in per]
        new_ids = db.upsert_documents_bulk(conn, rows)
        chunk_rows, pos = [], 0
        for a, ch in per:
            did = new_ids.get(a["content_hash"])
            for idx, (section, text) in enumerate(ch):
                if did is not None:
                    chunk_rows.append((did, section, idx, text, vecs[pos]))
                pos += 1
        db.insert_chunks_bulk(conn, chunk_rows, "english")
    return len(new_ids), len(chunk_rows)


def ingest_pubmed(query, retmax):
    print(f"[pubmed] buscando: {query!r} (retmax={retmax})")
    per, vecs = fetch_and_embed(query, retmax)
    nd, nc = persist(per, vecs)
    print(f"[ok] novos: {nd} docs / {nc} chunks (de {len(per)} artigos com abstract)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ingest")
    p.add_argument("--source", required=True, choices=["pubmed"])
    p.add_argument("--query", help="termo de busca (obrigatório p/ pubmed)")
    p.add_argument("--retmax", type=int, default=20, help="máx. de artigos (default 20)")
    args = p.parse_args(argv)

    if args.source == "pubmed":
        if not args.query:
            p.error("--query é obrigatório para --source pubmed")
        ingest_pubmed(args.query, args.retmax)


if __name__ == "__main__":
    main(sys.argv[1:])
