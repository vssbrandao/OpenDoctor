"""Transcrição do áudio da consulta (speech-to-text).

Hoje usa a OpenAI (/v1/audio/transcriptions), que pela documentação dela não guarda o áudio nem o texto
(retenção "None" no monitoramento de abuso). Trocar de transcritor = escrever outra função com a mesma
assinatura e apontar config.OPENAI_STT_MODEL / o provedor; a revisão de privacidade vem junto.

O áudio nunca é gravado em disco, banco ou log aqui: entra em memória, vai para a transcrição e sai como texto.
"""
import asyncio
import re
import time
import unicodedata

import httpx

from . import config

URL = "https://api.openai.com/v1/audio/transcriptions"
MAX_BYTES = 25 * 1024 * 1024          # limite da OpenAI por arquivo
_BAD_KW = ("<", ">", "\r", "\n")      # a API recusa o pedido inteiro se uma palavra-chave tiver isso
_RETRY = (408, 409, 429, 500, 502, 503, 504)
_TRIES = 3
# palavra com confiança abaixo disto (produto dos pedaços) é marcada como duvidosa. Calibrado em 15/10/2026 com os
# cortes da página (evals/scribe/relatorios/duvida-2026-10-15.md): 0,8 marca 40% dos erros do transcritor (0,6: 14%)
# com a mesma precisão, ~1 em 3 palavras marcadas está errada de fato; custa ~1 ponto a mais para conferir por consulta.
DUVIDA = 0.8

# Frases que os transcritores da família Whisper "ouvem" em silêncio ou ruído (vêm de legendas de vídeo do
# treino). Em português aparecem muito; numa consulta, nunca são fala de verdade.
# Só a frase inteira, e no formato de legenda/vídeo: "Legenda da receita: …" e "Inscreva-se no grupo de tabagismo" são fala.
_ALUCINA = [r"amara\.?\s?org", r"legendas?\s+(pela|por)\b.*", r"legendas?\s+(da|de)\s+(comunidade|amara)\b.*",
            r"legendad[oa]\s+por\b.*", r"obrigad[oa]s?\s+por\s+assistir",
            r"inscreva-?\s?se(\s+no\s+(nosso\s+|meu\s+)?canal\b.*|\s+e\s+ative\b.*)?", r"ative\s+o\s+sininho",
            r"deixe\s+(seu|o)\s+like", r"(sous|sub)-?titres?\b.*",
            r"transcri[çc][ãa]o\s+(e\s+legendas?\s+)?por\b.*", r"legenda\s+adriana\s+zanotto", r"\bcc\s+por\b.*"]
_ALUCINA_RE = re.compile(r"(?i)^\s*(?:" + "|".join(_ALUCINA) + r")\s*[.!]*\s*$")
_SO_TCHAU = re.compile(r"(?i)^\s*(tchau[,!. ]*)+$")


def _keywords(words):
    out, seen = [], set()
    for w in words or []:
        w = " ".join(str(w).split())[:60]
        if w and not any(c in w for c in _BAD_KW) and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[:50]


def _form(model, prompt, keywords, confidence=True):
    """Campos do formulário (multipart). Listas viram campos repetidos com [] (o httpx repete cada item)."""
    data = {"model": model, "response_format": "json"}
    if confidence:                           # confiança por pedaço de palavra (gpt-transcribe e gpt-4o-*-transcribe)
        data["include[]"] = ["logprobs"]
    if model == "gpt-transcribe":
        data["languages[]"] = ["pt"]
        kw = _keywords(keywords)
        if kw:
            data["keywords[]"] = kw
    else:
        data["language"] = "pt"
    if prompt:
        data["prompt"] = prompt[-800:]       # só o fim do trecho anterior: dá contexto, não estoura
    return data


