"""Transcrição do áudio da consulta (speech-to-text).

Hoje usa a OpenAI (/v1/audio/transcriptions), que pela documentação dela não guarda o áudio nem o texto
(retenção "None" no monitoramento de abuso). Trocar de transcritor = escrever outra função com a mesma
assinatura e apontar config.OPENAI_STT_MODEL / o provedor; a revisão de privacidade vem junto.

O áudio nunca é gravado em disco, banco ou log aqui: entra em memória, vai para a transcrição e sai como texto.
"""
import httpx

from . import config

URL = "https://api.openai.com/v1/audio/transcriptions"
MAX_BYTES = 25 * 1024 * 1024          # limite da OpenAI por arquivo
_BAD_KW = ("<", ">", "\r", "\n")      # a API recusa o pedido inteiro se uma palavra-chave tiver isso


def _keywords(words):
    out, seen = [], set()
    for w in words or []:
        w = " ".join(str(w).split())[:60]
        if w and not any(c in w for c in _BAD_KW) and w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[:50]


def _form(model, prompt, keywords):
    """Campos do formulário (multipart). Listas viram campos repetidos com [] (o httpx repete cada item)."""
    data = {"model": model, "response_format": "json"}
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


def _parse(r):
    if r.status_code != 200:
        raise RuntimeError(f"transcrição {r.status_code}: {r.text[:200]}")
    j = r.json()
    return {"text": (j.get("text") or "").strip(), "usage": j.get("usage") or {}}


def transcribe(audio, mime="audio/wav", prompt="", keywords=None, model=None):
    """Síncrono (scripts e avaliação). Devolve {"text", "usage"}."""
    if len(audio) > MAX_BYTES:
        raise ValueError("trecho de áudio grande demais")
    model = model or config.OPENAI_STT_MODEL
    files = {"file": ("trecho." + mime.split("/")[-1].split(";")[0], audio, mime)}
    r = httpx.post(URL, headers={"Authorization": f"Bearer {config.require_openai()}"},
                   data=_form(model, prompt, keywords), files=files, timeout=120)
    return _parse(r)


async def atranscribe(audio, mime="audio/wav", prompt="", keywords=None, model=None):
    """Assíncrono (servidor): o Render roda um processo só; chamada síncrona travaria o app."""
    if len(audio) > MAX_BYTES:
        raise ValueError("trecho de áudio grande demais")
    model = model or config.OPENAI_STT_MODEL
    files = {"file": ("trecho." + mime.split("/")[-1].split(";")[0], audio, mime)}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(URL, headers={"Authorization": f"Bearer {config.require_openai()}"},
                         data=_form(model, prompt, keywords), files=files)
    return _parse(r)
