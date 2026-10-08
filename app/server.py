"""Servidor FastAPI do assistente (spec §5.2 / §8.5).

Endpoint SSE /ask: envia as FONTES assim que a busca termina (antes do LLM),
depois faz o streaming do texto da resposta. Recusa (insufficient_evidence) é
decidida antes do LLM pelo limiar da busca.

Rodar:  uvicorn app.server:app --reload --port 8000
"""
import os
import json
import datetime
import threading

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import search, synthesize, llm, validate, db, config, ingest, integrations, auth

app = FastAPI(title="OpenDoctor Assistant")
WEB_DIR = os.path.join(config.ROOT, "web")

# Abaixo deste cosseno, a evidência local é fraca → consulta o PubMed ao vivo
# antes de responder (em vez de recusar). Acima, usa só o corpus (mais rápido).
FETCH_SIM = 0.62

# filtro p/ priorizar artigos que RESUMEM conduta (revisões/diretrizes/metanálises)
_EVID_FILTER = (" AND (review[ptyp] OR systematic review[ptyp] OR "
                "meta-analysis[ptyp] OR practice guideline[ptyp])")


@app.on_event("startup")
def _warm_pool():
    # abre o pool no startup p/ a 1ª requisição já pegar conexão quente
    try:
        db.get_pool()
    except Exception:
        pass


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
def root():
    # raiz do site cai na agenda (home do app)
    return RedirectResponse("/opendoctor-agenda.html")


@app.get("/health")
def health():
    return {"ok": True, "model": llm.config.OPENAI_MODEL}


def _pubmed_terms(question):
    """Gera uma query do PubMed em inglês a partir da pergunta (PT) do médico."""
    try:
        t = llm.chat([
            {"role": "system", "content": "Converta a pergunta clínica em uma consulta de busca do "
             "PubMed em INGLÊS: apenas os termos-chave relevantes (condição, intervenção, desfecho), "
             "sem aspas, sem operadores e sem explicação."},
            {"role": "user", "content": question}], temperature=0, max_tokens=40).strip()
        return t or question
    except Exception:
        return question


def _rank_fresh(qvec, per, vecs, k):
    """Ranqueia em memória os chunks recém-buscados (cosseno), sem tocar no banco.
    Embeddings da OpenAI são normalizados → produto escalar == cosseno."""
    meta = []
    for a, ch in per:
        for section, text in ch:
            meta.append((a, section, text))
    scored = []
    for i, v in enumerate(vecs):
        dot = 0.0
        for x, y in zip(qvec, v):
            dot += x * y
        scored.append((dot, i))
    scored.sort(reverse=True)
    hits = []
    for sim, i in scored[:k]:
        a, section, text = meta[i]
        yr = a.get("year")
        hits.append({
            "chunk_id": -(i + 1), "document_id": None, "section_title": section,
            "text": text, "title": a["title"], "url": a["url"], "source_type": "article",
            "publication_date": datetime.date(yr, 1, 1) if yr else None,
            "score": sim, "cosine_sim": sim,
        })
    return hits


def _safe_persist(per, vecs):
    try:
        ingest.persist(per, vecs)
    except Exception as e:
        print("[ask] persist em background falhou:", str(e)[:200])


def _ask_stream(query, k):
    # 1) busca local — decide suficiência antes de chamar o LLM
    res = search.search(query, k=k)
    yield _sse("status", {"stage": "searched", "best_sim": round(res["best_sim"], 3)})

    # 2) se a evidência local for fraca, CONSULTA o PubMed ao vivo antes de responder.
    #    Ranqueia em memória (responde já) e persiste no banco em 2º plano (cache).
    if res["best_sim"] < FETCH_SIM or not res["hits"]:
        yield _sse("status", {"stage": "fetching"})
        per, vecs = [], []
        try:
            terms = _pubmed_terms(query)
            # 1º tenta revisões/diretrizes (resumem conduta); se vier vazio, busca ampla
            per, vecs = ingest.fetch_and_embed(terms + _EVID_FILTER, 12)
            if not per:
                per, vecs = ingest.fetch_and_embed(terms, 12)
        except Exception as e:
            print("[ask] fetch on-demand falhou:", str(e)[:200])
        if per:
            fresh = _rank_fresh(res.get("qvec"), per, vecs, k)
            threading.Thread(target=_safe_persist, args=(per, vecs), daemon=True).start()
            best = max((h["score"] for h in fresh), default=0.0)
            res = {"insufficient": best < search.SIM_THRESHOLD, "best_sim": best,
                   "hits": fresh, "qvec": res.get("qvec")}
        yield _sse("status", {"stage": "refetched", "best_sim": round(res["best_sim"], 3)})

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

    # 3) streaming VALIDADO por frase: só envia a frase que passar nas checagens.
    #    Frase que falhar é PULADA (não interrompe o resto) — uma frase ruim
    #    nunca zera a resposta. Só recusa se NENHUMA frase passar.
    buf = validate.SentenceBuffer()
    cited, emitted_any, first_checked, skipped, stop = set(), False, False, 0, False

    def _handle(sentence):
        """Valida e devolve (evento_sse ou None, parar?)."""
        nonlocal first_checked, emitted_any, skipped
        if not first_checked:
            first_checked = True
            if sentence.upper().startswith(synthesize.SENTINEL):
                return None, True   # modelo sinalizou insuficiência
        ok, _reason = validate.validate_sentence(sentence, allowed_ns, text_by_n)
        if not ok:
            skipped += 1
            return None, False      # pula a frase, continua
        cited.update(validate.citations(sentence))
        emitted_any = True
        return _sse("sentence", {"text": sentence}), False

    try:
        for delta in llm.stream_chat(messages):
            for sentence in buf.feed(delta):
                ev, stop = _handle(sentence)
                if ev:
                    yield ev
                if stop:
                    break
            if stop:
                break
        if not stop:
            tail = buf.flush()
            if tail:
                ev, stop = _handle(tail)
                if ev:
                    yield ev
    except Exception as e:
        yield _sse("failed", {"message": str(e)[:200]})
        return

    if not emitted_any:
        yield _sse("insufficient", {"text": synthesize.REFUSAL})
    yield _sse("done", {"insufficient": not emitted_any, "cited": sorted(cited), "skipped": skipped})


