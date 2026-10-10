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
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import search, synthesize, llm, validate, db, config, ingest, integrations, auth, tools

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


@app.middleware("http")
async def _no_cache_html(request: Request, call_next):
    """Impede o navegador de servir HTML velho do cache após um deploy."""
    resp = await call_next(request)
    path = request.url.path
    if path.endswith(".html") or path == "/":
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


@app.get("/")
def root():
    # raiz do site cai na agenda (home do app)
    return RedirectResponse("/opendoctor-agenda.html")


@app.get("/health")
def health():
    return {"ok": True, "model": llm.config.OPENAI_MODEL}


@app.get("/privacy")
def privacy():
    return FileResponse(os.path.join(WEB_DIR, "privacy.html"))


@app.get("/terms")
def terms():
    return FileResponse(os.path.join(WEB_DIR, "terms.html"))


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
        lbl, w = search.evidence_level(a.get("title"))
        hits.append({
            "chunk_id": -(i + 1), "document_id": None, "section_title": section,
            "text": text, "title": a["title"], "url": a["url"], "source_type": "article",
            "publication_date": datetime.date(yr, 1, 1) if yr else None,
            "evidence": lbl, "evidence_w": w,
            "score": sim, "cosine_sim": sim,
        })
    return hits


def _safe_persist(per, vecs):
    try:
        ingest.persist(per, vecs)
    except Exception as e:
        print("[ask] persist em background falhou:", str(e)[:200])


def _log(*a):
    print("[ask]", *a, flush=True)


def _ctx_query(query, history):
    """Query de BUSCA sensível ao contexto: em follow-ups curtos ('e na gestante?'),
    junta o último turno do usuário para recuperar evidência relevante."""
    if not history:
        return query
    last_user = ""
    for m in reversed(history):
        if m.get("role") == "user" and (m.get("content") or "").strip():
            last_user = m["content"].strip()
            break
    if last_user and len(query) < 80:
        return (last_user + " " + query)[:500]
    return query


def _ask_stream(query, k, history=None):
    _log("start len=", len(query), "hist=", len(history or []))
    ctxq = _ctx_query(query, history)   # query de busca (contexto p/ follow-ups)
    # 1) busca local — decide suficiência antes de chamar o LLM
    try:
        res = search.search(ctxq, k=k)
    except Exception as e:
        _log("search falhou:", str(e)[:200])
        yield _sse("failed", {"message": "Falha ao consultar o servidor. Tente novamente."})
        yield _sse("done", {"insufficient": True})
        return
    _log("searched best_sim=", round(res["best_sim"], 3), "hits=", len(res.get("hits") or []))
    yield _sse("status", {"stage": "searched", "best_sim": round(res["best_sim"], 3)})

    # 2) se a evidência local for fraca, CONSULTA o PubMed ao vivo antes de responder.
    #    Ranqueia em memória (responde já) e persiste no banco em 2º plano (cache).
    if res["best_sim"] < FETCH_SIM or not res["hits"]:
        yield _sse("status", {"stage": "fetching"})
        per, vecs = [], []
        try:
            _log("pubmed_terms…")
            terms = _pubmed_terms(ctxq)
            _log("terms=", terms[:120])
            # 1º tenta revisões/diretrizes (resumem conduta); se vier vazio, busca ampla.
            # retmax baixo p/ caber na memória do plano atual (evita derrubar o processo)
            per, vecs = ingest.fetch_and_embed(terms + _EVID_FILTER, 6)
            _log("fetch1 artigos=", len(per))
            if not per:
                per, vecs = ingest.fetch_and_embed(terms, 6)
                _log("fetch2 artigos=", len(per))
        except Exception as e:
            print("[ask] fetch on-demand falhou:", str(e)[:200], flush=True)
        if per:
            _log("rank_fresh…")
            fresh = _rank_fresh(res.get("qvec"), per, vecs, k)
            _log("rank ok; persist bg…")
            threading.Thread(target=_safe_persist, args=(per, vecs), daemon=True).start()
            best = max((h["score"] for h in fresh), default=0.0)
            res = {"insufficient": best < search.SIM_THRESHOLD, "best_sim": best,
                   "hits": fresh, "qvec": res.get("qvec")}
        yield _sse("status", {"stage": "refetched", "best_sim": round(res["best_sim"], 3)})

    # NÃO recusamos por falta de evidência: seguimos para a síntese sempre.
    # O modelo usa os trechos quando há (citando [n]) e complementa com
    # conhecimento clínico consolidado quando a evidência é fraca/ausente,
    # sinalizando o nível de evidência. Só declina perguntas NÃO-médicas.
    hits = res.get("hits") or []
    _log("synthesize best_sim=", round(res["best_sim"], 3), "hits=", len(hits))

    # 2) fontes ANTES da resposta (alavanca de latência percebida)
    # cálculos determinísticos (ex.: eGFR) — o código calcula, o modelo explica
    try:
        extra = tools.renal_note(ctxq)
    except Exception as e:
        _log("tools falhou:", str(e)[:150])
        extra = None
    if extra:
        _log("tool renal aplicado")

    _log("synthesize.build + stream…")
    messages, sources = synthesize.build(query, hits, history, extra)
    yield _sse("sources", {"sources": sources})

    # texto de cada trecho por número de citação, p/ a validação (spec §6.1)
    allowed_ns = set(range(1, len(hits) + 1))
    text_by_n = {i + 1: (h.get("text") or "") for i, h in enumerate(hits)}

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


