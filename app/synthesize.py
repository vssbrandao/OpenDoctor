"""Síntese (spec §5): monta o prompt com os trechos numerados, chama o LLM,
mapeia [n] → fonte. Decide insufficient_evidence antes do LLM (limiar da busca)
ou pela frase-sentinela do modelo.

CLI:  python -m app.search ... (busca)   |   python -m app.synthesize --query "..."
"""
import os
import re
import sys
import argparse

from . import search, llm, config

PROMPT_PATH = os.path.join(config.ROOT, "prompts", "clinical_answer.v3.md")
SENTINEL = "EVIDENCIA_INSUFICIENTE"
REFUSAL = "Não encontrei evidência científica suficiente nas fontes para uma resposta segura."


def load_prompt():
    with open(PROMPT_PATH, encoding="utf-8") as fh:
        return fh.read().strip()


def _source_label(hit):
    yr = hit["publication_date"].year if hit.get("publication_date") else "s/d"
    doi = ""
    url = hit.get("url") or ""
    if "doi.org/" in url:
        doi = " · DOI: " + url.split("doi.org/", 1)[1]
    return f"{hit.get('source_type','?')}, {yr}{doi}"


def build(query, hits, history=None, extra=None):
    """Devolve (messages, sources) — sources[i] corresponde a [i+1].
    history: turnos anteriores [{role:'user'|'assistant', content}] p/ follow-ups.
    extra: bloco determinístico (ex.: cálculo de eGFR) a ser usado pelo modelo."""
    blocks = []
    sources = []
    for i, h in enumerate(hits, start=1):
        head = f"[{i}] ({_source_label(h)}) {h.get('title','')}"
        if h.get("section_title"):
            head += f" — {h['section_title']}"
        blocks.append(head + "\n" + (h.get("text") or "").strip())
        sources.append({
            "n": i, "chunk_id": h["chunk_id"], "document_id": h["document_id"],
            "title": h.get("title"), "url": h.get("url"),
            "source_type": h.get("source_type"), "evidence": h.get("evidence"),
            "year": h["publication_date"].year if h.get("publication_date") else None,
            "section_title": h.get("section_title"),
        })
    excerpts = "\n\n".join(blocks) if blocks else "(nenhum trecho recuperado)"
    user = ("Trechos (cite com [n]):\n\n" + excerpts +
            (f"\n\n{extra}" if extra else "") +
            f"\n\nPergunta do médico: {query}")
    messages = [{"role": "system", "content": load_prompt()}]
    for m in (history or []):
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:4000]})
    messages.append({"role": "user", "content": user})
    return messages, sources


def used_sources(answer, sources):
    cited = set(int(n) for n in re.findall(r"\[(\d+)\]", answer))
    return [s for s in sources if s["n"] in cited]


def answer(query, k=5):
    res = search.search(query, k=k)
    # não recusa por falta de evidência: sintetiza com os trechos disponíveis
    # (fracos ou vazios) e deixa o modelo complementar com conhecimento consolidado.
    messages, sources = build(query, res.get("hits") or [])
    text = llm.chat(messages).strip()
    if text.upper().startswith(SENTINEL):
        return {"insufficient": True, "answer": REFUSAL, "sources": [],
                "best_sim": res["best_sim"]}
    return {"insufficient": False, "answer": text,
            "sources": used_sources(text, sources), "all_sources": sources,
            "best_sim": res["best_sim"]}


def main(argv=None):
    p = argparse.ArgumentParser(prog="synthesize")
    p.add_argument("--query", required=True)
    p.add_argument("--k", type=int, default=5)
    args = p.parse_args(argv)

    res = answer(args.query, k=args.k)
    print(f"(best_sim={res['best_sim']:.3f} · insufficient={res['insufficient']})\n")
    print(res["answer"])
    if res.get("sources"):
        print("\n--- Fontes citadas ---")
        for s in res["sources"]:
            yr = s["year"] or "s/d"
            print(f"[{s['n']}] ({s['source_type']}, {yr}) {s['title'][:70]}\n     {s['url']}")


if __name__ == "__main__":
    main(sys.argv[1:])
