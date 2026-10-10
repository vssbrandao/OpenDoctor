"""Busca híbrida (spec §4): vetorial ∥ full-text → RRF → boost → limiar.

Sem rerank nesta fase (MVP). O limiar de suficiência usa a melhor similaridade
de cosseno da busca vetorial — provisório, a ser calibrado com o eval na F5.

CLI:  python -m app.search --query "..." [--k 5]
"""
import re
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
# calibrado (10/10/2026) com a pergunta em INGLÊS: relevantes 0,50–0,79;
# irrelevantes 0,29–0,46. Abaixo disso o trecho não vai ao modelo nem vira fonte.
REL_FLOOR = 0.48
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


def _fts_search(conn, query, limit, qvec):
    """Full-text; devolve também o cosseno do trecho com a pergunta, para que
    todo candidato possa passar pelo corte de relevância (REL_FLOOR)."""
    lit = _vec_literal(qvec)
    with conn.cursor() as cur:
        cur.execute(
            """
            select c.id, c.document_id, c.section_title, c.text,
                   d.title, d.url, d.source_type, d.publication_date,
                   ts_rank(c.tsv, q) as fts_rank,
                   1 - (c.embedding <=> %s::vector) as cosine_sim
            from chunks c
            join documents d on d.id = c.document_id,
                 websearch_to_tsquery(%s, %s) q
            where c.tsv @@ q
            order by fts_rank desc
            limit %s
            """,
            (lit, FTS_CONFIG, query, limit),
        )
        return cur.fetchall()


# ===== nível de evidência =====
# 1º: tipo de publicação oficial do PubMed (gravado em documents.source_type);
# 2º (fallback, corpus antigo): heurística pelo título.
# Usado no rerank (prioriza evidência forte) e no selo mostrado ao médico.

# source_type gravado → (label, peso)
_SOURCE_TYPE_LEVEL = {
    "guideline": ("Diretriz", 5), "protocol": ("Diretriz", 5),
    "meta-analysis": ("Metanálise", 4), "systematic-review": ("Revisão sistemática", 4),
    "rct": ("Ensaio clínico", 3), "secondary-analysis": ("Análise secundária", 2),
    "observational": ("Observacional", 2), "review": ("Revisão", 2),
}

# PublicationType do PubMed → source_type (em ordem de força)
_PUBTYPE_MAP = [
    (("practice guideline", "guideline", "consensus development conference"), "guideline"),
    (("meta-analysis",), "meta-analysis"),
    (("systematic review",), "systematic-review"),
    (("randomized controlled trial", "clinical trial, phase iii", "clinical trial, phase iv",
      "equivalence trial", "pragmatic clinical trial"), "rct"),
    (("observational study", "comparative study", "multicenter study"), "observational"),
    (("review",), "review"),
]


def source_type_from_pubtypes(pub_types):
    """Mapeia a lista de PublicationType do PubMed p/ um source_type gravável."""
    pts = [p.lower() for p in (pub_types or [])]
    for keys, st in _PUBTYPE_MAP:
        if any(k in pts for k in keys):
            return st
    return "article"


# heurística por título (só p/ documentos sem tipo de publicação)
_RE = re.compile
_TITLE_RULES = [
    # análise secundária ANTES de ensaio clínico (senão "post hoc ... randomized" vira ECR)
    (_RE(r"post[- ]hoc|secondary analysis|sub-?analysis|subgroup analysis|exploratory analysis"),
     "Análise secundária", 2),
    # diretriz só com padrões de documento normativo (não "guideline adherence/-directed")
    (_RE(r"(practice|clinical) guideline|guidelines? (for|on)|consensus statement|"
         r"position statement|recommendations? (for|on)|scientific statement"),
     "Diretriz", 5),
    (_RE(r"meta-?analys[ie]s|metanálise|umbrella review|network meta"), "Metanálise", 4),
    (_RE(r"systematic review"), "Revisão sistemática", 4),
    (_RE(r"randomi[sz]ed|double-blind|placebo-controlled|controlled trial"), "Ensaio clínico", 3),
    (_RE(r"cohort|case-?control|observational|retrospective|prospective|registry|real-world"),
     "Observacional", 2),
    (_RE(r"\breview\b|overview|state of the art|update on"), "Revisão", 2),
]


def evidence_level(title, source_type=None):
    """Devolve (label, peso 1–5) estimando a força da evidência."""
    if source_type in _SOURCE_TYPE_LEVEL:
        return _SOURCE_TYPE_LEVEL[source_type]
    t = (title or "").lower()
    for rx, label, w in _TITLE_RULES:
        if rx.search(t):
            return (label, w)
    return ("Artigo", 1)


