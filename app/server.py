"""Servidor FastAPI do assistente (spec §5.2 / §8.5).

Endpoint SSE /ask: envia as FONTES assim que a busca termina (antes do LLM),
depois faz o streaming do texto da resposta. Recusa (insufficient_evidence) é
decidida antes do LLM pelo limiar da busca.

Rodar:  uvicorn app.server:app --reload --port 8000
"""
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse

from . import search, synthesize, llm

app = FastAPI(title="OpenDoctor Assistant")


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
def health():
    return {"ok": True, "model": llm.config.OPENAI_MODEL}


def _ask_stream(query, k):
    # 1) busca — decide suficiência antes de chamar o LLM
    res = search.search(query, k=k)
    yield _sse("status", {"stage": "searched", "best_sim": round(res["best_sim"], 3)})

    if res["insufficient"] or not res["hits"]:
        yield _sse("insufficient", {"text": synthesize.REFUSAL})
        yield _sse("done", {"insufficient": True})
        return

    # 2) fontes ANTES da resposta (alavanca de latência percebida)
    messages, sources = synthesize.build(query, res["hits"])
    yield _sse("sources", {"sources": sources})

    # 3) streaming do texto
    full = []
    try:
        for delta in llm.stream_chat(messages):
            full.append(delta)
            yield _sse("token", {"delta": delta})
    except Exception as e:
        yield _sse("error", {"message": str(e)[:200]})
        return

    text = "".join(full).strip()
    if text.upper().startswith(synthesize.SENTINEL):
        # modelo sinalizou insuficiência apesar do limiar
        yield _sse("insufficient", {"text": synthesize.REFUSAL})
        yield _sse("done", {"insufficient": True})
        return

    used = synthesize.used_sources(text, sources)
    yield _sse("done", {"insufficient": False, "cited": [s["n"] for s in used]})


@app.get("/ask")
def ask(query: str, k: int = 5):
    if not query.strip():
        return JSONResponse({"error": "query vazia"}, status_code=400)
    return StreamingResponse(_ask_stream(query, k), media_type="text/event-stream")
