"""Cliente de LLM (OpenAI chat completions). Non-stream e streaming."""
import json

import httpx

from . import config

URL = "https://api.openai.com/v1/chat/completions"


def _headers():
    return {"Authorization": f"Bearer {config.require_openai()}",
            "Content-Type": "application/json"}


def chat(messages, temperature=0.2, max_tokens=2000, model=None, json_mode=False):
    body = {"model": model or config.OPENAI_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(URL, headers=_headers(), timeout=60, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


def stream_chat(messages, temperature=0.2, max_tokens=2000):
    """Gera os deltas de texto (str) conforme chegam do modelo."""
    body = {"model": config.OPENAI_MODEL, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": True}
    with httpx.stream("POST", URL, headers=_headers(), json=body, timeout=120) as r:
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.read().decode('utf-8','ignore')[:300]}")
        for line in r.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except Exception:
                delta = None
            if delta:
                yield delta
