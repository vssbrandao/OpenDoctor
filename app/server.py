"""Servidor FastAPI do assistente (spec §5.2 / §8.5).

Endpoint SSE /ask: envia as FONTES assim que a busca termina (antes do LLM),
depois faz o streaming do texto da resposta. Recusa (insufficient_evidence) é
decidida antes do LLM pelo limiar da busca.

Rodar:  uvicorn app.server:app --reload --port 8000
"""
import os
import re
import json
import time
import hashlib
import datetime
import threading
import collections

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import search, synthesize, llm, validate, db, config, ingest, integrations, auth, tools

app = FastAPI(title="OpenDoctor Assistant")
WEB_DIR = os.path.join(config.ROOT, "web")

# Abaixo deste cosseno, a evidência local é fraca → consulta o PubMed ao vivo
# antes de responder (em vez de recusar). Acima, usa só o corpus (mais rápido).
# calibrado com a pergunta em INGLÊS (cosseno ~0,1 maior que em PT): temas bem
# cobertos pelo corpus ficam em 0,69–0,79; abaixo disso, busca no PubMed.
FETCH_SIM = 0.68

# nunca usar artigos retratados
_NOT_RETRACTED = " NOT retracted publication[ptyp] NOT retraction of publication[ptyp]"
# filtro p/ priorizar artigos que RESUMEM conduta (revisões/diretrizes/metanálises)
_EVID_FILTER = (" AND (review[ptyp] OR systematic review[ptyp] OR "
                "meta-analysis[ptyp] OR practice guideline[ptyp])" + _NOT_RETRACTED)


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


def _log(*a):
    print("[ask]", *a, flush=True)


# ===== planejamento: 1 chamada barata decide escopo, pergunta autônoma e termos =====
_PLAN_SYS = (
    "Você prepara a busca de um assistente clínico para MÉDICOS. Responda APENAS um JSON: "
    '{"medical": true|false, "standalone": "...", "question_en": "...", "terms_en": "..."}. '
    "medical: true para QUALQUER tema de saúde, medicina, farmacologia, fisiologia, exames, "
    "condutas, epidemiologia, nutrição clínica ou gestão clínica; false só para temas "
    "claramente alheios (culinária, esporte, política, programação, entretenimento). "
    "Na dúvida, true. "
    "standalone: a pergunta reescrita em português de forma autônoma, incorporando o "
    "contexto da conversa SE for um follow-up (ex.: 'e na gestante?' → pergunta completa); "
    "se a pergunta já for autônoma ou mudar de assunto, repita-a sem misturar o tema anterior. "
    "question_en: a pergunta 'standalone' traduzida para o INGLÊS (o corpus é em inglês). "
    "terms_en: consulta CURTA em INGLÊS para o PubMed — 2 a 4 termos específicos (a "
    "condição + a intervenção/tema central), sem palavras genéricas como management, "
    "treatment, therapy, clinical, patients; sem vírgulas, operadores ou aspas. "
    "Ex.: 'Wilson disease chelation zinc', 'cystitis pregnancy antibiotics'."
)


def _short_terms(terms, n):
    """Primeiros n termos significativos (p/ alargar a busca quando volta vazia)."""
    words = [w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", terms or "")
             if w.lower() not in search.GENERIC_TERMS]
    return " ".join(words[:n])


