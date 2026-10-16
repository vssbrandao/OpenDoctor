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
import base64
import hashlib
import urllib.parse
import posixpath
import datetime
import threading
import collections
import secrets
import concurrent.futures
import mimetypes
import asyncio
import struct

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import search, synthesize, llm, validate, db, config, ingest, integrations, auth, tools, cid10, mailer, exemplo
from . import scribe, stt

mimetypes.add_type("text/javascript", ".mjs")   # pdf.js (web/vendor) é módulo: o navegador exige esse tipo

app = FastAPI(title="OpenDoctor Assistant")
WEB_DIR = os.path.join(config.ROOT, "web")

# Abaixo deste cosseno, a evidência local é fraca → consulta o PubMed ao vivo
# antes de responder (em vez de recusar). Acima, usa só o corpus (mais rápido).
# calibrado com a pergunta em INGLÊS (cosseno ~0,1 maior que em PT): temas bem
# cobertos pelo corpus ficam em 0,69–0,79; abaixo disso, busca no PubMed.
FETCH_SIM = 0.68
# entre FETCH_BLOCK_SIM e FETCH_SIM a evidência local já é razoável: responde na
# hora e busca no PubMed em 2º plano (enriquece o corpus p/ as próximas perguntas).
# Abaixo de FETCH_BLOCK_SIM, espera a busca ao vivo antes de responder.
FETCH_BLOCK_SIM = 0.60
# busca ao vivo: artigos dos últimos ~12 anos, ordenados por relevância (Best Match)
FETCH_MINDATE = 2014
FETCH_RETMAX = 10

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


def _cleanup_loop():
    """Limpeza diária dos registros vencidos (db.RETENTION). A primeira roda logo após subir."""
    while True:
        try:
            print("[limpeza]", db.cleanup_old_records(), flush=True)
        except Exception as e:
            print("[limpeza] falhou:", str(e)[:200], flush=True)
        time.sleep(24 * 60 * 60)


@app.on_event("startup")
def _start_cleanup():
    if config.DATABASE_URL:
        threading.Thread(target=_cleanup_loop, name="limpeza", daemon=True).start()


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# respostas com dados de pacientes/agenda: nunca guardar em cache (LGPD, dado de saúde)
_NO_STORE = ("/patients", "/prontuario/", "/calendar/")


def _inline_script_hashes():
    """Hash de cada <script> escrito dentro das páginas: o navegador só roda esses blocos exatos, e um
    script injetado (XSS) é recusado. Calculado ao subir, a partir dos próprios arquivos — editar um
    script não exige mexer aqui. (Por isso nada de onclick= no HTML: use addEventListener.)"""
    out = set()
    if os.path.isdir(WEB_DIR):
        for f in sorted(os.listdir(WEB_DIR)):
            if f.endswith(".html"):
                with open(os.path.join(WEB_DIR, f), encoding="utf-8") as fh:
                    for body in re.findall(r"<script>(.*?)</script>", fh.read(), re.S):
                        out.add("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
    return sorted(out)


# cabeçalhos de segurança em todas as respostas
_CSP = "; ".join((
    "default-src 'self'",
    " ".join(["script-src 'self' https://cdn.jsdelivr.net"] + _inline_script_hashes()),   # jsdelivr: mermaid
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
))
_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",          # só HTTPS por 1 ano
    "Content-Security-Policy": _CSP,                           # de onde a página pode carregar código
    "X-Frame-Options": "DENY",                                 # ninguém embute o app num iframe (clickjacking)
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",       # links externos não recebem o endereço completo
    # microfone só para o próprio site (gravação da consulta, com autorização do paciente); o resto, para ninguém
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


# ===== quem acessa o quê: FECHADO POR PADRÃO =====
# Todo endereço exige login, menos os listados aqui. Rota ou página nova nasce privada; para abrir uma,
# inclua aqui com o motivo — o teste tests/test_security.py exige que a lista bata com a dele, então
# abrir algo é sempre uma decisão consciente (veja CLAUDE.md).
PUBLIC_PATHS = {
    "/": "redireciona para a agenda (logado) ou para o login",
    "/health": "verificação de saúde do Render",
    "/me": "diz se há sessão (a tela de login e o aviso de sessão expirada perguntam)",
    "/opendoctor-login.html": "tela de entrar / criar conta",
    "/privacy": "Política de Privacidade (exigida pelo Google)", "/privacy.html": "idem",
    "/terms": "Termos de Serviço (exigidos pelo Google)", "/terms.html": "idem",
}
PUBLIC_PREFIXES = {
    "/auth/": "entrar, criar conta, nova senha, sair e o retorno do Google/Microsoft",
    "/assets/": "fontes, ícones e imagens da tela de login e do logo dos e-mails",
}


def _norm(path):
    # "/" + lstrip: o normpath mantém "//" no começo (regra POSIX)
    return posixpath.normpath("/" + path.lstrip("/"))


def is_public(path):
    """O caminho é normalizado (//, /./, /../, maiúsculas): não há outro jeito de pedir o mesmo endereço."""
    p = _norm(path).lower()
    return p in PUBLIC_PATHS or p.startswith(tuple(PUBLIC_PREFIXES))


@app.middleware("http")
async def _no_cache_html(request: Request, call_next):
    """Exige login em tudo que não é público; impede o navegador de servir HTML velho do cache após
    um deploy, e de guardar respostas com dados de pacientes. Também põe os cabeçalhos de segurança."""
    path = request.url.path
    private = not is_public(path)
    page = _norm(path).lower().endswith(".html")
    if private and not await run_in_threadpool(auth.current_user, request):
        navegando = request.method == "GET" and "text/html" in (request.headers.get("accept") or "")
        if page or navegando:   # página ou link clicado: vai para o login e volta depois
            resp = RedirectResponse("/opendoctor-login.html?next=" + urllib.parse.quote(_norm(path), safe=""),
                                    status_code=302)
        else:
            resp = JSONResponse({"error": "não autenticado"}, status_code=401)
    elif path.lower().endswith(".md"):
        resp = JSONResponse({"error": "não encontrado"}, status_code=404)   # notas internas da pasta web
    else:
        resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    if private and page:
        # páginas com dados: nada em cache (nem para o botão Voltar depois de sair)
        resp.headers["Cache-Control"] = "no-store"
    elif path.endswith(".html") or path == "/":
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    elif path.startswith(_NO_STORE):
        resp.headers["Cache-Control"] = "no-store"
    elif path.startswith("/assets/icons/"):
        # ícones mudam com o design: o navegador sempre confere (304 se igual), nunca usa cópia velha
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/")
def root(request: Request):
    # raiz do site: agenda (home do app) para quem já entrou; senão, a tela de login
    return RedirectResponse("/opendoctor-agenda.html" if auth.current_user(request) else "/opendoctor-login.html")


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


def _doc_key(h):
    """Identidade do documento: título normalizado (a mesma diretriz sai em várias
    revistas com PMIDs/DOIs diferentes); URL só se não houver título."""
    def norm(x):
        return re.sub(r"[^a-z0-9]+", " ", x).strip()
    title = (h.get("title") or "").lower()
    main = norm(title.split(":")[0])
    # título principal (antes dos ":") só quando é específico o bastante p/ não
    # fundir artigos distintos de título genérico ("Heart failure: a review")
    if len(main.split()) >= 6:
        return main[:90]
    return norm(title)[:90] or (h.get("url") or "")


def _merge_by_doc(hits, k):
    """Junta trechos do MESMO documento num único item [n] (sem fontes duplicadas)."""
    merged, order = {}, []
    for h in hits:
        key = _doc_key(h)
        if key in merged:
            m = merged[key]
            if len(m["text"] or "") < 3500:
                m["text"] = (m["text"] or "") + "\n…\n" + (h.get("text") or "")
            continue
        merged[key] = dict(h)
        order.append(key)
    return [merged[x] for x in order][:k]


REC_MAX = 5            # artigos em "Leitura recomendada"
REC_MIN_COS = 0.52     # mais exigente que o corte de relevância (alta precisão)


def _recommend(docs):
    """Melhores artigos para LER: relevância + força da evidência + recência.
    docs: documentos relevantes já agrupados (_merge_by_doc)."""
    this_year = datetime.date.today().year
    scored = []
    for h in docs:
        cos = h.get("cosine_sim") or 0
        if cos < REC_MIN_COS:
            continue
        d = h.get("publication_date")
        yr = d.year if d is not None and hasattr(d, "year") else None
        score = cos + 0.02 * (h.get("evidence_w") or 1) + (0.01 if yr and yr >= this_year - 5 else 0)
        scored.append((score, h, yr))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"title": h.get("title"), "url": h.get("url"), "year": yr,
             "evidence": h.get("evidence")} for _, h, yr in scored[:REC_MAX]]


