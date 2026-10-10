"""Ingestão em massa do corpus curado (app/topics.py).

Para cada tema: PubMed ordenado por RELEVÂNCIA, últimos ~10 anos, só evidência
forte (diretriz / metanálise / revisão sistemática); se vier pouco, completa
com revisões. Retomável: temas já feitos ficam em data/bulk_ingest_state.json.

    python -m app.bulk_ingest                 # todos os temas pendentes
    python -m app.bulk_ingest --only cardiologia --limit 5
    python -m app.bulk_ingest --reset         # refaz do zero (não apaga o banco)
"""
import os
import sys
import json
import time
import argparse

from . import config, ingest
from .topics import all_topics

STATE = os.path.join(config.ROOT, "data", "bulk_ingest_state.json")
MINDATE = 2016
STRONG = (" AND (practice guideline[ptyp] OR guideline[ptyp] OR meta-analysis[ptyp]"
          " OR systematic review[ptyp])")
REVIEW = " AND review[ptyp]"
NOT_RETRACTED = " NOT retracted publication[ptyp] NOT retraction of publication[ptyp]"
STRONG_RETMAX = 8
REVIEW_RETMAX = 4
MIN_STRONG = 4


def _load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"done": {}}


def _save_state(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def _with_retry(fn, *a, tries=4):
    for i in range(tries):
        try:
            return fn(*a)
        except Exception as e:
            if i == tries - 1:
                raise
            wait = 2 ** (i + 1)
            print(f"   ! {str(e)[:100]} — nova tentativa em {wait}s", flush=True)
            time.sleep(wait)


def ingest_topic(topic):
    """Devolve (novos_docs, novos_chunks, artigos_vistos)."""
    per, vecs = _with_retry(ingest.fetch_and_embed, topic + STRONG + NOT_RETRACTED,
                            STRONG_RETMAX, MINDATE)
    seen = len(per)
    nd, nc = ingest.persist(per, vecs) if per else (0, 0)
    if seen < MIN_STRONG:   # completa com revisões quando há pouca evidência forte
        time.sleep(0.4)
        per2, vecs2 = _with_retry(ingest.fetch_and_embed, topic + REVIEW + NOT_RETRACTED,
                                  REVIEW_RETMAX, MINDATE)
        seen += len(per2)
        if per2:
            d2, c2 = ingest.persist(per2, vecs2)
            nd, nc = nd + d2, nc + c2
    return nd, nc, seen


def main(argv=None):
    p = argparse.ArgumentParser(prog="bulk_ingest")
    p.add_argument("--only", help="só uma especialidade (chave de TOPICS)")
    p.add_argument("--limit", type=int, default=0, help="máx. de temas nesta execução")
    p.add_argument("--reset", action="store_true", help="ignora o estado salvo")
    args = p.parse_args(argv)

    st = {"done": {}} if args.reset else _load_state()
    todo = [(s, t) for s, t in all_topics()
            if (not args.only or s == args.only) and t not in st["done"]]
    if args.limit:
        todo = todo[:args.limit]
    print(f"[bulk] {len(todo)} temas pendentes", flush=True)

    tot_d = tot_c = 0
    t0 = time.time()
    for i, (spec, topic) in enumerate(todo, 1):
        try:
            nd, nc, seen = ingest_topic(topic)
        except Exception as e:
            print(f"[{i}/{len(todo)}] {spec} · {topic}: FALHOU {str(e)[:120]}", flush=True)
            continue
        tot_d += nd; tot_c += nc
        st["done"][topic] = {"spec": spec, "seen": seen, "new_docs": nd, "new_chunks": nc}
        _save_state(st)
        print(f"[{i}/{len(todo)}] {spec} · {topic}: {seen} artigos, +{nd} docs/+{nc} trechos",
              flush=True)
        time.sleep(0.4)   # E-utilities sem API key: ≤3 req/s
    print(f"[bulk] fim: +{tot_d} documentos, +{tot_c} trechos em {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