def _plan(query, history):
    """Devolve {medical, standalone, terms_en}. Em falha, assume médico (não bloqueia)."""
    ctx = ""
    if history:
        last = [m for m in history[-4:] if (m.get("content") or "").strip()]
        ctx = "\n".join(f"{m['role']}: {m['content'][:600]}" for m in last)
    user = (f"Conversa anterior:\n{ctx}\n\n" if ctx else "") + f"Pergunta atual: {query}"
    try:
        out = llm.chat([{"role": "system", "content": _PLAN_SYS},
                        {"role": "user", "content": user}],
                       temperature=0, max_tokens=160,
                       model=config.OPENAI_FAST_MODEL, json_mode=True)
        d = json.loads(out)
        med = d.get("medical")
        standalone = str(d.get("standalone") or query).strip()[:600] or query
        terms = _short_terms(str(d.get("terms_en") or ""), 5) or _short_terms(standalone, 5) or standalone
        q_en = str(d.get("question_en") or "").strip()[:600] or terms
        return {"medical": True if med is None else bool(med),
                "standalone": standalone, "question_en": q_en, "terms_en": terms}
    except Exception as e:
        _log("plan falhou:", str(e)[:150])
        return {"medical": True, "standalone": query, "question_en": query, "terms_en": query}


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
        st = search.source_type_from_pubtypes(a.get("pub_types"))
        lbl, w = search.evidence_level(a.get("title"), st)
        hits.append({
            "chunk_id": -(i + 1), "document_id": None, "section_title": section,
            "text": text, "title": a["title"], "url": a["url"], "source_type": st,
            "publication_date": datetime.date(yr, 1, 1) if yr else None,
            "evidence": lbl, "evidence_w": w,
            "score": sim, "cosine_sim": sim,
        })
    return hits


def _merge_by_doc(hits, k):
    """Junta trechos do MESMO documento num único item [n] (sem fontes duplicadas)."""
    merged, order = {}, []
    for h in hits:
        key = (h.get("url") or "") or (h.get("title") or "")
        if key in merged:
            m = merged[key]
            if len(m["text"] or "") < 3500:
                m["text"] = (m["text"] or "") + "\n…\n" + (h.get("text") or "")
            continue
        merged[key] = dict(h)
        order.append(key)
    return [merged[x] for x in order][:k]


def _safe_persist(per, vecs):
    try:
        ingest.persist(per, vecs)
    except Exception as e:
        print("[ask] persist em background falhou:", str(e)[:200], flush=True)


# ===== histórico assinado: o cliente não consegue forjar turnos do assistente =====
def _answer_sig(text):
    return auth.sign({"h": hashlib.sha256(text.encode("utf-8")).hexdigest()})


def _clean_history(raw):
    """Aceita turnos do usuário e SÓ turnos do assistente com assinatura válida."""
    out = []
    if not isinstance(raw, list):
        return out
    for m in raw[-(synthesize.HISTORY_TURNS * 2):]:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            out.append({"role": "user", "content": content.strip()[:synthesize.HISTORY_CHARS]})
        elif role == "assistant":
            p = auth.unsign(m.get("sig") or "", 60 * 60 * 24)
            if p and p.get("h") == hashlib.sha256(content.encode("utf-8")).hexdigest():
                out.append({"role": "assistant", "content": content[:synthesize.HISTORY_CHARS]})
    return out[-synthesize.HISTORY_TURNS:]


# ===== limite de uso por IP (sem login por enquanto) =====
RATE_LIMITS = {"ask": (20, 600), "followups": (40, 600)}   # (pedidos, janela em s)
MAX_QUERY_CHARS = 2000
_RL = {}
_RL_LOCK = threading.Lock()


def _client_ip(request):
    h = request.headers
    ip = h.get("cf-connecting-ip") or (h.get("x-forwarded-for") or "").split(",")[0].strip()
    return ip or (request.client.host if request.client else "?")


def _rate_limited(request, bucket):
    n, win = RATE_LIMITS[bucket]
    now = time.time()
    key = (bucket, _client_ip(request))
    with _RL_LOCK:
        q = _RL.setdefault(key, collections.deque())
        while q and now - q[0] > win:
            q.popleft()
        if len(q) >= n:
            return True
        q.append(now)
        if len(_RL) > 5000:   # limpeza de IPs inativos
            for kk in [kk for kk, dq in _RL.items() if not dq or now - dq[-1] > win]:
                _RL.pop(kk, None)
    return False


def _too_many():
    return JSONResponse({"error": "Muitas perguntas em pouco tempo. Aguarde alguns minutos."},
                        status_code=429)