def _bg_enrich(terms):
    """Busca evidência forte no PubMed e grava no corpus, sem bloquear a resposta."""
    try:
        per, vecs = ingest.fetch_and_embed(terms + _EVID_FILTER, FETCH_RETMAX, FETCH_MINDATE)
        if per:
            ingest.persist(per, vecs)
            _log("enriquecimento em 2º plano: +", len(per), "artigos")
    except Exception as e:
        _log("enriquecimento falhou:", str(e)[:150])


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


# ===== limite de uso por IP (além do login) =====
RATE_LIMITS = {"ask": (20, 600), "followups": (40, 600),   # (pedidos, janela em s)
               "login_check": (30, 600), "login_pw": (20, 600), "login_code": (10, 600), "login_verify": (30, 600),
               "transcribe": (240, 600), "scribe": (30, 600)}      # trecho a cada 15–30 s; depois de cair a internet, vários de uma vez
MAX_QUERY_CHARS = 2000
_RL = {}
_RL_LOCK = threading.Lock()


def _client_ip(request):
    """IP do visitante. O site fica atrás do Cloudflare, que põe o IP real em CF-Connecting-IP e recusa
    quem tenta forjar esse cabeçalho. O X-Forwarded-For não serve: o primeiro item é o que o próprio
    visitante mandar (trocar a cada pedido escaparia do limite) — dele só vale o último, do proxy."""
    h = request.headers
    ip = (h.get("cf-connecting-ip") or "").strip()
    if not ip:
        hops = [x.strip() for x in (h.get("x-forwarded-for") or "").split(",") if x.strip()]
        ip = hops[-1] if hops else ""
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
    if res["hits"] and FETCH_BLOCK_SIM <= res["best_sim"] < FETCH_SIM:
        _log("evidência local razoável; enriquecendo o corpus em 2º plano")
        threading.Thread(target=_bg_enrich, args=(terms,), daemon=True).start()
    elif res["best_sim"] < FETCH_BLOCK_SIM or not res["hits"]:
        yield _sse("status", {"stage": "fetching"})
        per, vecs, cacheable = [], [], False
        try:
            # 1º termos completos c/ filtro de evidência; se vazio, alarga para os
            # 2 termos centrais; só a busca SEM filtro de evidência não é cacheada
            short = _short_terms(terms, 2)
            per, vecs = ingest.fetch_and_embed(terms + _EVID_FILTER, FETCH_RETMAX, FETCH_MINDATE)
            _log("fetch1 artigos=", len(per))
            if not per and short and short != terms:
                per, vecs = ingest.fetch_and_embed(short + _EVID_FILTER, FETCH_RETMAX, FETCH_MINDATE)
                _log("fetch1b (alargada) artigos=", len(per))
            cacheable = bool(per)
            if not per:
                per, vecs = ingest.fetch_and_embed((short or terms) + _NOT_RETRACTED, FETCH_RETMAX, FETCH_MINDATE)
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
    docs = _merge_by_doc(relevant, 50)      # todos os documentos relevantes
    hits = docs[:k]                          # os k melhores vão ao modelo
    recommended = _recommend(docs)

    # cálculos determinísticos (ex.: eGFR) — o código calcula, o modelo explica
    try:
        extra = tools.renal_note(sq)
    except Exception as e:
        _log("tools falhou:", str(e)[:150])
        extra = None

    messages, sources = synthesize.build(query, hits, history, extra)
    yield _sse("sources", {"sources": sources, "recommended": recommended})

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
    """Body: {query, k?, history?[{role,content,sig?}]} → SSE. Só com login."""
    u, err = _auth_or_401(request)
    if err:
        return err
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
    """Sugere 3 perguntas de acompanhamento curtas a partir da última resposta. Só com login."""
    u, err = _auth_or_401(request)
    if err:
        return err
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
def google_login(next: str = ""):
    if not integrations.configured("google"):
        return JSONResponse({"error": "google não configurado"}, status_code=400)
    url, nonce = auth.google_login_start("", next)
    resp = RedirectResponse(url)
    auth.set_oauth_cookie(resp, nonce)
    return resp


def _login_page(erro, nxt=""):
    """Volta para a tela de login com o motivo (e a página de origem, se houver)."""
    q = {"erro": erro}
    nxt = auth.safe_next(nxt)
    if nxt != auth.HOME:
        q["next"] = nxt
    return "/opendoctor-login.html?" + urllib.parse.urlencode(q)


_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,63}")


@app.post("/auth/google/start")
async def google_start(request: Request):
    """Tela de login: recebe o e-mail no corpo (fora da URL e dos logs) e devolve a URL do Google
    com `login_hint`, para abrir direto nessa conta."""
    if not integrations.configured("google"):
        return JSONResponse({"error": "google não configurado"}, status_code=400)
    try:
        body = await request.json()
        email, nxt = str(body.get("email") or "").strip(), str(body.get("next") or "")
    except Exception:
        email, nxt = "", ""
    if email and not _EMAIL.fullmatch(email):
        return JSONResponse({"error": "e-mail inválido"}, status_code=400)
    url, nonce = auth.google_login_start(email, nxt)
    resp = JSONResponse({"url": url})
    auth.set_oauth_cookie(resp, nonce)
    return resp


# ----- login por e-mail e senha -----
# Tela inicial: e-mail → (tem conta com senha) senha | (conta só Google) Google | (sem conta) cadastro.
# O cadastro e a redefinição de senha exigem um código de 6 dígitos enviado ao e-mail: ninguém cria
# conta (nem troca a senha) de um e-mail que não é seu.

async def _body(request):
    """Corpo JSON. Exige Content-Type application/json: um formulário de outro site só consegue mandar
    text/plain/form — sem isso, ele poderia logar a vítima na conta do atacante (login CSRF)."""
    if not (request.headers.get("content-type") or "").lower().startswith("application/json"):
        return {}
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _err(code, status=400, **extra):
    return JSONResponse(dict({"error": code}, **extra), status_code=status)


def _email_of(b):
    email = str(b.get("email") or "").strip().lower()
    return email if _EMAIL.fullmatch(email) else None


_AUDIT = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _audit(request, user_id, event, method, dev=None):
    """Registra o acesso (login_events) em segundo plano, sem atrasar o login. Numa entrada por um
    aparelho novo, avisa o dono da conta por e-mail. Falhas só vão para o log."""
    ip, ua = _client_ip(request), request.headers.get("user-agent") or ""
    dev = dev or auth.device_id(request)

    def run():
        try:
            novo = db.record_login(user_id, event, method, ip, ua, auth.device_hash(dev))
            if novo and method in ("senha", "google") and mailer.configured():
                u = db.get_user(user_id)
                if u:
                    mailer.send_new_device(u["email"], u.get("name") or "", auth.device_label(ua), method)
        except Exception as e:
            print("[login] registro de acesso falhou:", str(e)[:200], flush=True)
    _AUDIT.submit(run)


def _device(request, resp):
    """Aparelho deste navegador: o cookie que já tinha ou um novo (renovado a cada entrada)."""
    dev = auth.device_id(request) or secrets.token_urlsafe(24)
    auth.set_device(resp, dev)
    return dev


def _logged(request, user, nxt, method, welcome=False):
    """Resposta de login concluído: cookie de sessão + para onde ir. Registra a entrada."""
    dest = auth.safe_next(nxt)
    resp = JSONResponse({"ok": True, "redirect": auth.with_welcome(dest) if welcome else dest})
    auth.set_session(resp, user["id"], user.get("sv", 0))
    _audit(request, user["id"], "entrou", method, _device(request, resp))
    return resp


