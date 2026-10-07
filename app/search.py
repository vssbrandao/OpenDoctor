"""Busca híbrida (spec §4): vetorial ∥ full-text → RRF → boost → limiar.

Sem rerank nesta fase (MVP). O limiar de suficiência usa a melhor similaridade
de cosseno da busca vetorial — provisório, a ser calibrado com o eval na F5.

CLI:  python -m app.search --query "..." [--k 5]
"""
import sys
import argparse

from . import embeddings, db

# --- parâmetros (vão para config/calibração na F5) ---
VEC_TOPN = 20
FTS_TOPN = 20
MAX_CANDIDATES = 30
FINAL_TOPK = 5
RRF_K = 60
FTS_CONFIG = "english"          # corpus atual é inglês (PubMed)
SIM_THRESHOLD = 0.30            # cosseno mínimo p/ considerar que há evidência
SOURCE_BOOST = {"guideline": 1.15, "protocol": 1.15, "article": 1.0}
RECENCY_BOOST_PER_YEAR = 0.01   # leve; aplicado sobre (ano - 2015), saturando
RECENCY_BASE_YEAR = 2015
RECENCY_MAX = 0.12


def _vec_literal(vec):
    """Formata a lista como literal de vetor pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _vector_search(conn, qvec, limit):
    lit = _vec_literal(qvec)
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.id, c.document_id, c.section_title, c.text,
                   d.title, d.url, d.source_type, d.publication_date,
                   1 - (c.embedding <=> %s::vector) as cosine_sim
            from chunks c join documents d on d.id = c.document_id
            where c.embedding is not null
            order by c.embedding <=> %s::vector
            limit %s
            """,
            (lit, lit, limit),
        )
        return cur.fetchall()


def _fts_search(conn, query, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.id, c.document_id, c.section_title, c.text,
                   d.title, d.url, d.source_type, d.publication_date,
                   ts_rank(c.tsv, q) as fts_rank
            from chunks c
            join documents d on d.id = c.document_id,
                 websearch_to_tsquery(%s, %s) q
            where c.tsv @@ q
            order by fts_rank desc
            limit %s
            """,
            (FTS_CONFIG, query, limit),
        )
        return cur.fetchall()


def _row_to_hit(row):
    (cid, doc_id, section, text, title, url, source_type, pub_date, score) = row
    return {
        "chunk_id": cid, "document_id": doc_id, "section_title": section,
        "text": text, "title": title, "url": url,
        "source_type": source_type, "publication_date": pub_date,
        "score": float(score) if score is not None else 0.0,
    }


def _boost(hit):
    b = SOURCE_BOOST.get(hit.get("source_type"), 1.0)
    d = hit.get("publication_date")
    if d is not None:
        yr = d.year if hasattr(d, "year") else int(str(d)[:4])
        b += min(max(yr - RECENCY_BASE_YEAR, 0) * RECENCY_BOOST_PER_YEAR, RECENCY_MAX)
    return b


def _vec_pooled(qvec, limit):
    with db.connection() as conn:
        return _vector_search(conn, qvec, limit)


def _fts_pooled(query, limit):
    with db.connection() as conn:
        return _fts_search(conn, query, limit)


def search(query, k=FINAL_TOPK, qvec=None):
    """Retorna dict: {insufficient: bool, best_sim: float, hits: [...]}

    Latência: embedding (API) roda em paralelo com o full-text (DB); a busca
    vetorial vem depois do embedding. Conexões vêm do pool (sem reconectar).
    """
    if qvec is None:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fut_emb = ex.submit(embeddings.embed, [query])
            fut_fts = ex.submit(_fts_pooled, query, FTS_TOPN)
            qvec = fut_emb.result()[0]
            fts_rows = fut_fts.result()
    else:
        fts_rows = _fts_pooled(query, FTS_TOPN)   # embedding reaproveitado
    vec_rows = _vec_pooled(qvec, VEC_TOPN)

    vec_hits = [_row_to_hit(r) for r in vec_rows]
    fts_hits = [_row_to_hit(r) for r in fts_rows]

    best_sim = max((h["score"] for h in vec_hits), default=0.0)

    # Reciprocal Rank Fusion
    fused = {}   # chunk_id -> hit (+ rrf)
    for ranked in (vec_hits, fts_hits):
        for rank, h in enumerate(ranked, start=1):
            entry = fused.setdefault(h["chunk_id"], dict(h, rrf=0.0, cosine_sim=None))
            entry["rrf"] += 1.0 / (RRF_K + rank)
    # anexa a similaridade de cosseno (quando veio da busca vetorial)
    for h in vec_hits:
        if h["chunk_id"] in fused:
            fused[h["chunk_id"]]["cosine_sim"] = h["score"]

    candidates = list(fused.values())
    for h in candidates:
        h["final"] = h["rrf"] * _boost(h)
    candidates.sort(key=lambda h: h["final"], reverse=True)
    candidates = candidates[:MAX_CANDIDATES]

    insufficient = best_sim < SIM_THRESHOLD
    return {"insufficient": insufficient, "best_sim": best_sim, "hits": candidates[:k], "qvec": qvec}


def main(argv=None):
    p = argparse.ArgumentParser(prog="search")
    p.add_argument("--query", required=True)
    p.add_argument("--k", type=int, default=FINAL_TOPK)
    args = p.parse_args(argv)

    res = search(args.query, k=args.k)
    print(f"melhor similaridade (cosseno): {res['best_sim']:.3f}  |  "
          f"limiar: {SIM_THRESHOLD}  |  insufficient_evidence: {res['insufficient']}\n")
    if res["insufficient"]:
        print("→ Sem evidência suficiente nas fontes para uma resposta segura.")
        return
    for i, h in enumerate(res["hits"], start=1):
        sim = f"{h['cosine_sim']:.3f}" if h.get("cosine_sim") is not None else "—"
        yr = h["publication_date"].year if h.get("publication_date") else "?"
        print(f"[{i}] rrf={h['rrf']:.4f} final={h['final']:.4f} cos={sim} "
              f"({h['source_type']}, {yr})  {h['title'][:70]}")
        print(f"    {h['section_title'] or ''}: {h['text'][:160].strip()}…")
        print(f"    {h['url']}\n")


if __name__ == "__main__":
    main(sys.argv[1:])
