"""Servidor FastAPI do assistente (spec §5.2 / §8.5).

Endpoint SSE /ask: envia as FONTES assim que a busca termina (antes do LLM),
depois faz o streaming do texto da resposta. Recusa (insufficient_evidence) é
decidida antes do LLM pelo limiar da busca.

Rodar:  uvicorn app.server:app --reload --port 8000
"""
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse

from . import search, synthesize, llm, validate, db

app = FastAPI(title="OpenDoctor Assistant")


@app.on_event("startup")
def _warm_pool():
    # abre o pool no startup p/ a 1ª requisição já pegar conexão quente
    try:
        db.get_pool()
    except Exception:
        pass


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

    # texto de cada trecho por número de citação, p/ a validação (spec §6.1)
    allowed_ns = set(range(1, len(res["hits"]) + 1))
    text_by_n = {i + 1: (h.get("text") or "") for i, h in enumerate(res["hits"])}

    # 3) streaming VALIDADO por frase: só envia a frase depois de checá-la
    buf = validate.SentenceBuffer()
    cited, emitted_any, first_checked = set(), False, False

    def _handle(sentence):
        """Valida e devolve (evento_sse, parar?)."""
        nonlocal first_checked, emitted_any
        if not first_checked:
            first_checked = True
            if sentence.upper().startswith(synthesize.SENTINEL):
                return _sse("insufficient", {"text": synthesize.REFUSAL}), True
        ok, reason = validate.validate_sentence(sentence, allowed_ns, text_by_n)
        if not ok:
            return _sse("halted", {"reason": reason,
                                   "warning": "Não consegui sintetizar o restante com segurança. "
                                              "Veja os trechos recuperados acima."}), True
        cited.update(validate.citations(sentence))
        emitted_any = True
        return _sse("sentence", {"text": sentence}), False

    try:
        halted = False
        for delta in llm.stream_chat(messages):
            for sentence in buf.feed(delta):
                ev, stop = _handle(sentence)
                yield ev
                if stop:
                    halted = True
                    break
            if halted:
                break
        if not halted:
            tail = buf.flush()
            if tail:
                ev, stop = _handle(tail)
                yield ev
                halted = stop
    except Exception as e:
        yield _sse("error", {"message": str(e)[:200]})
        return

    yield _sse("done", {"insufficient": not emitted_any, "cited": sorted(cited), "halted": halted})


@app.get("/ask")
def ask(query: str, k: int = 5):
    if not query.strip():
        return JSONResponse({"error": "query vazia"}, status_code=400)
    return StreamingResponse(_ask_stream(query, k), media_type="text/event-stream")