def _send_code(email, purpose, name=""):
    """Cria e envia um código. Devolve (resposta de erro ou None, segundos até poder reenviar —
    negativo quando não enviou agora porque o código de menos de 30s atrás continua valendo)."""
    code = auth.new_code()
    try:
        status, wait = db.new_login_code(email, auth.code_hash(email, code, purpose))
    except Exception as e:
        print("[login] código falhou:", str(e)[:200], flush=True)
        return _err("erro", 500), 0
    if status == "aguarde":
        return None, -wait                         # negativo = não enviou agora (o anterior ainda vale)
    if status == "limite":
        return _err("limite", 429), 0
    try:
        mailer.send_code(email, code, purpose, name)
    except Exception as e:
        print("[login] envio falhou:", str(e)[:200], flush=True)
        try:
            db.discard_login_code(email)          # sem e-mail enviado, não conta reenvio nem limite
        except Exception:
            pass
        return _err("envio_falhou", 502), 0
    return None, db.CODE_RESEND_S


def _check_code(email, code, purpose):
    """None se o código confere; senão a resposta de erro (incorreto / expirado / tentativas)."""
    code = re.sub(r"\D", "", str(code or ""))
    if len(code) != 6:
        return _err("codigo_invalido")
    status, left = db.check_login_code(email, auth.code_hash(email, code, purpose))
    if status == "ok":
        return None
    return _err({"errado": "codigo_incorreto", "expirado": "codigo_expirado", "bloqueado": "muitas_tentativas"}[status],
                429 if status == "bloqueado" else 400, left=left)


