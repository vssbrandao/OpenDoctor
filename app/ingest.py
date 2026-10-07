"""CLI de ingestão (spec §3.3): `python -m app.ingest --source pubmed --query "..."`."""
import sys
import argparse

from . import pubmed, chunking, embeddings, db


EMBED_BATCH = 100  # chunks por chamada de embeddings


def ingest_pubmed(query, retmax):
    print(f"[pubmed] buscando: {query!r} (retmax={retmax})")
    pmids = pubmed.search(query, retmax=retmax)
    print(f"[pubmed] {len(pmids)} PMIDs")
    articles = pubmed.fetch(pmids)
    print(f"[pubmed] {len(articles)} artigos com abstract")

    # dedupe por content_hash dentro do lote
    seen, uniq = set(), []
    for a in articles:
        if a["content_hash"] in seen:
            continue
        seen.add(a["content_hash"])
        uniq.append(a)
    articles = uniq

    with db.connection() as conn:  # conexão do pool (evita reconectar ~3s)
        # 1) upsert de TODOS os documentos em 1 round-trip → ids dos novos
        rows = [("pubmed", "article", a["title"], a["url"], "english",
                 (f"{a['year']}-01-01" if a.get("year") else None),
                 "PubMed/PMC (verificar por artigo)", None, a["content_hash"]) for a in articles]
        new_ids = db.upsert_documents_bulk(conn, rows)   # {content_hash: id}
        new_articles = [a for a in articles if a["content_hash"] in new_ids]

        # 2) chunk + embeda TODOS os chunks em lote (poucas chamadas)
        per_article = [(a, chunking.chunk_article(a)) for a in new_articles]
        flat = [c[1] for (_, ch) in per_article for c in ch]
        vecs = []
        for i in range(0, len(flat), EMBED_BATCH):
            vecs += embeddings.embed(flat[i:i + EMBED_BATCH])

        # 3) monta e insere TODOS os chunks em 1 round-trip
        chunk_rows, pos = [], 0
        for a, ch in per_article:
            doc_id = new_ids[a["content_hash"]]
            for idx, (section, text) in enumerate(ch):
                chunk_rows.append((doc_id, section, idx, text, vecs[pos]))
                pos += 1
        db.insert_chunks_bulk(conn, chunk_rows, "english")

        d, c = db.counts(conn)
    print(f"[ok] novos: {len(new_articles)} docs / {len(chunk_rows)} chunks · "
          f"já existiam: {len(articles) - len(new_articles)}")
    print(f"[ok] total no banco: {d} documents / {c} chunks")


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