def _row_to_hit(row):
    (cid, doc_id, section, text, title, url, source_type, pub_date, score) = row
    lbl, w = evidence_level(title, source_type)
    return {
        "chunk_id": cid, "document_id": doc_id, "section_title": section,
        "text": text, "title": title, "url": url,
        "source_type": source_type, "publication_date": pub_date,
        "evidence": lbl, "evidence_w": w,
        "score": float(score) if score is not None else 0.0,
    }


def _boost(hit):
    b = SOURCE_BOOST.get(hit.get("source_type"), 1.0)
    # rerank ponderado por nível de evidência (diretriz/metanálise > artigo)
    b *= 1.0 + 0.05 * (hit.get("evidence_w", 1) - 1)
    d = hit.get("publication_date")
    if d is not None:
        yr = d.year if hasattr(d, "year") else int(str(d)[:4])
        b += min(max(yr - RECENCY_BASE_YEAR, 0) * RECENCY_BOOST_PER_YEAR, RECENCY_MAX)
    return b


_STOP = {"and", "or", "the", "of", "in", "for", "with", "to", "a", "an", "on", "vs", "versus"}
# palavras genéricas: num OR, puxam qualquer artigo ("therapy", "management"...)
GENERIC_TERMS = {"management", "treatment", "treatments", "therapy", "therapies",
                 "pharmacological", "pharmacologic", "clinical", "patient", "patients",
                 "adult", "adults", "outcome", "outcomes", "efficacy", "safety", "use",
                 "risk", "care", "review", "study", "studies", "approach", "approaches",
                 "options", "guidelines", "guideline", "recommendations"}
_FTS_GENERIC = GENERIC_TERMS | {"disease", "diseases", "syndrome", "disorder", "acute", "chronic"}


def _or_query(terms):
    """'heart failure sglt2' → 'heart or failure or sglt2' (websearch_to_tsquery
    trata palavras soltas como AND; com OR o ts_rank ordena pela relevância)."""
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{1,}", terms or "")
             if w.lower() not in _STOP and w.lower() not in _FTS_GENERIC]
    return " or ".join(words[:12]) if words else (terms or "")


def _vec_pooled(qvec, limit):
    with db.connection() as conn:
        return _vector_search(conn, qvec, limit)


def _fts_pooled(query, limit, qvec):
    with db.connection() as conn:
        return _fts_search(conn, query, limit, qvec)


def search(query, k=FINAL_TOPK, qvec=None, fts_query=None):
    """Retorna dict: {insufficient: bool, best_sim: float, hits: [...]}

    query: pergunta (PT) → busca vetorial (o embedding é multilíngue).
    fts_query: termos em INGLÊS p/ o full-text (o corpus é inglês; usar a
    pergunta em PT no tsquery 'english' quase não acha nada).
    Latência: embedding (API) roda em paralelo com o full-text (DB).
    """
    fq = _or_query(fts_query) if fts_query else query
    if qvec is None:
        qvec = embeddings.embed([query])[0]
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fut_vec = ex.submit(_vec_pooled, qvec, VEC_TOPN)
        fut_fts = ex.submit(_fts_pooled, fq, FTS_TOPN, qvec) if fq.strip() else None
        vec_rows = fut_vec.result()
        fts_rows = fut_fts.result() if fut_fts else []

    vec_hits = [_row_to_hit(r) for r in vec_rows]
    fts_hits = []
    for r in fts_rows:
        h = _row_to_hit(r[:9])
        h["fts_cosine"] = float(r[9]) if r[9] is not None else None
        fts_hits.append(h)

    best_sim = max((h["score"] for h in vec_hits), default=0.0)

    # Reciprocal Rank Fusion
    fused = {}   # chunk_id -> hit (+ rrf)
    for ranked in (vec_hits, fts_hits):
        for rank, h in enumerate(ranked, start=1):
            entry = fused.setdefault(h["chunk_id"], dict(h, rrf=0.0, cosine_sim=None))
            entry["rrf"] += 1.0 / (RRF_K + rank)
    # cosseno de cada candidato (da busca vetorial ou calculado no full-text)
    for h in fts_hits:
        if h["chunk_id"] in fused and h.get("fts_cosine") is not None:
            fused[h["chunk_id"]]["cosine_sim"] = h["fts_cosine"]
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
