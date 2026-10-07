"""Eval offline (spec §6.2): busca (recall@6, 1º acerto), resposta (fidelidade/
cobertura via LLM-as-judge), recusa, e latência p50/p95. Grava baseline em
docs/eval-history.md.

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


def _relevant_hit(hit, terms):
    blob = ((hit.get("title") or "") + " " + (hit.get("text") or "")).lower()
    return all(t.lower() in blob for t in terms)


def _judge(question, answer, cited_text, key_points):
    rubric = open(RUBRIC, encoding="utf-8").read()
    user = (f"Pergunta: {question}\n\nResposta do assistente:\n{answer}\n\n"
            f"Trechos citados (evidência disponível):\n{cited_text or '(nenhum)'}\n\n"
            f"Pontos-chave esperados: {json.dumps(key_points, ensure_ascii=False)}")
    try:
        out = llm.chat([{"role": "system", "content": rubric},
                        {"role": "user", "content": user}], temperature=0, max_tokens=200)
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group(0))
        return float(d.get("faithfulness", 0)), float(d.get("coverage", 0))
    except Exception:
        return None, None


def run(path=GOLDEN):
    items = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    recalls, firsts, faiths, covs = [], [], [], []
    false_refusals = 0
    refusal_total = refusal_ok = 0
    t_search, t_total = [], []
    rows = []

    for it in items:
        q = it["question"]
        t0 = time.perf_counter()
        res = search.search(q, k=6)
        t_s = time.perf_counter() - t0
        hits = res["hits"]

        refused = res["insufficient"] or not hits
        answer_text, cited_text = "", ""
        if not refused:
            messages, sources = synthesize.build(q, hits[:5])
            answer_text = llm.chat(messages).strip()
            if answer_text.upper().startswith(synthesize.SENTINEL):
                refused = True
            else:
                tbn = {i + 1: (h.get("text") or "") for i, h in enumerate(hits[:5])}
                used = synthesize.used_sources(answer_text, sources)
                cited_text = "\n".join(tbn.get(s["n"], "") for s in used)
        t_total.append(time.perf_counter() - t0)
        t_search.append(t_s)

        typ = it["type"]
        verdict = ""
        if typ == "answerable":
            terms = it.get("relevant_terms", [])
            rec = any(_relevant_hit(h, terms) for h in hits) if terms else False
            fst = _relevant_hit(hits[0], terms) if (hits and terms) else False
            recalls.append(1 if rec else 0)
            firsts.append(1 if fst else 0)
            if refused:
                false_refusals += 1
                verdict = "RECUSA INDEVIDA"
            else:
                f, c = _judge(q, answer_text, cited_text, it.get("key_points", []))
                if f is not None:
                    faiths.append(f); covs.append(c)
                verdict = f"fiel={f} cob={c}" if f is not None else "juiz falhou"
        else:  # no_evidence | out_of_scope → espera recusa
            refusal_total += 1
            if refused:
                refusal_ok += 1; verdict = "recusou (ok)"
            else:
                verdict = "RESPONDEU (deveria recusar)"
        rows.append((it["id"], typ, verdict))

    n_ans = len(recalls)
    metrics = {
        "recall@6": round(sum(recalls) / n_ans, 3) if n_ans else None,
        "first_hit": round(sum(firsts) / n_ans, 3) if n_ans else None,
        "false_refusal_rate": round(false_refusals / n_ans, 3) if n_ans else None,
        "refusal_accuracy": round(refusal_ok / refusal_total, 3) if refusal_total else None,
        "faithfulness_mean": round(statistics.mean(faiths), 3) if faiths else None,
        "coverage_mean": round(statistics.mean(covs), 3) if covs else None,
        "latency_search_p50": round(_pct(t_search, .5), 2),
        "latency_search_p95": round(_pct(t_search, .95), 2),
        "latency_total_p50": round(_pct(t_total, .5), 2),
        "latency_total_p95": round(_pct(t_total, .95), 2),
    }
    return metrics, rows


def _write_history(metrics):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    line = (f"| {ts} | {config.OPENAI_MODEL} | clinical_answer.v1 | "
            f"{metrics['recall@6']} | {metrics['first_hit']} | {metrics['refusal_accuracy']} | "
            f"{metrics['false_refusal_rate']} | {metrics['faithfulness_mean']} | "
            f"{metrics['coverage_mean']} | {metrics['latency_total_p50']} | {metrics['latency_total_p95']} |\n")
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