@app.post("/auth/email/check")
async def email_check(request: Request):
    email = _email_of(await _body(request))
    if not email:
        return _err("email_invalido")
    if _rate_limited(request, "login_check"):
        return _err("limite_ip", 429)
    try:
        acc = db.account(email)
    except Exception as e:
        print("[login] check falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    return {"exists": acc is not None, "password": bool(acc and acc["password"]), "email_ok": mailer.configured()}


@app.post("/auth/password/login")
async def password_login(request: Request):
    b = await _body(request)
    email, pw = _email_of(b), b.get("password")
    if not email:
        return _err("email_invalido")
    if not isinstance(pw, str) or not pw:
        return _err("senha_vazia")
    if _rate_limited(request, "login_pw"):
        return _err("limite_ip", 429)
    try:
        info = db.password_login_info(email)
        if not info:
            return _err("sem_conta", 404)
        if not info["hash"]:
            return _err("sem_senha")                        # conta criada pelo Google
        if info["locked_s"] > 0:
            _audit(request, info["id"], "bloqueado", "senha")
            return _err("bloqueado", 429, minutes=-(-info["locked_s"] // 60))
        if not auth.check_password(pw, info["hash"]):
            left, locked = db.login_failed(info["id"])
            _audit(request, info["id"], "bloqueado" if locked else "senha_incorreta", "senha")
            if locked:
                return _err("bloqueado", 429, minutes=locked // 60)
            return _err("senha_incorreta", 401, left=left)
        db.login_succeeded(info["id"])
    except Exception as e:
        print("[login] senha falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    return _logged(request, {"id": info["id"], "sv": info["sv"]}, b.get("next"), "senha")


def _valid_name(raw):
    name = " ".join(str(raw or "").split())
    return name if 2 <= len(name) <= 120 else None


@app.post("/auth/signup/start")
async def signup_start(request: Request):
    """Dados do cadastro → envia o código de confirmação. A conta só é criada no /verify."""
    b = await _body(request)
    email, name, pw = _email_of(b), _valid_name(b.get("name")), b.get("password")
    if not email:
        return _err("email_invalido")
    if not name:
        return _err("nome")
    if auth.password_problems(pw):
        return _err("senha_fraca", rules=auth.password_problems(pw))
    if not mailer.configured():
        return _err("email_indisponivel", 503)
    if _rate_limited(request, "login_code"):
        return _err("limite_ip", 429)
    try:
        if db.account(email) is not None:
            return _err("conta_existe", 409)
    except Exception as e:
        print("[login] cadastro falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    fail, wait = _send_code(email, "signup", name)
    if fail:
        return fail
    # os dados esperam a confirmação num tíquete assinado (30 min), não no banco
    ticket = auth.sign({"k": "signup", "email": email, "name": name, "ph": auth.hash_password(pw)})
    return {"ok": True, "ticket": ticket, "resend_in": abs(wait), "sent": wait > 0}


def _signup_ticket(b):
    t = auth.unsign(str(b.get("ticket") or ""), 30 * 60)
    return t if t and t.get("k") == "signup" and t.get("email") and t.get("ph") else None


@app.post("/auth/signup/resend")
async def signup_resend(request: Request):
    t = _signup_ticket(await _body(request))
    if not t:
        return _err("sessao_expirada")
    if _rate_limited(request, "login_code"):
        return _err("limite_ip", 429)
    fail, wait = _send_code(t["email"], "signup", t.get("name", ""))
    return fail or {"ok": True, "resend_in": abs(wait), "sent": wait > 0}


@app.post("/auth/signup/verify")
async def signup_verify(request: Request):
    b = await _body(request)
    t = _signup_ticket(b)
    if not t:
        return _err("sessao_expirada")
    if _rate_limited(request, "login_verify"):
        return _err("limite_ip", 429)
    try:
        bad = _check_code(t["email"], b.get("code"), "signup")
        if bad:
            return bad
        novo = db.user_by_email(t["email"]) is None
        user = db.create_email_user(t["email"], t.get("name"), t["ph"])
    except Exception as e:
        print("[login] confirmação falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    if novo:
        exemplo.seed_safe(user["id"])                   # conta nova: paciente de exemplo (fictícia)
    return _logged(request, user, b.get("next"), "cadastro", welcome=True)


@app.post("/auth/password/forgot")
async def password_forgot(request: Request):
    """Envia o código para criar uma nova senha (também serve para conta só Google criar uma senha)."""
    email = _email_of(await _body(request))
    if not email:
        return _err("email_invalido")
    if not mailer.configured():
        return _err("email_indisponivel", 503)
    if _rate_limited(request, "login_code"):
        return _err("limite_ip", 429)
    try:
        acc = db.user_by_email(email)
    except Exception as e:
        print("[login] esqueci falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    wait = db.CODE_RESEND_S
    if acc:
        fail, wait = _send_code(email, "reset", acc.get("name") or "")
        if fail:
            return fail
    return {"ok": True, "resend_in": abs(wait), "sent": wait > 0}


@app.post("/auth/password/reset/verify")
async def password_reset_verify(request: Request):
    """Etapa 1 da nova senha: confere o código e devolve um tíquete (15 min) para escolher a senha."""
    b = await _body(request)
    email = _email_of(b)
    if not email:
        return _err("email_invalido")
    if _rate_limited(request, "login_verify"):
        return _err("limite_ip", 429)
    try:
        bad = _check_code(email, b.get("code"), "reset")
        if bad:
            return bad
        acc = db.user_by_email(email)
    except Exception as e:
        print("[login] código de redefinição falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    if not acc:
        return _err("codigo_expirado")
    # a versão da sessão vai no tíquete: depois que a senha muda, ele não serve mais (uso único)
    return {"ok": True, "ticket": auth.sign({"k": "reset", "uid": acc["id"], "sv": acc.get("sv", 0)})}


@app.post("/auth/password/reset")
async def password_reset(request: Request):
    """Etapa 2: nova senha com o tíquete da etapa 1."""
    b = await _body(request)
    pw = b.get("password")
    t = auth.unsign(str(b.get("ticket") or ""), 15 * 60)
    if not t or t.get("k") != "reset" or not t.get("uid"):
        return _err("sessao_expirada")
    if auth.password_problems(pw):
        return _err("senha_fraca", rules=auth.password_problems(pw))
    try:
        cur = db.get_user(t["uid"])
        if not cur or int(cur.get("sv") or 0) != int(t.get("sv") or 0):
            return _err("sessao_expirada")                   # tíquete já usado (a senha já mudou)
        user = db.set_password(t["uid"], auth.hash_password(pw))
    except Exception as e:
        print("[login] redefinição falhou:", str(e)[:200], flush=True)
        return _err("erro", 500)
    try:
        mailer.send_password_changed(user["email"], user.get("name") or "")   # aviso; falha não desfaz a troca
    except Exception as e:
        print("[login] aviso de senha alterada falhou:", str(e)[:200], flush=True)
    return _logged(request, user, b.get("next"), "nova_senha")


@app.get("/auth/logout")
def logout():
    resp = RedirectResponse("/opendoctor-login.html")
    auth.clear_session(resp)
    # apaga o que o app guardou neste navegador (rascunhos do prontuário, conversas) — LGPD
    resp.headers["Clear-Site-Data"] = '"storage"'
    return resp


def scribe_on(user):
    """A conta tem a gravação real da consulta? (SCRIBE_OFF desliga para todos na hora.)"""
    if not user or config.SCRIBE_OFF:
        return False
    return config.SCRIBE_ALL or str(user.get("email") or "").lower() in config.SCRIBE_EMAILS


@app.get("/me")
def me(request: Request):
    u = auth.current_user(request)
    on = scribe_on(u)
    if u:
        u = {k: v for k, v in u.items() if k != "sv"}
    return {"logged_in": bool(u), "user": u, "scribe": on}


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
        return RedirectResponse("/opendoctor-login.html?next=" + urllib.parse.quote("/opendoctor-integracao.html", safe=""))
    state = auth.sign({"k": "cal", "prov": provider, "uid": u["id"]})
    return RedirectResponse(integrations.connect_url(provider, state))


@app.get("/auth/{provider}/callback")
def auth_callback(provider: str, request: Request, code: str = "", state: str = "", error: str = ""):
    """Callback único por provedor: distingue login x conexão de calendário pelo `state`."""
    payload = auth.unsign(state, auth.STATE_MAX_AGE) if state else None
    if error or not code or not payload:
        if (payload or {}).get("k") == "cal":
            return RedirectResponse("/opendoctor-integracao.html?erro=" + urllib.parse.quote(error or "sem_code"))
        # cancelou na tela do Google → aviso simples; o resto é erro de conexão
        return RedirectResponse(_login_page("cancelado" if error == "access_denied" else "conexao",
                                            (payload or {}).get("nx", "")))

    # --- login do app (só Google) ---
    if payload.get("k") == "login":
        if not auth.login_nonce_ok(request, payload):
            # retorno que não começou neste navegador (ou começou em outra aba): não loga
            resp = RedirectResponse(_login_page("conexao", payload.get("nx", "")))
            resp.delete_cookie(auth.OAUTH_COOKIE, path="/auth/")
            return resp
        try:
            info = auth.exchange_login(code)
            novo = db.user_by_email(info["email"]) is None
            user = db.upsert_user(info["email"], info.get("name"),
                                  info.get("picture"), info.get("sub"))
            if novo:
                exemplo.seed_safe(user["id"])           # conta nova: paciente de exemplo (fictícia)
            dest = auth.safe_next(payload.get("nx"))
            resp = RedirectResponse(auth.with_welcome(dest) if novo else dest)
            auth.set_session(resp, user["id"], user.get("sv", 0))
            _audit(request, user["id"], "entrou", "google", _device(request, resp))
            resp.delete_cookie(auth.OAUTH_COOKIE, path="/auth/")
            return resp
        except Exception as e:
            print("[auth] login falhou:", str(e)[:200])
            return RedirectResponse(_login_page("conexao", payload.get("nx", "")))

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
def calendar_events(request: Request, start: str = "", end: str = "", limit: int = 50):
    """Eventos do provedor conectado do usuário (o que a agenda consome).
    `limit` maior (até 250) é usado pela busca, que filtra no navegador."""
    u = auth.current_user(request)
    if not u:
        return {"logged_in": False, "connected": None, "events": []}
    connected = db.connected_providers(u["id"])
    if not connected:
        return {"logged_in": True, "connected": None, "events": []}
    prov = "google" if "google" in connected else next(iter(connected))
    evs = integrations.events(u["id"], prov, max(1, min(limit, 250)), start or None, end or None)
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
                                       start, end, payload.get("description"),
                                       location=(payload.get("location") or "").strip() or None,
                                       all_day=bool(payload.get("all_day")),
                                       patient_id=_own_patient_id(u, payload))
        return {"ok": True, "event": ev}
    except Exception as e:
        msg = str(e)
        # token somente-leitura → precisa reconectar com permissão de escrita
        needs_reconnect = msg.startswith("403") or "insufficient" in msg.lower()
        return JSONResponse({"error": msg[:200], "needs_reconnect": needs_reconnect},
                            status_code=403 if needs_reconnect else 400)


def _own_patient_id(u, payload):
    """patient_id do payload, só se o paciente for deste médico (senão None).
    Marca o paciente como usado agora (lista de recentes)."""
    pid = payload.get("patient_id")
    if not str(pid or "").isdigit():
        return None
    p = db.get_patient(u["id"], int(pid))
    if not p:
        return None
    db.touch_patient(u["id"], p["id"])
    return p["id"]


def _cal_error(e):
    msg = str(e)
    needs_reconnect = msg.startswith("403") or "insufficient" in msg.lower()
    return JSONResponse({"error": msg[:200], "needs_reconnect": needs_reconnect},
                        status_code=403 if needs_reconnect else 400)


def _cal_user(request):
    """(usuário, provedor conectado) ou JSONResponse de erro."""
    u = auth.current_user(request)
    if not u:
        return None, JSONResponse({"error": "não autenticado"}, status_code=401)
    connected = db.connected_providers(u["id"])
    if not connected:
        return None, JSONResponse({"error": "sem calendário conectado"}, status_code=400)
    return (u, "google" if "google" in connected else next(iter(connected))), None


@app.patch("/calendar/events/{event_id}")
async def update_calendar_event(event_id: str, request: Request):
    """Edita um evento (salvo ao fechar a janela do evento)."""
    ctx, err = _cal_user(request)
    if err:
        return err
    u, prov = ctx
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    start = payload.get("start"); end = payload.get("end")
    if not start or not end:
        return JSONResponse({"error": "início e fim são obrigatórios"}, status_code=400)
    try:
        ev = integrations.update_event(u["id"], prov, event_id,
                                       (payload.get("title") or "").strip(), start, end,
                                       payload.get("description"),
                                       location=(payload.get("location") or "").strip() or None,
                                       all_day=bool(payload.get("all_day")),
                                       patient_id=_own_patient_id(u, payload))
        return {"ok": True, "event": ev}
    except Exception as e:
        return _cal_error(e)


@app.delete("/calendar/events/{event_id}")
def delete_calendar_event(event_id: str, request: Request):
    """Exclui um evento do calendário conectado."""
    ctx, err = _cal_user(request)
    if err:
        return err
    u, prov = ctx
    try:
        integrations.delete_event(u["id"], prov, event_id)
        return {"ok": True}
    except Exception as e:
        return _cal_error(e)


# --- prontuário: anotações por paciente (POST p/ não levar o nome do paciente na URL) ---
MAX_NOTE_CHARS = 50000          # evolução maior é recusada (413) — nunca cortada em silêncio
MAX_DATA_CHARS = 60000
_SEX = {"F", "M", "O"}
_VITALS = ("pa_s", "pa_d", "fc", "fr", "temp", "spo2", "peso", "altura", "glicemia")
# exames laboratoriais registrados na evolução (a TFG é calculada na tela a partir da creatinina)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_LABS = ("hba1c", "ct", "ldl", "hdl", "tg", "creat", "rac", "pot", "sod", "au", "tsh", "hb", "alt")


def _iso_or_none(v):
    """Data/hora ISO 8601 válida ou None (evita erro 500 do Postgres com texto qualquer)."""
    import datetime as _dt
    if not isinstance(v, str) or not v:
        return None
    try:
        _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v
    except ValueError:
        return None


def _date_or_none(v):
    """Data AAAA-MM-DD válida (não futura, após 1900) ou None."""
    import datetime as _dt
    if not isinstance(v, str) or not v:
        return None
    try:
        d = _dt.date.fromisoformat(v[:10])
    except ValueError:
        return None
    return v[:10] if _dt.date(1900, 1, 1) <= d <= _dt.date.today() else None


def _cpf_ok(v):
    """CPF com dígitos verificadores válidos (só números)."""
    d = "".join(c for c in str(v or "") if c.isdigit())
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        s = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (s * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _clean_text(v, limit):
    return str(v or "").replace("\r\n", "\n")[:limit]


def _note_data(v):
    """Evolução estruturada (SOAP + sinais vitais + CID-10): só campos conhecidos e tamanhos limitados."""
    if not isinstance(v, dict):
        return None
    out = {"mode": "soap" if v.get("mode") == "soap" else "free"}
    if v.get("kind") == "labs":                         # registro só de exames (botão "Adicionar exames")
        out["kind"] = "labs"
    for k in ("s", "o", "a", "p"):
        if isinstance(v.get(k), str):
            out[k] = v[k][:MAX_NOTE_CHARS]
    vit = v.get("vitals") if isinstance(v.get("vitals"), dict) else {}
    out["vitals"] = {k: str(vit[k])[:12] for k in _VITALS if vit.get(k) not in (None, "")}
    labs = v.get("labs") if isinstance(v.get("labs"), dict) else {}
    lv = labs.get("v") if isinstance(labs.get("v"), dict) else {}
    lv = {k: str(lv[k])[:12] for k in _LABS if lv.get(k) not in (None, "")}
    if lv:
        out["labs"] = {"date": _date_or_none(labs.get("date")), "v": lv}
    cid = v.get("cid") if isinstance(v.get("cid"), list) else []
    out["cid"] = [{"code": str(c.get("code") or "")[:10], "desc": str(c.get("desc") or "")[:200]}
                  for c in cid[:20] if isinstance(c, dict) and (c.get("code") or c.get("desc"))]
    if isinstance(v.get("scribe"), dict):              # evolução gerada pela gravação: rastreio, sem texto
        out["scribe"] = _scribe_rastreio(v["scribe"])
    return out if len(json.dumps(out)) <= MAX_DATA_CHARS else None


def _scribe_rastreio(sc):
    """O rastreio da evolução gerada pela gravação (data.scribe e recordings.scribe), sem texto. A ÚNICA definição dos
    campos: o servidor monta com ela ao gerar, e ela filtra o que a página manda ao salvar (a página só acrescenta
    conferidos e conf_idx — os pontos que o médico marcou)."""
    def inteiro(k, top):
        x = sc.get(k)
        return x if isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= top else 0
    pts = sc.get("pontos") if isinstance(sc.get("pontos"), dict) else {}
    return {"rec_ids": [str(x).lower() for x in (sc.get("rec_ids") or [])[:20] if _UUID.match(str(x).lower())],
            "prompt": str(sc.get("prompt") or "")[:40], "model": str(sc.get("model") or "")[:40],
            "consent_at": _iso_or_none(sc.get("consent_at")), "generated_at": _iso_or_none(sc.get("generated_at")),
            "pontos": {k: pts[k] for k in ("alto", "medio", "info") if isinstance(pts.get(k), int) and 0 <= pts[k] < 1000},
            "segundos": inteiro("segundos", 6 * 3600), "conferidos": inteiro("conferidos", 999),
            "gen_s": inteiro("gen_s", 3600),                  # do "Encerrar" à evolução pronta (critério 5)
            "conf_idx": sorted({i for i in (sc.get("conf_idx") or [])[:300] if isinstance(i, int) and not isinstance(i, bool) and 0 <= i < 1000})}


def _patient_fields(payload, partial=True):
    """Campos do cadastro vindos da tela, validados. Devolve (campos, erro)."""
    f = {}
    if "name" in payload or not partial:
        name = " ".join(str(payload.get("name") or "").split())[:200]
        if not db.patient_key(name):
            return None, "nome obrigatório"
        f["name"] = name
    if "birth_date" in payload:
        bd = payload.get("birth_date")
        if bd and not _date_or_none(bd):
            return None, "data de nascimento inválida"
        f["birth_date"] = _date_or_none(bd)
    if "sex" in payload:
        sx = payload.get("sex") or None
        if sx and sx not in _SEX:
            return None, "sexo inválido"
        f["sex"] = sx
    if "cpf" in payload:
        cpf = "".join(c for c in str(payload.get("cpf") or "") if c.isdigit())
        if cpf and not _cpf_ok(cpf):
            return None, "CPF inválido"
        f["cpf"] = cpf or None
    if "phone" in payload:
        f["phone"] = " ".join(str(payload.get("phone") or "").split())[:40] or None
    for k in ("allergies", "problems", "medications"):
        if k in payload:
            f[k] = _clean_text(payload.get(k), 5000)
    return f, None


async def _json(request):
    try:
        v = await request.json()
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _note_patient(u, payload):
    """Paciente do prontuário: pelo id do cadastro; eventos antigos (só com o nome) são
    ligados ao cadastrado com esse nome (ou cadastrados na hora). Devolve o paciente ou None."""
    pid = payload.get("patient_id")
    if str(pid or "").isdigit():
        return db.get_patient(u["id"], int(pid))
    name = " ".join((payload.get("patient") or "").split())[:200]
    if not db.patient_key(name):
        return None
    p, created = db.ensure_patient(u["id"], name)       # homônimos → db.AmbiguousPatient (quem chama trata)
    if created:
        db.log_access(u["id"], "patient_create", p["id"])
    return p


def _ambiguous():
    return JSONResponse({"error": "há mais de um paciente com esse nome: escolha qual na consulta",
                         "ambiguous": True}, status_code=409)


def _auth_or_401(request):
    u = auth.current_user(request)
    return u, (None if u else JSONResponse({"error": "não autenticado"}, status_code=401))


@app.post("/prontuario/list")
async def prontuario_list(request: Request):
    """Prontuário do paciente: cadastro completo + evoluções (com finalização e adendos)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    # o banco roda fora do laço de eventos: o servidor tem um processo só e a gravação de outra consulta não espera
    return await run_in_threadpool(_prontuario_list, u, await _json(request))


def _prontuario_list(u, payload):
    try:
        p = _note_patient(u, payload)
    except db.AmbiguousPatient:
        return _ambiguous()
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    db.log_access(u["id"], "view", p["id"], dedupe_minutes=10)
    pub = {k: v for k, v in p.items() if k != "key"}
    return {"patient": pub, "notes": db.list_notes(u["id"], p["id"], p["key"])}


@app.post("/prontuario/notes")
async def prontuario_save(request: Request):
    """Salva a evolução da consulta (ou avulsa). Finalizada → 409; grande demais → 413."""
    u, err = _auth_or_401(request)
    if err:
        return err
    # salvamento automático a cada pausa na digitação: o banco roda fora do laço de eventos (um processo só)
    return await run_in_threadpool(_prontuario_save, u, await _json(request))


def _prontuario_save(u, payload):
    try:
        p = _note_patient(u, payload)
    except db.AmbiguousPatient:
        return _ambiguous()
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    content = str(payload.get("content") or "")
    if len(content) > MAX_NOTE_CHARS:
        return JSONResponse({"error": f"evolução maior que {MAX_NOTE_CHARS} caracteres"}, status_code=413)
    data = _note_data(payload.get("data")) if payload.get("data") is not None else None
    if payload.get("data") is not None and data is None:
        return JSONResponse({"error": "evolução estruturada grande demais"}, status_code=413)
    note_id = payload.get("note_id")
    try:
        nid = db.upsert_note(u["id"], p["id"], p["key"], p["name"],
                             (payload.get("event_id") or None), (payload.get("event_title") or "")[:300] or None,
                             _iso_or_none(payload.get("event_start")), content,
                             note_id=int(note_id) if str(note_id or "").isdigit() else None, data=data)
    except db.NoteLocked:
        return JSONResponse({"error": "evolução finalizada: use um adendo"}, status_code=409)
    db.touch_patient(u["id"], p["id"])
    if data and data.get("scribe") and data["scribe"]["rec_ids"]:
        db.rec_link_note(u["id"], p["id"], data["scribe"]["rec_ids"], nid)
    rids = _rec_ids({"rec_ids": payload.get("rec_ids")})
    if rids:              # gravação desta consulta que ainda não tinha evolução (avulsa): fica ligada a ela desde já
        db.rec_link_orphans(u["id"], p["id"], rids, nid)
    db.log_access(u["id"], "note_edit", p["id"], nid, dedupe_minutes=10)
    return {"ok": True, "id": nid}


@app.patch("/prontuario/notes/{note_id}")
async def prontuario_note_update(note_id: int, request: Request):
    """Edita uma evolução anterior ainda não finalizada."""
    u, err = _auth_or_401(request)
    if err:
        return err
    return await run_in_threadpool(_prontuario_note_update, u, note_id, await _json(request))


def _prontuario_note_update(u, note_id, payload):
    content = str(payload.get("content") or "")
    if len(content) > MAX_NOTE_CHARS:
        return JSONResponse({"error": f"evolução maior que {MAX_NOTE_CHARS} caracteres"}, status_code=413)
    data = _note_data(payload.get("data")) if payload.get("data") is not None else None
    n = db.get_note(u["id"], note_id)
    if not n:
        return JSONResponse({"error": "evolução não encontrada"}, status_code=404)
    if db.update_note(u["id"], note_id, content, data) is False:
        return JSONResponse({"error": "evolução finalizada: use um adendo"}, status_code=409)
    db.log_access(u["id"], "note_edit", n["patient_id"], note_id, dedupe_minutes=10)
    return {"ok": True, "id": note_id}


def _timing(v):
    """Tempo de documentação da evolução (linha de base da gravação): só números, limitados. None se vazio."""
    if not isinstance(v, dict):
        return None
    def nums(d, lim):
        out = {}
        for k, top in lim.items():
            x = d.get(k)
            if isinstance(x, (int, float)) and not isinstance(x, bool) and 0 <= x <= top:
                out[k] = int(x)
        return out
    out = nums(v, {"active_s": 86400, "wall_s": 30 * 86400, "edits": 100000})
    if isinstance(v.get("scribe"), dict):              # evolução gerada pela gravação: critérios 5 e 6 do plano
        sc = nums(v["scribe"], {"rec_s": 6 * 3600, "gen_s": 3600, "review_s": 30 * 86400, "fim_s": 30 * 86400,
                                "mantido_pct": 100, "alto": 1000, "medio": 1000, "info": 1000, "conferidos": 1000, "pendentes": 1000})
        if sc:
            out["scribe"] = sc
    return out or None


@app.post("/prontuario/notes/{note_id}/finalize")
async def prontuario_note_finalize(note_id: int, request: Request):
    """Finaliza a evolução (registro imutável; correções só por adendo)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    timing = _timing((await _json(request)).get("timing"))
    n = await run_in_threadpool(db.get_note, u["id"], note_id)
    if not n:
        return JSONResponse({"error": "evolução não encontrada"}, status_code=404)
    signed = await run_in_threadpool(db.finalize_note, u["id"], note_id, timing)
    if not signed:
        return JSONResponse({"error": "evolução vazia não pode ser finalizada"}, status_code=400)
    await run_in_threadpool(db.log_access, u["id"], "note_finalize", n["patient_id"], note_id)
    return {"ok": True, "signed_at": signed}


@app.post("/prontuario/notes/{note_id}/addenda")
async def prontuario_note_addendum(note_id: int, request: Request):
    u, err = _auth_or_401(request)
    if err:
        return err
    content = str((await _json(request)).get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "adendo vazio"}, status_code=400)
    if len(content) > MAX_NOTE_CHARS:
        return JSONResponse({"error": "adendo grande demais"}, status_code=413)
    n = db.get_note(u["id"], note_id)
    a = db.add_addendum(u["id"], note_id, content) if n else None
    if not a:
        return JSONResponse({"error": "só evoluções finalizadas recebem adendo"}, status_code=400)
    db.log_access(u["id"], "addendum", n["patient_id"], note_id)
    return {"ok": True, "addendum": a}


@app.post("/prontuario/visits")
async def prontuario_visits(request: Request):
    """Consultas do paciente no calendário (anteriores e próximas) com a situação da evolução."""
    u, err = _auth_or_401(request)
    if err:
        return err
    payload = await _json(request)
    pid = payload.get("patient_id")
    p = db.get_patient(u["id"], int(pid)) if str(pid or "").isdigit() else None
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    connected = db.connected_providers(u["id"])
    if not connected:
        return {"connected": False, "visits": []}
    prov = "google" if "google" in connected else next(iter(connected))
    # eventos antigos (só com o nome) só entram se ninguém mais tem esse nome
    legacy_name = p["name"] if len(db.find_patients(u["id"], p["name"])) == 1 else None
    visits = integrations.patient_events(u["id"], prov, p["id"], legacy_name)
    notes = db.notes_by_event(u["id"], [v["id"] for v in visits])
    for v in visits:
        v["note"] = notes.get(v["id"])
    return {"connected": True, "visits": visits}


@app.post("/prontuario/audit")
async def prontuario_audit(request: Request):
    """Ações feitas só na tela que precisam constar no registro (ex.: exportar/imprimir)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    payload = await _json(request)
    action = payload.get("action")
    pid = payload.get("patient_id")
    if action not in ("export",) or not str(pid or "").isdigit() or not db.get_patient(u["id"], int(pid)):
        return JSONResponse({"error": "inválido"}, status_code=400)
    db.log_access(u["id"], action, int(pid))
    return {"ok": True}


@app.post("/prontuario/access")
async def prontuario_access(request: Request):
    """Registro de acessos do paciente (quem viu/alterou e quando)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    pid = (await _json(request)).get("patient_id")
    if not str(pid or "").isdigit() or not db.get_patient(u["id"], int(pid)):
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    return {"access": db.list_access(u["id"], int(pid))}


# --- exames anexados (PDF/imagem do laudo) ---
MAX_FILE_BYTES = 10 * 1024 * 1024
_FILE_MAGIC = (("application/pdf", b"%PDF-"), ("image/jpeg", b"\xff\xd8\xff"), ("image/png", b"\x89PNG\r\n\x1a\n"))


def _sniff(b):
    """Tipo pelo conteúdo (nunca pelo que o navegador diz): PDF, JPG, PNG ou WEBP. SVG/HTML não entram."""
    for mime, magic in _FILE_MAGIC:
        if b.startswith(magic):
            return mime
    return "image/webp" if b[:4] == b"RIFF" and b[8:12] == b"WEBP" else None


def _file_name(v):
    n = urllib.parse.unquote(str(v or ""))[:200]
    return re.sub(r"[\x00-\x1f\x7f/\\]+", " ", n).strip() or "exame"


def _file_id_ok(file_id):
    return 0 < file_id < 2 ** 62


@app.post("/prontuario/files")
async def prontuario_file_add(request: Request):
    """Anexa um exame. O corpo é o próprio arquivo; o paciente vai pelo id no cabeçalho (nunca o nome
    na URL). Cabeçalho próprio + tipo não-JSON obrigam o pre-flight: outro site não consegue enviar."""
    u, err = _auth_or_401(request)
    if err:
        return err
    pid = str(request.headers.get("x-patient-id") or "")
    if not pid.isdigit() or not db.get_patient(u["id"], int(pid)):
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    cl = request.headers.get("content-length") or ""
    if cl.isdigit() and int(cl) > MAX_FILE_BYTES:
        return JSONResponse({"error": "arquivo maior que 10 MB"}, status_code=413)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_FILE_BYTES:
            return JSONResponse({"error": "arquivo maior que 10 MB"}, status_code=413)
    mime = _sniff(bytes(body[:16]))
    if not mime:
        return JSONResponse({"error": "formato não aceito: envie PDF, JPG, PNG ou WEBP"}, status_code=415)
    f = db.add_file(u["id"], int(pid), _file_name(request.headers.get("x-file-name")), mime, bytes(body))
    db.log_access(u["id"], "file_add", int(pid))
    return {"ok": True, "file": f}


@app.post("/prontuario/files/list")
async def prontuario_file_list(request: Request):
    u, err = _auth_or_401(request)
    if err:
        return err
    pid = (await _json(request)).get("patient_id")
    if not str(pid or "").isdigit() or not db.get_patient(u["id"], int(pid)):
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    return {"files": db.list_files(u["id"], int(pid))}


@app.get("/prontuario/files/{file_id}")
def prontuario_file_get(file_id: int, request: Request):
    """Abre o anexo (só o médico dono). Fica registrado no histórico de acessos."""
    u, err = _auth_or_401(request)
    if err:
        return err
    f = db.get_file(u["id"], file_id) if _file_id_ok(file_id) else None
    if not f:
        return JSONResponse({"error": "anexo não encontrado"}, status_code=404)
    db.log_access(u["id"], "file_view", f["patient_id"], dedupe_minutes=10)
    return Response(f["data"], media_type=f["mime"], headers={
        "Content-Disposition": "inline; filename*=UTF-8''" + urllib.parse.quote(f["name"]),
        "Cache-Control": "private, no-store"})


@app.delete("/prontuario/files/{file_id}")
def prontuario_file_delete(file_id: int, request: Request):
    """Remove um anexo (arquivo errado ou de outro paciente). Fica registrado no histórico de acessos."""
    u, err = _auth_or_401(request)
    if err:
        return err
    pid = db.delete_file(u["id"], file_id) if _file_id_ok(file_id) else None
    if pid is None:
        return JSONResponse({"error": "anexo não encontrado"}, status_code=404)
    db.log_access(u["id"], "file_delete", pid)
    return {"ok": True}


# --- gravação da consulta (só contas liberadas: SCRIBE_EMAILS / SCRIBE_ALL; SCRIBE_OFF desliga) ---
# O áudio vem em trechos WAV, fica só na memória durante a transcrição e some; guarda-se o texto.
MAX_SEG_BYTES = 5 * 1024 * 1024
_EM_ANDAMENTO = {}                      # (médico, gravação, trecho) → transcrição em curso (um processo só no Render)
MAX_SEG_S = 60                          # trecho normal: 15–30 s
SCRIBE_DAY_S = 6 * 3600                 # teto por médico em 24 h


def _scribe_gate(u):
    """None se a conta pode gravar; senão a resposta. Desligado (SCRIBE_OFF) ou sem chave → 503: a página
    guarda os trechos e tenta de novo depois. Conta sem a gravação → 403."""
    if config.SCRIBE_OFF:
        return JSONResponse({"error": "gravação desligada no momento"}, status_code=503)
    if not scribe_on(u):
        return JSONResponse({"error": "gravação não liberada para esta conta"}, status_code=403)
    if not config.OPENAI_API_KEY:
        return JSONResponse({"error": "transcrição indisponível no momento"}, status_code=503)
    return None


def _wav_seconds(b):
    """Duração de um WAV PCM 16 bits mono 16 kHz (o formato da página) ou None se for outra coisa."""
    if len(b) < 46 or b[:4] != b"RIFF" or b[8:12] != b"WAVE" or b[12:16] != b"fmt " or b[36:40] != b"data":
        return None
    fmt, ch, rate = struct.unpack("<HHI", b[20:28])
    bits, n = struct.unpack("<H", b[34:36])[0], struct.unpack("<I", b[40:44])[0]
    if fmt != 1 or ch != 1 or rate != 16000 or bits != 16 or not 0 < n <= len(b) - 44:
        return None
    return n / 32000


def _num_or_none(v, lo, hi):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def _rec_ids(b):
    ids = [b.get("rec_id")] + (b.get("rec_ids") if isinstance(b.get("rec_ids"), list) else [])
    return [str(x).lower() for x in ids[:20] if _UUID.match(str(x or "").lower())]


def _years(bd):
    d = _date_or_none(bd)
    if not d:
        return ""
    b, t = datetime.date.fromisoformat(d), datetime.date.today()
    return f"{t.year - b.year - ((t.month, t.day) < (b.month, b.day))} anos"


@app.post("/prontuario/transcribe")
async def prontuario_transcribe(request: Request):
    """Transcreve um trecho da gravação. O corpo é o WAV; paciente, gravação e ordem vão em cabeçalhos (nunca
    o nome). Reenvio do mesmo rec_id + seq devolve o texto já guardado, sem transcrever (nem cobrar) de novo.
    Cabeçalho próprio + tipo não-JSON obrigam o pre-flight: outro site não consegue enviar."""
    u, err = _auth_or_401(request)
    if err:
        return err
    gate = _scribe_gate(u)
    if gate:
        return gate
    h = request.headers
    pid, rid, seq = str(h.get("x-patient-id") or ""), str(h.get("x-rec-id") or "").lower(), str(h.get("x-seq") or "")
    if not (pid.isdigit() and _UUID.match(rid) and seq.isdigit() and 0 < int(seq) <= 2000):
        return JSONResponse({"error": "trecho sem identificação"}, status_code=400)
    consent = _iso_or_none(h.get("x-consent"))
    if not consent:
        return JSONResponse({"error": "autorização do paciente obrigatória"}, status_code=400)
    # o servidor tem um processo só: o banco (no Canadá) roda fora do laço de eventos, para um trecho não segurar os outros
    seq = int(seq)

    def paciente_e_trecho():                 # o paciente do médico e, se este trecho já subiu, o texto dele
        pt = db.get_patient(u["id"], int(pid))
        return pt, pt and db.rec_segment(u["id"], rid, seq)
    p, done = await run_in_threadpool(paciente_e_trecho)
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    if done:
        return {"ok": True, "text": done["text"], "duvidas": done["duvidas"], "repetido": True}
    if _rate_limited(request, "transcribe"):
        return JSONResponse({"error": "muitos trechos em pouco tempo"}, status_code=429)
    cl = h.get("content-length") or ""
    if cl.isdigit() and int(cl) > MAX_SEG_BYTES:
        return JSONResponse({"error": "trecho grande demais"}, status_code=413)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_SEG_BYTES:
            return JSONResponse({"error": "trecho grande demais"}, status_code=413)
    dur = _wav_seconds(bytes(body))
    if dur is None:
        return JSONResponse({"error": "formato não aceito: WAV 16 kHz mono"}, status_code=415)
    if dur > MAX_SEG_S:
        return JSONResponse({"error": "trecho longo demais"}, status_code=413)
    nid = str(h.get("x-note-id") or "")

    def prepare():
        if db.rec_seconds_today(u["id"]) + dur > SCRIBE_DAY_S:
            return "teto", None
        if not db.rec_open(u["id"], p["id"], rid, str(h.get("x-event-id") or "")[:300] or None,
                           int(nid) if nid.isdigit() else None, consent):
            return "outra", None
        return None, db.rec_prev_text(u["id"], rid, seq)
    why, prev = await run_in_threadpool(prepare)
    if why == "teto":
        return JSONResponse({"error": "limite de 6 horas de gravação em 24 horas"}, status_code=429)
    if why == "outra":
        return JSONResponse({"error": "gravação não encontrada"}, status_code=404)
    key = (u["id"], rid, seq)
    if key in _EM_ANDAMENTO:      # o mesmo trecho já está sendo transcrito (outra aba, reenvio depois do corte de 100 s)
        r = await asyncio.shield(_EM_ANDAMENTO[key])
        if not r:
            return JSONResponse({"error": "a transcrição falhou; o trecho fica guardado e é enviado de novo"}, status_code=502)
        return {"ok": True, "text": r["text"], "duvidas": r["duvidas"], "repetido": True}
    fut = _EM_ANDAMENTO[key] = asyncio.get_running_loop().create_future()
    t0 = time.time()
    try:
        # contexto: o fim do trecho anterior, sem CPF, telefone e e-mail; o nome falado fica (o áudio já o tem)
        r = await stt.atranscribe(bytes(body), "audio/wav", prompt=scribe.mask_docs(prev), keywords=scribe.keywords(p))

        def save():
            db.rec_add_segment(u["id"], rid, seq, _num_or_none(h.get("x-at"), 0, 24 * 3600) or 0.0, dur, r["text"], r["duvidas"])
            db.log_access(u["id"], "recording", p["id"], dedupe_minutes=180)
        await run_in_threadpool(save)
        fut.set_result(r)
    except Exception as e:                                  # o log nunca leva conteúdo
        print("[gravacao] transcrição falhou:", type(e).__name__, flush=True)
        return JSONResponse({"error": "a transcrição falhou; o trecho fica guardado e é enviado de novo"}, status_code=502)
    finally:
        if not fut.done():
            fut.set_result(None)
        _EM_ANDAMENTO.pop(key, None)
    print(f"[gravacao] trecho {seq}: {dur:.1f} s transcritos em {time.time() - t0:.1f} s", flush=True)
    return {"ok": True, "text": r["text"], "duvidas": r["duvidas"]}


def _rec_patient(u, b):
    pid = b.get("patient_id")
    return db.get_patient(u["id"], int(pid)) if str(pid or "").isdigit() else None


def _rec_where(b):
    nid = int(b["note_id"]) if str(b.get("note_id") or "").isdigit() else None
    eid = str(b.get("event_id") or "")[:300] or None
    # consulta avulsa ainda sem evolução: a gravação feita até aqui não tem consulta nem evolução. Consulta que já tem
    # evolução acha as gravações por ela (salvar a evolução liga a gravação): nunca pega a de outra consulta avulsa
    return eid, nid, _rec_ids(b), bool(b.get("orfas")) and not eid and nid is None


@app.post("/prontuario/recordings/state")
async def prontuario_recordings_state(request: Request):
    """O que já foi transcrito nesta consulta (para continuar depois que a aba fechou ou a internet caiu)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    b = await _json(request)
    p = await run_in_threadpool(_rec_patient, u, b)
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    recs = await run_in_threadpool(db.rec_list, u["id"], p["id"], *_rec_where(b))
    return {"recordings": [{k: r[k] for k in ("rec_id", "status", "consent_at", "seconds", "updated_at", "segments", "scribe")}
                           for r in recs]}


def _line(obj):
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.post("/prontuario/scribe")
async def prontuario_scribe(request: Request):
    """Escreve a evolução a partir das transcrições da consulta e confere (sem IA) números, remédios, doses,
    alergias, sinais vitais e CID. Responde em linhas JSON (progresso, depois o resultado): a geração leva
    uns 10–20 s e a linha de progresso mantém a conexão viva (o Cloudflare corta resposta parada em 100 s).
    Vai ao modelo só texto mascarado (nome, CPF, telefone, e-mail), o cadastro e o perfil de escrita."""
    t0 = time.monotonic()
    u, err = _auth_or_401(request)
    if err:
        return err
    gate = _scribe_gate(u)
    if gate:
        return gate
    b = await _json(request)
    # segundos entre o "Encerrar" e este pedido (trechos ainda subindo): entram no tempo até a evolução pronta (critério 5)
    espera = b["espera_s"] if isinstance(b.get("espera_s"), int) and not isinstance(b["espera_s"], bool) and 0 <= b["espera_s"] <= 3600 else 0
    p = await run_in_threadpool(_rec_patient, u, b)
    if not p:
        return JSONResponse({"error": "paciente obrigatório"}, status_code=400)
    if _rate_limited(request, "scribe"):
        return JSONResponse({"error": "muitos pedidos em pouco tempo"}, status_code=429)
    eid, nid, rids, _ = _rec_where(b)
    recs = await run_in_threadpool(db.rec_list, u["id"], p["id"], eid, nid, rids)
    segs, table = [], []                     # numeração única para o modelo, mesmo com mais de uma gravação
    for r in recs:
        for s in r["segments"]:
            if (s.get("text") or "").strip():
                table.append({"n": len(table) + 1, "rec_id": r["rec_id"], "seq": s["seq"], "at": s["at"]})
                segs.append({"seq": len(table), "at": s["at"], "text": s["text"], "duvidas": s.get("duvidas") or []})
    if not segs:
        return JSONResponse({"error": "nada transcrito nesta consulta ainda"}, status_code=400)
    mode = "soap" if b.get("mode") == "soap" else "free"
    cad = {"age": _years(p.get("birth_date")), "sex": p.get("sex") or "", "problems": p["problems"],
           "medications": p["medications"], "allergies": p["allergies"]}
    profile, last = await run_in_threadpool(lambda: (scribe.writing_profile(db.recent_notes(u["id"])),
                                                     db.last_note_content(u["id"], p["id"], nid, eid)))
    msgs = scribe.build_messages(segs, mode, cad, profile, last, p["name"])

    async def run():
        yield _line({"step": "escrevendo", "trechos": len(segs)})
        task = asyncio.ensure_future(asyncio.to_thread(scribe.ask_model, msgs))
        while True:
            done, _ = await asyncio.wait({task}, timeout=8)
            if done:
                break
            yield _line({"step": "escrevendo"})
        try:
            raw = task.result()
        except Exception as e:                              # o log nunca leva conteúdo
            print("[gravacao] geração falhou:", type(e).__name__, flush=True)
            yield _line({"error": "o serviço de IA não respondeu"})
            return
        yield _line({"step": "conferindo"})
        res, flags, _ = scribe.finish(raw, segs, mode, cad, p["name"])
        fields = scribe.render_text(res)
        if not any(v.strip() for v in fields.values()):
            yield _line({"error": "a IA não devolveu uma evolução válida"})
            return
        meta = _scribe_rastreio({
            "rec_ids": [r["rec_id"] for r in recs], "prompt": scribe.PROMPT_VERSION, "model": config.OPENAI_SCRIBE_MODEL,
            "segundos": int(sum(r["seconds"] or 0 for r in recs)),
            "consent_at": recs[0]["consent_at"], "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pontos": {k: sum(1 for f in flags if f["nivel"] == k) for k in ("alto", "medio", "info")},
            "gen_s": min(3600, espera + round(time.monotonic() - t0))})       # guardado: volta ao recarregar a página
        result = dict(res, fields=fields)

        def save():
            db.rec_generated(u["id"], p["id"], meta["rec_ids"], dict(meta, saida={"result": result, "flags": flags, "segs": table}), nid)
            db.log_access(u["id"], "scribe", p["id"], nid)
        await run_in_threadpool(save)
        yield _line({"ok": True, "result": result, "flags": flags, "segs": table, "meta": meta})
    return StreamingResponse(run(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.delete("/prontuario/recordings/{rec_id}")
def prontuario_recording_delete(rec_id: str, request: Request):
    """Apaga a transcrição de uma gravação. Fica registrado no histórico de acessos."""
    u, err = _auth_or_401(request)
    if err:
        return err
    pid = db.rec_delete(u["id"], rec_id.lower()) if _UUID.match(rec_id.lower()) else None
    if pid is None:
        return JSONResponse({"error": "gravação não encontrada"}, status_code=404)
    db.log_access(u["id"], "recording_delete", pid)
    return {"ok": True}


# --- CID-10 (tabela oficial do DATASUS): busca para o diagnóstico da evolução ---
@app.get("/cid10")
def cid10_search(request: Request, q: str = "", limit: int = 20):
    """Busca por código ou descrição. O termo é clínico (não identifica paciente)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    return {"items": cid10.search(q, max(1, min(limit, 50)))}


# --- pacientes: o campo "Paciente" da agenda escolhe um existente ou cria um novo ---
@app.get("/patients")
def patients_list(request: Request):
    """Lista completa do médico (a busca filtra no navegador; nome nunca vai em URL)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    return {"patients": db.list_patients(u["id"])}


@app.post("/patients")
async def patients_create(request: Request):
    """Cria o paciente. Já existe alguém com o mesmo nome → 409 com os homônimos, a menos que
    a tela confirme (force=true) que é outra pessoa."""
    u, err = _auth_or_401(request)
    if err:
        return err
    payload = await _json(request)
    f, msg = _patient_fields(payload, partial=False)
    if msg:
        return JSONResponse({"error": msg}, status_code=400)
    other = db.find_by_cpf(u["id"], f.get("cpf"))
    if other:
        return JSONResponse({"error": f"CPF já cadastrado para {other['name']}"}, status_code=409)
    same = db.find_patients(u["id"], f["name"])
    if same and not payload.get("force"):
        return JSONResponse({"error": "já existe paciente com esse nome", "duplicates":
                             [{"id": x["id"], "name": x["name"], "birth_date": x["birth_date"]} for x in same]},
                            status_code=409)
    p = db.create_patient(u["id"], f["name"], f.get("birth_date"), f.get("sex"), f.get("cpf"), f.get("phone"))
    db.log_access(u["id"], "patient_create", p["id"])
    return {"ok": True, "patient": {k: v for k, v in p.items() if k != "key"}, "created": True}


@app.patch("/patients/{patient_id}")
async def patients_update(patient_id: int, request: Request):
    """Atualiza cadastro e/ou resumo clínico (alergias, problemas, medicações)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    f, msg = _patient_fields(await _json(request))
    if msg:
        return JSONResponse({"error": msg}, status_code=400)
    other = db.find_by_cpf(u["id"], f.get("cpf"), exclude_id=patient_id)
    if other:
        return JSONResponse({"error": f"CPF já cadastrado para {other['name']}"}, status_code=409)
    p = db.update_patient(u["id"], patient_id, f)
    if not p:
        return JSONResponse({"error": "paciente não encontrado"}, status_code=404)
    db.log_access(u["id"], "patient_update", patient_id)
    return {"ok": True, "patient": {k: v for k, v in p.items() if k != "key"}}


@app.delete("/patients/{patient_id}")
def patients_delete(patient_id: int, request: Request):
    """Só exclui cadastro sem prontuário (anotações clínicas são guardadas)."""
    u, err = _auth_or_401(request)
    if err:
        return err
    r = db.delete_patient(u["id"], patient_id)
    if r == "not_found":
        return JSONResponse({"error": "paciente não encontrado"}, status_code=404)
    if r == "has_notes":
        return JSONResponse({"error": "paciente com prontuário não pode ser excluído"}, status_code=409)
    return {"ok": True}


# serve o front-end (web/) na mesma origem — registrado por último para não
# sombrear as rotas acima. Abra http://127.0.0.1:8000/opendoctor-agenda.html
if os.path.isdir(WEB_DIR):
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