def _plain(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", t))


def clean(text, prompt=""):
    """Tira frases-fantasma de silêncio e a repetição do contexto (o modelo às vezes devolve o próprio
    prompt quando o trecho não tem fala)."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    keep = [p for p in parts if p and not _ALUCINA_RE.match(p)]
    out = " ".join(keep).strip()
    if _SO_TCHAU.match(out):
        return ""
    po, pp = _plain(out), _plain(prompt)
    if po and len(po) >= 20 and pp.endswith(po):          # cópia exata do fim do trecho anterior
        return ""
    return out


def words(logprobs):
    """Palavras com a confiança (produto das probabilidades dos pedaços): [(palavra, p)]. Pontuação sozinha
    não conta como palavra."""
    import math
    out, cur, lp = [], "", 0.0
    for t in logprobs or []:
        tok = t.get("token") or ""
        if tok[:1].isspace() or not cur:
            if re.search(r"\w", cur):
                out.append((cur.strip(), math.exp(lp)))
            cur, lp = tok, 0.0
        else:
            cur += tok
        if re.search(r"\w", tok):
            lp += float(t.get("logprob") or 0.0)
    if re.search(r"\w", cur):
        out.append((cur.strip(), math.exp(lp)))
    return [(re.sub(r"^\W+|\W+$", "", w), p) for w, p in out if re.sub(r"^\W+|\W+$", "", w)]


_PALAVRA = re.compile(r"\w[\w'.,/-]*\w|\w")


def present_words(text):
    """Palavras do texto como o transcritor as devolve, inclusive com vírgula, ponto, barra ou hífen no meio
    ("6,9", "38,2", "12/12h", "punho-percussão"): é com elas que se cruza a confiança por palavra."""
    return set(_PALAVRA.findall(text or ""))


def _parse(r, prompt):
    if r.status_code != 200:
        raise RuntimeError(f"transcrição {r.status_code}: {r.text[:200]}")
    j = r.json()
    raw = (j.get("text") or "").strip()
    text = clean(raw, prompt)
    ws = words(j.get("logprobs"))
    present = present_words(text)
    duv = sorted({w for w, p in ws if p < DUVIDA and w in present})
    return {"text": text, "raw": raw, "usage": j.get("usage") or {}, "duvidas": duv,
            "confianca": round(sum(p for _, p in ws) / len(ws), 3) if ws else None,
            "palavras": [[w, round(p, 4)] for w, p in ws]}           # para calibrar o limite DUVIDA


def _wait(r, attempt):
    try:
        ra = float(r.headers.get("retry-after", "")) if r is not None else None
    except ValueError:
        ra = None
    return min(10.0, ra if ra is not None else 1.5 * 2 ** attempt)


def _args(audio, mime, prompt, keywords, model, confidence=True):
    if not audio:
        raise ValueError("trecho de áudio vazio")
    if len(audio) > MAX_BYTES:
        raise ValueError("trecho de áudio grande demais")
    model = model or config.OPENAI_STT_MODEL
    files = {"file": ("trecho." + mime.split("/")[-1].split(";")[0], audio, mime)}
    return dict(headers={"Authorization": f"Bearer {config.require_openai()}"},
                data=_form(model, prompt, keywords, confidence), files=files)


def transcribe(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
    """Síncrono (scripts e avaliação). Devolve {"text" (limpo), "raw", "usage", "duvidas" (palavras ouvidas com
    pouca certeza), "confianca"}. Tenta de novo em 429/5xx."""
    kw = _args(audio, mime, prompt, keywords, model, confidence)
    for attempt in range(_TRIES):
        try:
            r = httpx.post(URL, timeout=120, **kw)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == _TRIES - 1:
                raise
            time.sleep(_wait(None, attempt)); continue
        if r.status_code in _RETRY and attempt < _TRIES - 1:
            time.sleep(_wait(r, attempt)); continue
        return _parse(r, prompt)


async def atranscribe(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
    """Assíncrono (servidor): o Render roda um processo só; chamada síncrona travaria o app."""
    kw = _args(audio, mime, prompt, keywords, model, confidence)
    async with httpx.AsyncClient(timeout=120) as c:
        for attempt in range(_TRIES):
            try:
                r = await c.post(URL, **kw)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == _TRIES - 1:
                    raise
                await asyncio.sleep(_wait(None, attempt)); continue
            if r.status_code in _RETRY and attempt < _TRIES - 1:
                await asyncio.sleep(_wait(r, attempt)); continue
            return _parse(r, prompt)