def _ask_stream(query, k, history=None):
    history = history or []
    _log("start len=", len(query), "hist=", len(history))

    # 0) planejamento: escopo + pergunta autônoma + termos em inglês
    plan = _plan(query, history)
    _log("plan medical=", plan["medical"], "terms=", plan["terms_en"][:100])
    if not plan["medical"]:
        # fora de escopo: não busca, não grava no corpus e não chama o modelo grande
        yield _sse("insufficient", {"text": synthesize.OUT_OF_SCOPE})
        yield _sse("done", {"insufficient": True, "out_of_scope": True})
        return
    sq, terms = plan["standalone"], plan["terms_en"]
    q_en = plan.get("question_en") or sq   # busca vetorial em INGLÊS (mesmo idioma do corpus)
    pool_k = k * 2   # busca mais trechos; depois agrupa por documento

    # 1) busca local (vetorial com a pergunta em PT, full-text com termos em inglês)
    try:
        res = search.search(q_en, k=pool_k, fts_query=terms)
    except Exception as e:
        _log("search falhou:", str(e)[:200])
        yield _sse("failed", {"message": "Falha ao consultar o servidor. Tente novamente."})
        yield _sse("done", {"insufficient": True})
        return
    _log("searched best_sim=", round(res["best_sim"], 3), "hits=", len(res.get("hits") or []))
    yield _sse("status", {"stage": "searched", "best_sim": round(res["best_sim"], 3)})

    # 2) evidência local fraca → PubMed ao vivo. Só o resultado FILTRADO por
    #    evidência (revisões/diretrizes/metanálises) é gravado no corpus.
    if res["best_sim"] < FETCH_SIM or not res["hits"]:
        yield _sse("status", {"stage": "fetching"})
        per, vecs, cacheable = [], [], False
        try:
            # 1º termos completos c/ filtro de evidência; se vazio, alarga para os
            # 2 termos centrais; só a busca SEM filtro de evidência não é cacheada
            short = _short_terms(terms, 2)
            per, vecs = ingest.fetch_and_embed(terms + _EVID_FILTER, 6)
            _log("fetch1 artigos=", len(per))
            if not per and short and short != terms:
                per, vecs = ingest.fetch_and_embed(short + _EVID_FILTER, 6)
                _log("fetch1b (alargada) artigos=", len(per))
            cacheable = bool(per)
            if not per:
                per, vecs = ingest.fetch_and_embed((short or terms) + _NOT_RETRACTED, 6)
                _log("fetch2 (não cacheado) artigos=", len(per))
        except Exception as e:
            _log("fetch on-demand falhou:", str(e)[:200])
        if per:
            fresh = _rank_fresh(res.get("qvec"), per, vecs, pool_k)
            if cacheable:
                threading.Thread(target=_safe_persist, args=(per, vecs), daemon=True).start()
            best = max((h["score"] for h in fresh), default=0.0)
            res = {"insufficient": best < search.SIM_THRESHOLD, "best_sim": best,
                   "hits": fresh, "qvec": res.get("qvec")}
        yield _sse("status", {"stage": "refetched", "best_sim": round(res["best_sim"], 3)})

    # NÃO recusamos pergunta clínica por falta de evidência: o modelo usa os
    # trechos quando há e complementa com conhecimento consolidado, sinalizado.
    # corte de relevância: trecho com cosseno abaixo do mínimo não vai ao modelo
    # (nem aparece como fonte). Sem trecho relevante, o modelo responde com
    # conhecimento consolidado e sem citar.
    relevant = [h for h in (res.get("hits") or [])
                if (h.get("cosine_sim") or 0) >= search.REL_FLOOR]
    if len(relevant) < len(res.get("hits") or []):
        _log("descartados por relevância:", len(res.get("hits") or []) - len(relevant))
    hits = _merge_by_doc(relevant, k)

    # cálculos determinísticos (ex.: eGFR) — o código calcula, o modelo explica
    try:
        extra = tools.renal_note(sq)
    except Exception as e:
        _log("tools falhou:", str(e)[:150])
        extra = None

    messages, sources = synthesize.build(query, hits, history, extra)
    yield _sse("sources", {"sources": sources})

    allowed_ns = set(range(1, len(hits) + 1))
    text_by_n = {i + 1: (h.get("text") or "") for i, h in enumerate(hits)}
    # números que o próprio médico informou / o sistema calculou também valem
    own_text = " ".join([query, extra or ""] +
                        [m["content"] for m in history if m.get("role") == "user"])

    # 3) streaming validado por frase
    buf = validate.SentenceBuffer()
    emitted, cited = [], set()
    st = {"first": False, "sentinel": False, "skipped": 0, "ungrounded": 0, "uncited": 0}

    def _handle(sentence):
        """Valida/ajusta a frase; devolve (evento_sse ou None, parar?)."""
        if not st["first"]:
            st["first"] = True
            if sentence.upper().startswith(synthesize.SENTINEL):
                st["sentinel"] = True
                return None, True
        ok, _reason = validate.validate_sentence(sentence, allowed_ns, text_by_n)
        if not ok:
            st["skipped"] += 1
            return None, False
        sentence, removed = validate.ground_citations(sentence, text_by_n, own_text)
        if removed:
            st["uncited"] += len(removed)
        if validate.is_ungrounded_claim(sentence):
            st["ungrounded"] += 1
        cited.update(validate.citations(sentence))
        emitted.append(sentence)
        return _sse("sentence", {"text": sentence}), False

    try:
        stop = False
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
                ev, _ = _handle(tail)
                if ev:
                    yield ev
    except Exception as e:
        _log("stream falhou:", str(e)[:200])
        yield _sse("failed", {"message": "Falha ao gerar a resposta. Tente novamente."})
        yield _sse("done", {"insufficient": True})
        return

    if not emitted:
        msg = synthesize.OUT_OF_SCOPE if st["sentinel"] else synthesize.EMPTY_ANSWER
        yield _sse("insufficient", {"text": msg})
        yield _sse("done", {"insufficient": True})
        return
    if st["uncited"]:
        _log("citações sem respaldo removidas:", st["uncited"])
    yield _sse("done", {"insufficient": False, "cited": sorted(cited),
                        "skipped": st["skipped"], "ungrounded": st["ungrounded"],
                        "citations_removed": st["uncited"],
                        "sig": _answer_sig("".join(emitted))})


