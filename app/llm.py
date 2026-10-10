"""Cliente de LLM (OpenAI chat completions). Non-stream e streaming.

Suporta os dois tipos de modelo da OpenAI:
- clássicos (gpt-4o, gpt-4.1): temperature + max_tokens;
- de raciocínio (gpt-5.x, o-series): sem temperature; max_completion_tokens
  (que INCLUI os tokens de raciocínio) e reasoning_effort.
"""
import json

import httpx

from . import config

URL = "https://api.openai.com/v1/chat/completions"


def _headers():
    return {"Authorization": f"Bearer {config.require_openai()}",
            "Content-Type": "application/json"}


def is_reasoning(model):
    return (model or "").startswith(("gpt-5", "o1", "o3", "o4"))


def _body(model, messages, temperature, max_tokens, reasoning=None, stream=False,
          verbosity=None):
    model = model or config.OPENAI_MODEL
    body = {"model": model, "messages": messages}
    if is_reasoning(model):
        # o orçamento inclui o raciocínio: reserva espaço extra p/ a resposta
        body["max_completion_tokens"] = max_tokens + config.REASONING_TOKEN_BUDGET
        body["reasoning_effort"] = reasoning or config.REASONING_EFFORT
        if model.startswith("gpt-5"):
            body["verbosity"] = verbosity or config.VERBOSITY
    else:
        body["temperature"] = temperature
        body["max_tokens"] = max_tokens
    if stream:
        body["stream"] = True
    return body


def chat(messages, temperature=0.2, max_tokens=2000, model=None, json_mode=False,
         reasoning=None):
    body = _body(model, messages, temperature, max_tokens, reasoning)
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = httpx.post(URL, headers=_headers(), timeout=120, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def stream_chat(messages, temperature=0.2, max_tokens=2000, model=None, reasoning=None,
                verbosity=None):
    """Gera os deltas de texto (str) conforme chegam do modelo."""
    body = _body(model, messages, temperature, max_tokens, reasoning, stream=True,
                 verbosity=verbosity)
    with httpx.stream("POST", URL, headers=_headers(), json=body, timeout=180) as r:
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
