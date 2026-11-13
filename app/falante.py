"""Quem fala em cada fala da transcrição (médico, paciente ou acompanhante). Contrato: docs/falante-contrato.md.

Fluxo, depois de cada trecho transcrito: o servidor divide o texto em frases (frases), mascara cada uma (scribe.mask:
nome do paciente, CPF, telefone, e-mail, CNS) e manda as frases numeradas, com o fim do trecho anterior já rotulado
(também mascarado), a um modelo barato (config.OPENAI_FALANTE_MODEL). Ele devolve só números e letras:
{"falas": [{"ate": <última frase da fala>, "q": "m"|"p"|"a"}, ...]}. O servidor confere a resposta (ler) e corta o
TEXTO ORIGINAL nas mesmas frases (montar): o modelo nunca reescreve nada. Qualquer erro (JSON ruim, índices fora,
cobertura incompleta, rede, sem chave, demora) → [] e o trecho segue sem rótulo: nunca derruba a transcrição.

O nome do paciente nunca vai ao modelo (o texto é mascarado frase a frase antes de montar o prompt). O log só leva
números. A evolução continua lendo o texto sem rótulo nesta fase.
"""
import asyncio
import json
import os
import re
import time

from . import config, llm, scribe

PROMPT_VERSION = "2026-11-13.1"
Q = ("m", "p", "a")
NOME_Q = {"m": "Médico", "p": "Paciente", "a": "Acompanhante"}
MAX_FRASES = 120            # trecho de 15–30 s tem bem menos; acima disso algo saiu errado: segue sem rótulo
MAX_CHARS = 6000
CONTEXTO_CHARS = 300        # o fim do trecho anterior que vai como contexto
TIMEOUT_S = 8               # teto da chamada (o servidor também corta em 8 s com asyncio.wait_for)
MAX_TOKENS = 600            # saída curta: ~10 tokens por fala

with open(os.path.join(os.path.dirname(__file__), "data", "falante_prompt.txt"), encoding="utf-8") as _f:
    PROMPT = _f.read().strip()

# fim de frase: ponto, interrogação, exclamação ou reticências (com aspas ou parêntese logo depois) seguidos de espaço
_FIM = re.compile(r"(?<=[.!?…])[\"”')\]]*\s+")
# "Sr." / "Sra." / "Dr." não fecham a frase: o nome que vem depois fica junto do tratamento (a máscara depende disso)
_ABREV = re.compile(r"(?:^|\W)(?:sr|sra|srta|dr|dra|d)\.[\"”')\]]*$", re.I)


def frases(text):
    """Divide o texto em pedaços que, juntos, dão EXATAMENTE o texto: cada pedaço é uma frase com o espaço que vem depois
    dela. Só pedaços com alguma letra ou número contam como frase (pontuação solta fica com a frase anterior)."""
    text = str(text or "")
    pedacos, ini = [], 0
    for m in _FIM.finditer(text):
        if _ABREV.search(text[ini:m.start()]):
            continue
        pedacos.append(text[ini:m.end()])
        ini = m.end()
    if ini < len(text):
        pedacos.append(text[ini:])
    out = []
    for p in pedacos:
        if out and not re.search(r"\w", p):
            out[-1] += p
        else:
            out.append(p)
    if len(out) > 1 and not re.search(r"\w", out[0]):          # texto que começa com pontuação solta
        out[1] = out[0] + out[1]
        out.pop(0)
    return out


def mascarar_seq(pedacos, patient_name="", base=""):
    """Cada pedaço mascarado COM o que vem antes dele (o fim do trecho anterior em `base` e os pedaços anteriores): a
    máscara de um nome que também é palavra comum ("Rosa", "Dias") depende do vizinho ("Sra. Rosa"), que mascarar
    pedaço por pedaço perderia. Devolve a lista mascarada ou None se a máscara não fica estável (aí nada vai ao modelo)."""
    acc = str(base or "")
    feito = scribe.mask(acc, patient_name) if acc else ""
    out = []
    for p in pedacos:
        acc += p
        m = scribe.mask(acc, patient_name)
        if not m.startswith(feito):
            return None
        out.append(m[len(feito):])
        feito = m
    return out


def contexto(prev, patient_name=""):
    """O fim do trecho anterior, mascarado: as últimas falas com o rótulo ("Médico: ...") ou, sem rótulo, o fim do
    texto. "" se não há trecho anterior."""
    prev = prev or {}
    fs = [f for f in (prev.get("falas") or []) if isinstance(f, dict) and f.get("q") in Q and str(f.get("t") or "").strip()]
    if fs:
        tudo = [str(f["t"]) for f in fs]                    # mascarado em sequência, com as falas de antes (o vizinho conta)
        ms = mascarar_seq([t if t.endswith((" ", "\n")) else t + " " for t in tudo], patient_name)
        if ms is None:
            return ""
        txt = "\n".join(f"{NOME_Q[f['q']]}: {m.strip()}" for f, m in list(zip(fs, ms))[-3:])
    else:
        txt = scribe.mask(str(prev.get("text") or "").strip(), patient_name)
    if len(txt) > CONTEXTO_CHARS:
        txt = "…" + txt[-CONTEXTO_CHARS:]
    return txt


