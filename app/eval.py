"""Eval offline (spec §6.2) sobre o MESMO pipeline do /ask de produção:
busca (recall@6, 1º acerto), fidelidade/cobertura (LLM-as-judge), escopo,
recusa indevida, cálculo determinístico, afirmações sem fonte e latência.
Grava baseline em docs/eval-history.md.

Rodar:  python -m app.eval            # usa evals/golden.jsonl
"""
import os
import re
import sys
import json
import time
import argparse
import datetime
import statistics

from . import config, search, synthesize, llm

GOLDEN = os.path.join(config.ROOT, "evals", "golden.jsonl")
RUBRIC = os.path.join(config.ROOT, "evals", "rubric.md")
BASELINE = os.path.join(config.ROOT, "evals", "baseline.json")
HISTORY = os.path.join(config.ROOT, "docs", "eval-history.md")


def check_regression(metrics):
    """Compara com os limiares de evals/baseline.json. Retorna lista de falhas."""
    bl = json.load(open(BASELINE, encoding="utf-8"))
    fails = []
    for k, floor in bl.get("min", {}).items():
        v = metrics.get(k)
        if v is None or v < floor:
            fails.append(f"{k}={v} abaixo do mínimo {floor}")
    for k, ceil in bl.get("max", {}).items():
        v = metrics.get(k)
        if v is None or v > ceil:
            fails.append(f"{k}={v} acima do máximo {ceil}")
    return fails


def _pct(xs, p):
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _relevant(title_or_text, terms):
    blob = (title_or_text or "").lower()
    return all(t.lower() in blob for t in terms)


def _judge(question, answer, cited_text, key_points):
    rubric = open(RUBRIC, encoding="utf-8").read()
    user = (f"Pergunta: {question}\n\nResposta do assistente:\n{answer}\n\n"
            f"Trechos recuperados (evidência disponível):\n{cited_text or '(nenhum)'}\n\n"
            f"Pontos-chave esperados: {json.dumps(key_points, ensure_ascii=False)}")
    try:
        out = llm.chat([{"role": "system", "content": rubric},
                        {"role": "user", "content": user}], temperature=0, max_tokens=200)
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group(0))
        return float(d.get("faithfulness", 0)), float(d.get("coverage", 0))
    except Exception:
        return None, None


def _parse_sse(chunks):
    """Converte as strings SSE do _ask_stream em eventos (nome, dict)."""
    for ch in chunks:
        ev, data = None, None
        for line in ch.splitlines():
            if line.startswith("event: "):
                ev = line[7:].strip()
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            yield ev, (data or {})


def _run_pipeline(question, history=None):
    """Roda o MESMO pipeline do /ask de produção e coleta o resultado."""
    from . import server
    seen = {}
    orig_build = synthesize.build

    def spy(query, hits, history=None, extra=None):
        seen["hits"] = hits
        return orig_build(query, hits, history, extra)

    synthesize.build = spy
    try:
        t0 = time.perf_counter()
        out = {"answer": "", "sources": [], "insufficient": False, "out_of_scope": False,
               "done": {}, "msg": ""}
        for ev, d in _parse_sse(server._ask_stream(question, 6, history or [])):
            if ev == "sentence":
                if "first" not in out:
                    out["first"] = time.perf_counter() - t0
                out["answer"] += d.get("text", "")
            elif ev == "sources":
                out["sources"] = d.get("sources", [])
            elif ev == "insufficient":
                out["insufficient"] = True
                out["msg"] = d.get("text", "")
            elif ev == "failed":
                out["insufficient"] = True
                out["msg"] = "FALHA: " + d.get("message", "")
            elif ev == "done":
                out["done"] = d
                out["out_of_scope"] = bool(d.get("out_of_scope"))
        out["latency"] = time.perf_counter() - t0
        out["hits"] = seen.get("hits") or []
        return out
    finally:
        synthesize.build = orig_build