@app.get("/ask")
def ask(query: str, k: int = 5):
    if not query.strip():
        return JSONResponse({"error": "query vazia"}, status_code=400)
    return StreamingResponse(_ask_stream(query, k), media_type="text/event-stream")


# ===== login do app (Google, escopos básicos) =====
@app.get("/auth/google/login")
def google_login():
    if not integrations.configured("google"):
        return JSONResponse({"error": "google não configurado"}, status_code=400)
    return RedirectResponse(auth.login_url())


@app.get("/auth/logout")
def logout():
    resp = RedirectResponse("/opendoctor-agenda.html")
    auth.clear_session(resp)
    return resp


@app.get("/me")
def me(request: Request):
    u = auth.current_user(request)
    return {"logged_in": bool(u), "user": u}


# ===== integrações de calendário (OAuth, por usuário) =====
@app.get("/integrations/status")
def integrations_status(request: Request):
    u = auth.current_user(request)
    out = integrations.status(u["id"] if u else None)
    return {"logged_in": bool(u), "providers": out}


@app.get("/integrations/{provider}/connect")
def integrations_connect(provider: str, request: Request):
    if provider not in integrations.PROVIDERS:
        return JSONResponse({"error": "provedor inválido"}, status_code=404)
    if not integrations.configured(provider):
        return JSONResponse({"error": f"{provider} não configurado"}, status_code=400)
    u = auth.current_user(request)
    if not u:
        # precisa estar logado para conectar um calendário a uma conta
        return RedirectResponse("/auth/google/login")
    state = auth.sign({"k": "cal", "prov": provider, "uid": u["id"]})
    return RedirectResponse(integrations.connect_url(provider, state))


@app.get("/auth/{provider}/callback")
def auth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    """Callback único por provedor: distingue login x conexão de calendário pelo `state`."""
    payload = auth.unsign(state, auth.STATE_MAX_AGE) if state else None
    if error or not code or not payload:
        dest = "/opendoctor-integracao.html" if (payload or {}).get("k") == "cal" else "/opendoctor-agenda.html"
        return RedirectResponse(dest + "?erro=" + (error or "sem_code"))

    # --- login do app (só Google) ---
    if payload.get("k") == "login":
        try:
            info = auth.exchange_login(code)
            user = db.upsert_user(info["email"], info.get("name"),
                                  info.get("picture"), info.get("sub"))
            resp = RedirectResponse("/opendoctor-agenda.html?login=ok")
            auth.set_session(resp, user["id"])
            return resp
        except Exception as e:
            print("[auth] login falhou:", str(e)[:200])
            return RedirectResponse("/opendoctor-agenda.html?erro=login")

    # --- conexão de calendário ---
    if payload.get("k") == "cal":
        dest = "/opendoctor-integracao.html"
        try:
            integrations.exchange_and_store(provider, code, payload["uid"])
            return RedirectResponse(dest + "?conectado=" + provider)
        except Exception as e:
            print("[oauth] callback falhou:", str(e)[:200])
            return RedirectResponse(dest + "?erro=" + provider)

    return RedirectResponse("/opendoctor-agenda.html?erro=state")


@app.post("/integrations/{provider}/disconnect")
def integrations_disconnect(provider: str, request: Request):
    u = auth.current_user(request)
    if not u:
        return JSONResponse({"error": "não autenticado"}, status_code=401)
    integrations.disconnect(u["id"], provider)
    return {"ok": True}


@app.get("/integrations/{provider}/events")
def integrations_events(provider: str, request: Request, limit: int = 10):
    if provider not in integrations.PROVIDERS:
        return JSONResponse({"error": "provedor inválido"}, status_code=404)
    u = auth.current_user(request)
    if not u:
        return JSONResponse({"error": "não autenticado"}, status_code=401)
    return {"events": integrations.events(u["id"], provider, limit)}


# serve o front-end (web/) na mesma origem — registrado por último para não
# sombrear as rotas acima. Abra http://127.0.0.1:8000/opendoctor-agenda.html
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