def build_messages(frases_mascaradas, ctx=""):
    """O prompt: as frases (já mascaradas) numeradas a partir de 1 e o contexto (já mascarado)."""
    partes = []
    if ctx:
        partes += ["Fim do trecho anterior (só contexto, não rotule):", ctx, ""]
    partes += ["Frases deste trecho:"]
    partes += [f"[{i}] {f.strip()}" for i, f in enumerate(frases_mascaradas, 1)]
    return [{"role": "system", "content": PROMPT}, {"role": "user", "content": "\n".join(partes)}]


def ler(raw, n):
    """Confere a resposta do modelo com rigor: [(ate, q)] cobrindo as frases 1..n em ordem, ou None."""
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(obj, dict) and set(obj) == {"falas"}:
        obj = obj["falas"]
    if not isinstance(obj, list) or not obj or len(obj) > n:
        return None
    out, ultimo = [], 0
    for it in obj:
        if not isinstance(it, dict) or set(it) != {"ate", "q"}:
            return None
        ate, q = it["ate"], it["q"]
        if isinstance(ate, bool) or not isinstance(ate, int) or q not in Q or not ultimo < ate <= n:
            return None
        out.append((ate, q))
        ultimo = ate
    return out if ultimo == n else None


def montar(text, pedacos, cortes, at=0.0, dur=0.0):
    """As falas, cortando o TEXTO ORIGINAL nas frases dos cortes: [{q, t, at}]. Confere que juntar os pedaços dá o texto
    e que as falas, juntas, têm todos os caracteres dele (só o espaço entre uma fala e outra sai). None se não bate."""
    text = str(text or "")
    if "".join(pedacos) != text or not cortes or cortes[-1][0] != len(pedacos):
        return None
    total = max(1, len(text))
    falas, ini, antes = [], 0, 0
    for ate, q in cortes:
        bruto = "".join(pedacos[ini:ate])
        t = bruto.strip()
        if not t:
            return None
        lead = len(bruto) - len(bruto.lstrip())
        falas.append({"q": q, "t": t, "at": round(float(at) + (antes + lead) / total * float(dur), 1)})
        antes += len(bruto)
        ini = ate
    if re.sub(r"\s+", "", "".join(f["t"] for f in falas)) != re.sub(r"\s+", "", text):
        return None
    return falas


def preparar(text, patient_name="", prev=None):
    """(pedaços do texto original, mensagens para o modelo) ou (pedaços, None) se o trecho não deve ir ao modelo. O
    nome do paciente sai de cada frase (scribe.mask) e do contexto antes de montar o prompt."""
    text = str(text or "")
    pedacos = frases(text)
    if not text.strip() or not pedacos or len(pedacos) > MAX_FRASES or len(text) > MAX_CHARS:
        return pedacos, None
    # o fim do trecho anterior entra como vizinho da máscara ("Sra." no fim de um trecho e o nome no começo do próximo)
    base = str((prev or {}).get("text") or "")[-200:]
    if base and not base.endswith((" ", "\n")):
        base += " "
    mascaradas = mascarar_seq(pedacos, patient_name, base)
    if mascaradas is None:
        return pedacos, None
    return pedacos, build_messages(mascaradas, contexto(prev, patient_name))


def chamar(msgs, model=None, timeout=TIMEOUT_S):
    """Chamada ao modelo barato (o mesmo cliente do llm.chat, em JSON). {"raw", "usage"}."""
    import httpx
    model = model or config.OPENAI_FALANTE_MODEL
    body = llm._body(model, msgs, 0, MAX_TOKENS, config.OPENAI_FALANTE_REASONING)
    body["response_format"] = {"type": "json_object"}
    r = httpx.post(llm.URL, headers=llm._headers(), json=body, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}")            # sem o corpo: pode repetir o pedido
    j = r.json()
    return {"raw": j["choices"][0]["message"]["content"] or "", "usage": j.get("usage") or {}}


def ask_model(msgs, model=None):
    """Só o texto da resposta (os testes trocam esta função; nada sai para a OpenAI)."""
    return chamar(msgs, model)["raw"]


def rotular(text, patient_name="", at=0.0, dur=0.0, prev=None):
    """As falas do trecho ([{q, t, at}]) ou [] (sem rótulo) em qualquer erro. Síncrona: o servidor roda em outra thread."""
    t0 = time.time()
    try:
        if not config.OPENAI_API_KEY:
            return []
        pedacos, msgs = preparar(text, patient_name, prev)
        if msgs is None:
            return []
        cortes = ler(ask_model(msgs), len(pedacos))
        falas = montar(text, pedacos, cortes, at, dur) if cortes else None
        if not falas:
            print(f"[falante] resposta recusada: {len(pedacos)} frases", flush=True)
            return []
        print(f"[falante] {len(pedacos)} frases, {len(falas)} falas em {time.time() - t0:.1f} s", flush=True)
        return falas
    except Exception as e:                                   # o log nunca leva conteúdo
        print("[falante] falhou:", type(e).__name__, flush=True)
        return []


async def arotular(text, patient_name="", at=0.0, dur=0.0, prev=None):
    """rotular fora do laço de eventos (o preview troca esta função: o rotulador real nunca roda nele)."""
    return await asyncio.to_thread(rotular, text, patient_name, at, dur, prev)