def run(path=GOLDEN):
    items = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    recalls, firsts, faiths, covs, lat, ttft = [], [], [], [], [], []
    n_medical = declined_medical = 0
    oos_total = oos_ok = 0
    ungrounded, cites_removed, calc_ok, calc_total = [], 0, 0, 0
    rows = []

    for it in items:
        q, typ = it["question"], it["type"]
        r = _run_pipeline(q, it.get("history"))
        lat.append(r["latency"])
        if "first" in r:
            ttft.append(r["first"])
        verdict = ""

        if typ == "out_of_scope":
            oos_total += 1
            if r["out_of_scope"] or (r["insufficient"] and not r["answer"]):
                oos_ok += 1; verdict = "declinou (ok)"
            else:
                verdict = "RESPONDEU tema fora do escopo"
            rows.append((it["id"], typ, verdict))
            continue

        # perguntas clínicas: devem SEMPRE ser respondidas
        n_medical += 1
        if r["insufficient"] or not r["answer"].strip():
            declined_medical += 1
            rows.append((it["id"], typ, "NÃO RESPONDEU: " + r["msg"][:60]))
            continue

        terms = it.get("relevant_terms") or []
        if typ == "answerable" and terms:
            # título + texto dos trechos que o modelo efetivamente recebeu
            blobs = [(h.get("title") or "") + " " + (h.get("text") or "") for h in r["hits"]]
            recalls.append(1 if any(_relevant(b, terms) for b in blobs) else 0)
            firsts.append(1 if blobs and _relevant(blobs[0], terms) else 0)

        if typ == "calc":
            calc_total += 1
            want = it.get("expect_number", "")
            ok = want and (want in r["answer"] or want.replace(",", ".") in r["answer"])
            calc_ok += 1 if ok else 0

        d = r["done"] or {}
        ungrounded.append(d.get("ungrounded", 0))
        cites_removed += d.get("citations_removed", 0) or 0
        hit_text = "\n\n".join(f"[{i + 1}] {h.get('title', '')}\n{(h.get('text') or '')[:1500]}"
                                for i, h in enumerate(r["hits"]))
        f, c = _judge(q, r["answer"], hit_text, it.get("key_points", []))
        if f is not None:
            faiths.append(f); covs.append(c)
        verdict = (f"fiel={f} cob={c}" if f is not None else "juiz falhou") + \
                  f" sem_fonte={d.get('ungrounded', 0)} cit_removidas={d.get('citations_removed', 0)}"
        rows.append((it["id"], typ, verdict))

    metrics = {
        "recall@6": round(sum(recalls) / len(recalls), 3) if recalls else None,
        "first_hit": round(sum(firsts) / len(firsts), 3) if firsts else None,
        "false_refusal_rate": round(declined_medical / n_medical, 3) if n_medical else None,
        "out_of_scope_accuracy": round(oos_ok / oos_total, 3) if oos_total else None,
        "calc_accuracy": round(calc_ok / calc_total, 3) if calc_total else None,
        "faithfulness_mean": round(statistics.mean(faiths), 3) if faiths else None,
        "coverage_mean": round(statistics.mean(covs), 3) if covs else None,
        "ungrounded_mean": round(statistics.mean(ungrounded), 2) if ungrounded else None,
        "citations_removed": cites_removed,
        "latency_first_p50": round(_pct(ttft, .5), 2),
        "latency_first_p95": round(_pct(ttft, .95), 2),
        "latency_total_p50": round(_pct(lat, .5), 2),
        "latency_total_p95": round(_pct(lat, .95), 2),
    }
    return metrics, rows


def _write_history(metrics):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = (f"| {ts} | {config.OPENAI_MODEL} | clinical_answer.v3 | "
            f"{metrics['recall@6']} | {metrics['first_hit']} | {metrics['out_of_scope_accuracy']} | "
            f"{metrics['false_refusal_rate']} | {metrics['faithfulness_mean']} | "
            f"{metrics['coverage_mean']} | {metrics['latency_total_p50']} | {metrics['latency_total_p95']} |"
            f" calc={metrics['calc_accuracy']} sem_fonte={metrics['ungrounded_mean']} |\n")
    new = not os.path.exists(HISTORY)
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as fh:
        if new:
            fh.write("# Histórico de eval\n\n"
                     "| data | modelo | prompt | recall@6 | 1º acerto | recusa_acc | "
                     "recusa_indevida | fidelidade | cobertura | lat_p50(s) | lat_p95(s) |\n"
                     "|---|---|---|---|---|---|---|---|---|---|---|\n")
        fh.write(line)


def main(argv=None):
    p = argparse.ArgumentParser(prog="eval")
    p.add_argument("--no-history", action="store_true", help="não grava em docs/eval-history.md")
    p.add_argument("--check", action="store_true",
                   help="falha (exit 1) se alguma métrica cruzar os limiares de evals/baseline.json")
    args = p.parse_args(argv)

    metrics, rows = run()
    print("=== por item ===")
    for rid, typ, verdict in rows:
        print(f"  {rid:16s} [{typ:12s}] {verdict}")
    print("\n=== métricas ===")
    for k, v in metrics.items():
        print(f"  {k:22s} {v}")
    if not args.no_history:
        _write_history(metrics)
        print(f"\nbaseline registrada em docs/eval-history.md")
    if args.check:
        fails = check_regression(metrics)
        if fails:
            print("\n❌ REGRESSÃO detectada:")
            for f in fails:
                print("  - " + f)
            sys.exit(1)
        print("\n✅ eval dentro dos limiares (evals/baseline.json)")


if __name__ == "__main__":
    main(argv=None)