@app.post("/ask")
async def ask_post(request: Request):
    """Body: {query, k?, history?[{role,content,sig?}]} → SSE."""
    if _rate_limited(request, "ask"):
        return _too_many()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    query = str(body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query vazia"}, status_code=400)
    if len(query) > MAX_QUERY_CHARS:
        return JSONResponse({"error": "pergunta muito longa"}, status_code=400)
    try:
        k = max(1, min(int(body.get("k") or 6), 8))
    except (TypeError, ValueError):
        k = 6
    history = _clean_history(body.get("history"))
    return StreamingResponse(_ask_stream(query, k, history),
                             media_type="text/event-stream")


@app.post("/followups")
async def followups(request: Request):
    """Sugere 3 perguntas de acompanhamento curtas a partir da última resposta."""
    if _rate_limited(request, "followups"):
        return _too_many()
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    query = str(body.get("query") or "").strip()[:MAX_QUERY_CHARS]
    answer = str(body.get("answer") or "").strip()
    if not answer:
        return {"suggestions": []}
    try:
        out = llm.chat([
            {"role": "system", "content": "Você gera perguntas de acompanhamento para um "
             "MÉDICO, a partir de uma resposta clínica. Devolva EXATAMENTE 3 perguntas curtas "
             "(máx. 8 palavras cada), clínicas e úteis para aprofundar (ex.: subgrupo, dose, "
             "alternativa, monitorização). Uma por linha, sem numeração, sem aspas."},
            {"role": "user", "content": f"Pergunta: {query}\n\nResposta:\n{answer[:3000]}"}],
            temperature=0.4, max_tokens=80, model=config.OPENAI_FAST_MODEL).strip()
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
