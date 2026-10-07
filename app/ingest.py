"""CLI de ingestão (spec §3.3): `python -m app.ingest --source pubmed --query "..."`."""
import sys
import argparse

from . import pubmed, chunking, embeddings, db


def ingest_pubmed(query, retmax):
    print(f"[pubmed] buscando: {query!r} (retmax={retmax})")
    pmids = pubmed.search(query, retmax=retmax)
    print(f"[pubmed] {len(pmids)} PMIDs")
    articles = pubmed.fetch(pmids)
    print(f"[pubmed] {len(articles)} artigos com abstract")

    conn = db.connect()
    new_docs = new_chunks = skipped = 0
    try:
        for a in articles:
            pub_date = f"{a['year']}-01-01" if a.get("year") else None
            doc_id, created = db.upsert_document(
                conn,
                source="pubmed",
                source_type="article",
                title=a["title"],
                url=a["url"],
                language="english",
                publication_date=pub_date,
                license="PubMed/PMC (verificar por artigo)",
                raw_path=None,
                content_hash=a["content_hash"],
            )
            if not created:
                skipped += 1
                continue  # idempotente: já ingerido, não re-embeda

            chunks = chunking.chunk_article(a)
            vecs = embeddings.embed([c[1] for c in chunks])
            db.insert_chunks(conn, doc_id, "english", chunks, vecs)
            new_docs += 1
            new_chunks += len(chunks)
            print(f"  + {a['pmid']}  {a['title'][:70]!r}  ({len(chunks)} chunks)")

        d, c = db.counts(conn)
        print(f"\n[ok] novos: {new_docs} docs / {new_chunks} chunks · já existiam: {skipped}")
        print(f"[ok] total no banco: {d} documents / {c} chunks")
    finally:
        conn.close()


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