@app.post("/ask")
async def ask_post(request: Request):
    """Versão com histórico (conversa). Body: {query, k?, history?[{role,content}]}."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query vazia"}, status_code=400)
    k = int(body.get("k") or 6)
    history = body.get("history") or []
    # mantém só os últimos turnos (controla custo/tokens)
    if isinstance(history, list):
        history = history[-8:]
    else:
        history = []
    return StreamingResponse(_ask_stream(query, k, history),
                             media_type="text/event-stream")


@app.post("/followups")
async def followups(request: Request):
    """Sugere 3 perguntas de acompanhamento curtas a partir da última resposta."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    query = (body.get("query") or "").strip()
    answer = (body.get("answer") or "").strip()
    if not answer:
        return {"suggestions": []}
    try:
        out = llm.chat([
            {"role": "system", "content": "Você gera perguntas de acompanhamento para um "
             "MÉDICO, a partir de uma resposta clínica. Devolva EXATAMENTE 3 perguntas curtas "
             "(máx. 8 palavras cada), clínicas e úteis para aprofundar (ex.: subgrupo, dose, "
             "alternativa, monitorização). Uma por linha, sem numeração, sem aspas."},
            {"role": "user", "content": f"Pergunta: {query}\n\nResposta:\n{answer[:3000]}"}],
            temperature=0.4, max_tokens=80).strip()
        sugg = [s.strip(" -•\t").strip() for s in out.splitlines() if s.strip()]
        sugg = [s for s in sugg if 3 <= len(s) <= 90][:3]
        return {"suggestions": sugg}
    except Exception as e:
        print("[followups] falhou:", str(e)[:150], flush=True)
        return {"suggestions": []}


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
def integrations_events(provider: str, request: Request, limit: int = 50,
                        start: str = "", end: str = ""):
    if provider not in integrations.PROVIDERS:
        return JSONResponse({"error": "provedor inválido"}, status_code=404)
    u = auth.current_user(request)
    if not u:
        return JSONResponse({"error": "não autenticado"}, status_code=401)
    return {"events": integrations.events(u["id"], provider, limit,
                                          start or None, end or None)}


@app.get("/calendar/events")
def calendar_events(request: Request, start: str = "", end: str = ""):
    """Eventos do provedor conectado do usuário (o que a agenda consome)."""
    u = auth.current_user(request)
    if not u:
        return {"logged_in": False, "connected": None, "events": []}
    connected = db.connected_providers(u["id"])
    if not connected:
        return {"logged_in": True, "connected": None, "events": []}
    prov = "google" if "google" in connected else next(iter(connected))
    evs = integrations.events(u["id"], prov, 50, start or None, end or None)
    return {"logged_in": True, "connected": prov, "events": evs}


@app.post("/calendar/events")
async def create_calendar_event(request: Request):
    """Cria um evento no calendário conectado do usuário."""
    u = auth.current_user(request)
    if not u:
        return JSONResponse({"error": "não autenticado"}, status_code=401)
    connected = db.connected_providers(u["id"])
    if not connected:
        return JSONResponse({"error": "sem calendário conectado"}, status_code=400)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    start = payload.get("start"); end = payload.get("end")
    if not start or not end:
        return JSONResponse({"error": "início e fim são obrigatórios"}, status_code=400)
    prov = "google" if "google" in connected else next(iter(connected))
    try:
        ev = integrations.create_event(u["id"], prov,
                                       (payload.get("title") or "").strip(),
                                       start, end, payload.get("description"))
        return {"ok": True, "event": ev}
    except Exception as e:
        msg = str(e)
        # token somente-leitura → precisa reconectar com permissão de escrita
        needs_reconnect = msg.startswith("403") or "insufficient" in msg.lower()
        return JSONResponse({"error": msg[:200], "needs_reconnect": needs_reconnect},
                            status_code=403 if needs_reconnect else 400)


# serve o front-end (web/) na mesma origem — registrado por último para não
# sombrear as rotas acima. Abra http://127.0.0.1:8000/opendoctor-agenda.html
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
