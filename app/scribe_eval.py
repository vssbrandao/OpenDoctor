"""Avaliação da gravação → evolução com consultas FICTÍCIAS (evals/scribe/casos/*.yaml).

Para cada caso: áudio (gravação encenada em evals/scribe/gravacoes/<id>.m4a|wav, ou voz sintética do Mac) →
cortes de 15–30 s no silêncio (como o navegador vai cortar) → transcrição → máscara → evolução →
conferências → nota contra o gabarito (revisado por médico).

Mede: erro de palavra da transcrição; remédios (certo / errado com aviso / errado SEM aviso / faltando /
inventado); sinais vitais; CID; fatos-chave; termos proibidos (inventados); avisos esperados; tempo.

Rodar:
  python -m app.scribe_eval --estimar                 # só gera o áudio e estima o custo (grátis)
  python -m app.scribe_eval --stt gpt-transcribe --modelo gpt-5.4 [--casos 01,02]   # GASTA crédito
Áudio, gravações encenadas e cache ficam fora do git (.gitignore): gravação encenada tem a voz de alguém.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np
import yaml

from . import config, scribe, stt

BASE = os.path.join(config.ROOT, "evals", "scribe")
CASOS, AUDIO, GRAV, CACHE, REL = (os.path.join(BASE, d) for d in ("casos", "audio", "gravacoes", "cache", "relatorios"))
SR = 16000
# preços oficiais (US$) em 15/10/2026 — conferir em developers.openai.com/api/docs/pricing antes de decidir
STT_MIN = {"gpt-transcribe": 0.0045, "gpt-4o-transcribe": 0.006, "gpt-4o-mini-transcribe": 0.003}
LLM_M = {"gpt-5.4": (2.50, 15.00), "gpt-5.4-mini": (0.75, 4.50)}
RUIDO = {"nenhum": 0.0, "leve": 0.004, "moderado": 0.012, "alto": 0.025}
# voz natural da OpenAI (gpt-4o-mini-tts, ~US$ 0,015 por minuto falado) no lugar das vozes robóticas do Mac
TTS_URL, TTS_MODEL, TTS_USD_MIN = "https://api.openai.com/v1/audio/speech", "gpt-4o-mini-tts", 0.015
VOZ_OPENAI = {"Luciana": ("coral", "médica adulta"), "Reed": ("cedar", "médico adulto"), "Eddy": ("ash", "médico jovem"),
              "Flo": ("shimmer", "mulher adulta"), "Sandy": ("nova", "mulher jovem"), "Shelley": ("sage", "mulher jovem"),
              "Rocko": ("onyx", "homem adulto"), "Grandma": ("marin", "senhora idosa, fala um pouco mais devagar"),
              "Grandpa": ("ballad", "senhor idoso, fala um pouco mais devagar")}
PAPEL = {"m": "o médico ou a médica", "p": "o paciente", "a": "o acompanhante"}


# ===== áudio sintético (vozes do Mac) =====
def _say(text, voice, rate):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.wav")
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", p, "--file-format=WAVE",
                        "--data-format=LEI16@16000", text], check=True)
        with wave.open(p) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def _resample_24k_16k(x):
    """24 kHz → 16 kHz (sobe 2×, filtro passa-baixa a 7,6 kHz, desce 3×) sem scipy."""
    up = np.zeros(len(x) * 2, np.float32); up[::2] = x * 2
    n = 95; t = np.arange(n) - (n - 1) / 2
    h = np.sinc(2 * (7600 / 48000) * t) * np.hamming(n); h /= h.sum()
    return np.convolve(up, h, mode="same")[::3].astype(np.float32)


def _tts(text, voz_mac, quem):
    """Fala com voz natural da OpenAI; fica no cache (nunca paga duas vezes a mesma fala)."""
    import httpx
    voice, persona = VOZ_OPENAI.get(voz_mac, ("coral", "pessoa adulta"))
    instr = (f"Fale em português do Brasil, com sotaque brasileiro natural (não de Portugal). Você é {persona}, "
             f"{PAPEL.get(quem, 'uma pessoa')} numa consulta médica: fale de forma natural, em ritmo de conversa, "
             "sem soar como locutor. Números como se fala no Brasil (128 por 82 = cento e vinte e oito por oitenta e dois).")
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, "tts-" + hashlib.sha1(f"{TTS_MODEL}|{voice}|{instr}|{text}".encode()).hexdigest()[:16] + ".pcm")
    if not os.path.exists(p):
        body = {"model": TTS_MODEL, "voice": voice, "input": text, "instructions": instr, "response_format": "pcm"}
        for attempt in range(3):
            r = httpx.post(TTS_URL, headers={"Authorization": f"Bearer {config.require_openai()}"}, json=body, timeout=120)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1)); continue
            if r.status_code != 200:
                raise RuntimeError(f"voz {r.status_code}: {r.text[:200]}")
            break
        open(p, "wb").write(r.content)
        _add_cost(len(r.content) / 2 / 24000 / 60 * TTS_USD_MIN)
    pcm = np.frombuffer(open(p, "rb").read(), dtype=np.int16).astype(np.float32) / 32768
    return _resample_24k_16k(pcm)


def synth(caso, fonte="openai"):
    """Monta a consulta: falas com pausas de 0,3–1,1 s, quem está longe do microfone mais baixo, ruído de fundo."""
    rng = np.random.default_rng(int(hashlib.sha1(caso["id"].encode()).hexdigest()[:8], 16))
    vozes = caso.get("vozes") or {}
    longe = set(caso.get("longe_do_microfone") or ["p", "a"])
    pausas = {int(k): float(v) for k, v in (caso.get("pausas") or {}).items()}     # {nº da fala: segundos de silêncio depois}
    falas = [(quem, fala, vozes.get(quem) or {"m": "Luciana", "p": "Flo", "a": "Reed"}.get(quem, "Luciana"))
             for quem, fala in caso["falas"]]
    if fonte == "openai":
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            sons = list(ex.map(lambda f: _tts(f[1], f[2], f[0]), falas))
    else:
        sons = [_say(fala, v, int(caso.get("ritmo", 180))) for _, fala, v in falas]
    parts = [np.zeros(int(SR * 0.6), np.float32)]
    for idx, ((quem, fala, v), x) in enumerate(zip(falas, sons), 1):
        if quem in longe:
            x = x * 0.55
        parts += [x, np.zeros(int(SR * (pausas.get(idx) or rng.uniform(0.3, 1.1))), np.float32)]
    a = np.concatenate(parts)
    lvl = RUIDO.get(caso.get("ruido", "leve"), 0.004)
    if lvl:
        a = a + rng.normal(0, lvl, a.shape).astype(np.float32)
    return np.clip(a, -1, 1)


def _read_any(path):
    """Gravação encenada (m4a/wav/webm/mp3) → mono 16 kHz, convertida pelo afconvert do Mac."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "g.wav")
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", path, out], check=True,
                       capture_output=True)
        with wave.open(out) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


FONTE = {"voz": "openai"}                       # "openai" (natural) ou "mac" (robótica, grátis)


def _audio_path(caso, fonte):
    return os.path.join(AUDIO, "openai", f"{caso['id']}.wav") if fonte == "openai" else os.path.join(AUDIO, f"{caso['id']}.wav")


def audio_of(caso, fonte=None):
    """(áudio, origem). Gravação encenada tem prioridade sobre a voz sintética."""
    fonte = fonte or FONTE["voz"]
    for ext in ("m4a", "wav", "webm", "mp3", "aiff"):
        p = os.path.join(GRAV, f"{caso['id']}.{ext}")
        if os.path.exists(p):
            return _read_any(p), "encenada"
    p = _audio_path(caso, fonte)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if not os.path.exists(p):
        _write_wav(p, synth(caso, fonte))
    with wave.open(p) as w:
        return (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768,
                "voz natural" if fonte == "openai" else "voz do Mac")


def _write_wav(path_or_buf, a):
    w = wave.open(path_or_buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    w.close()


def wav_bytes(a):
    b = io.BytesIO(); _write_wav(b, a); return b.getvalue()


def _frames(a, f=int(SR * 0.02)):
    return np.sqrt(np.mean(a[: len(a) // f * f].reshape(-1, f).astype(np.float64) ** 2, axis=1)) if len(a) >= f else np.zeros(0)


def noise_floor(a):
    """Piso de ruído da gravação INTEIRA (no navegador: média móvel desde o começo)."""
    rms = _frames(a)
    return float(np.percentile(rms, 10)) if len(rms) else 0.0


def speech_ratio(a, floor=None):
    """Fração de quadros de 20 ms com voz. Trecho só de silêncio não vai para a transcrição: é aí que o modelo
    inventa "Legendas pela comunidade Amara.org". O piso vem da gravação inteira (o piso do próprio trecho
    faria fala contínua parecer silêncio) e o limiar tem teto: na dúvida, o trecho é transcrito."""
    rms = _frames(a)
    if not len(rms):
        return 0.0
    floor = float(np.percentile(rms, 10)) if floor is None else floor
    return float(np.mean(rms > min(max(0.01, floor * 3), 0.03)))


# ===== cortes (o mesmo critério do navegador) =====
def cuts(a, min_s=15, max_s=30, frame_ms=20, sil_ms=250):
    """Corta entre 15 e 30 s no meio do primeiro silêncio (≥ 250 ms) depois dos 15 s; aos 30 s, no quadro mais
    baixo dos últimos 2 s. Os cortes são posições exatas: nenhuma amostra se perde."""
    f = int(SR * frame_ms / 1000)
    rms = np.sqrt(np.convolve(a.astype(np.float64) ** 2, np.ones(f) / f, mode="same"))[::f]
    thr = max(0.01, float(np.percentile(rms, 20)) * 1.8)
    out, start, n = [], 0, len(a)
    while n - start > max_s * SR:
        lo, hi = start + min_s * SR, start + max_s * SR
        fi, need, run, cut = lo // f, sil_ms // frame_ms, 0, None
        while fi < hi // f:
            run = run + 1 if rms[fi] < thr else 0
            if run >= need:
                cut = (fi - run // 2) * f
                break
            fi += 1
        if cut is None:
            seg = rms[(hi - 2 * SR) // f: hi // f]
            cut = ((hi - 2 * SR) // f + int(np.argmin(seg))) * f
        out.append((start, cut)); start = cut
    out.append((start, n))
    return out


# ===== custo de verdade (tokens que a OpenAI cobrou) e teto da rodada =====
import threading                                   # noqa: E402
SPENT = {"usd": 0.0}
TETO = {"usd": 1.75}
_LOCK = threading.Lock()


def _add_cost(usd):
    with _LOCK:
        SPENT["usd"] += usd


def chat_usage(msgs, model):
    """Mesma chamada do llm.chat (json), mas devolvendo também os tokens cobrados (o assistente não muda)."""
    import httpx
    from . import llm
    body = llm._body(model, msgs, 0, 6000, config.REASONING_EFFORT)
    body["response_format"] = {"type": "json_object"}
    t0 = time.time()
    for attempt in range(3):
        r = httpx.post(llm.URL, headers=llm._headers(), json=body, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 * (attempt + 1)); continue
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
        j = r.json()
        return {"raw": j["choices"][0]["message"]["content"] or "", "usage": j.get("usage") or {}, "t": round(time.time() - t0, 1)}


def llm_cost(model, usage):
    pin, pout = LLM_M.get(model, (2.5, 15))
    cached = ((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    return ((usage.get("prompt_tokens", 0) - cached) * pin + cached * pin / 10 + usage.get("completion_tokens", 0) * pout) / 1e6


# ===== cache (não gasta de novo o que já foi transcrito/gerado) =====
def _cache(kind, key, fn):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{kind}-{hashlib.sha1(key.encode()).hexdigest()[:16]}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")), True
    v = fn()
    json.dump(v, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return v, False


# ===== notas =====
def _words(t):
    return re.findall(r"[a-z0-9]+", scribe.norm(t))


def wer(ref, hyp):
    """Erro de palavra, com os números por extenso trocados por algarismos dos dois lados
    ("cento e vinte e oito" = "128")."""
    r, h = scribe.digitize(ref).split(), scribe.digitize(hyp).split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def doubt_quality(ref, segs):
    """Quanto as dúvidas do transcritor acertam: dos tokens errados (não batem com o roteiro), quantos foram
    marcados (cobertura); das marcas, quantas eram erro mesmo (precisão)."""
    import difflib
    hyp = []
    for x in segs:
        dv = {t for d in x.get("duvidas") or [] for t in scribe.tokens(d)}
        hyp += [(t, t in dv) for t in scribe.digitize(x["text"]).split()]
    r = scribe.digitize(ref).split()
    sm = difflib.SequenceMatcher(None, r, [t for t, _ in hyp], autojunk=False)
    ok = set()
    for blk in sm.get_matching_blocks():
        ok |= set(range(blk.b, blk.b + blk.size))
    err = [i for i in range(len(hyp)) if i not in ok]
    marked = [i for i, (_, d) in enumerate(hyp) if d]
    hit = len(set(err) & set(marked))
    return {"tok_errados": len(err), "tok_duvidosos": len(marked), "duvida_pega_erro": hit}


def calibrate_doubt(cases, stt_model, limites=(0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98)):
    """Transcreve com as palavras-chave da produção guardando a confiança de cada palavra (cache próprio) e mede,
    para cada limite, quanto a marcação de dúvida cobre os erros do transcritor e quanto acerta."""
    def one(caso):
        a, _ = audio_of(caso)
        pac = caso.get("paciente") or {}
        kw = scribe.keywords({"medications": pac.get("medicacoes", ""), "problems": pac.get("problemas", ""),
                              "allergies": pac.get("alergias", "")}, exame=True)
        tag = hashlib.sha1("|".join(kw).encode()).hexdigest()[:8]
        akey, floor, prev, segs = hashlib.sha1(a.tobytes()).hexdigest()[:16], noise_floor(a), "", []
        for i, (s0, s1) in enumerate(cuts(a), 1):
            if speech_ratio(a[s0:s1], floor) < 0.02:
                continue
            if SPENT["usd"] >= TETO["usd"]:
                raise RuntimeError("teto de gasto atingido")
            r, hit = _cache("sttw", f"{caso['id']}|{akey}|{i}|{stt_model}|{prev[-300:]}|kw:{tag}",
                            lambda: stt.transcribe(wav_bytes(a[s0:s1]), "audio/wav", prompt=prev, keywords=kw, model=stt_model))
            if not hit:
                _add_cost((s1 - s0) / SR / 60 * STT_MIN.get(stt_model, 0.006))
            segs.append(r); prev = r["text"] or prev
        return " ".join(f for _, f in caso["falas"]), segs
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, cases))
    out = []
    for t in limites:
        tot = {"tok_errados": 0, "tok_duvidosos": 0, "duvida_pega_erro": 0}
        for ref, segs in rows:
            ss = []
            for r in segs:
                present = set(re.findall(r"[\w']+", r["text"]))
                ss.append({"text": r["text"], "duvidas": sorted({w for w, p in r.get("palavras") or [] if p < t and w in present})})
            for k, v in doubt_quality(ref, ss).items():
                tot[k] += v
        out.append({"limite": t, "cobre": round(tot["duvida_pega_erro"] / max(1, tot["tok_errados"]), 3),
                    "precisao": round(tot["duvida_pega_erro"] / tot["tok_duvidosos"], 3) if tot["tok_duvidosos"] else None,
                    "marcadas": tot["tok_duvidosos"], "erros": tot["tok_errados"]})
    return out


def _nums(t):
    return sorted(round(x, 3) for x in scribe.numbers(t))


def freq(pos):
    """Tomadas por dia de uma posologia: "12/12h" e "de 12 em 12 horas" → 2; "2x/dia", "duas vezes ao dia" → 2;
    "1x/dia", "de manhã", "à noite", "em jejum", "ao deitar" → 1. None se não der para saber."""
    t = scribe.digitize(pos)
    m = re.search(r"(\d+)\s+(?:em\s+)?(\d+)\s*h", t) or re.search(r"de\s+(\d+)\s+em\s+(\d+)\s+hora", t)
    if m and float(m.group(2).replace(",", ".")) > 0:
        return round(24 / float(m.group(2).replace(",", ".")))
    m = re.search(r"(?:a\s+)?cada\s+(\d+)\s*h", t)                      # "a cada 6 horas"
    if m and float(m.group(1).replace(",", ".")) > 0:
        return round(24 / float(m.group(1).replace(",", ".")))
    m = re.search(r"(\d+)\s*(?:x|vez|vezes)\b", t)
    if m:
        return int(float(m.group(1).replace(",", ".")))
    if re.search(r"\b(manha|noite|jejum|deitar|almoco|jantar|dia)\b", t):
        return 1 + bool(re.search(r"manha.*(tarde|noite)|(tarde|noite).*manha", t))
    return None


def _txt(t):
    """Texto para comparar com o gabarito: sem acento, minúsculo, hífen como espaço ("raio-X" = "raio X")."""
    return re.sub(r"\s+", " ", scribe.norm(t).replace("-", " "))


def _has(alts, text):
    return any(_txt(a) in text for a in alts.split("|"))


def _is(alts, nome):
    return any(scribe.same_drug(x, nome) or scribe.same_drug(nome, x) for x in str(alts).split("|"))


def score(caso, res, flags):
    g = caso.get("gabarito") or {}
    script = " ".join(f for _, f in caso["falas"])
    script_nums = scribe.numbers(script)
    full = _txt(" ".join(scribe.render_text(res).values()) + " " +
                " ".join(f"{m['nome']} {m['dose']} {m['posologia']}" for m in res["meds"]))
    s = {"rem_certo": 0, "rem_aviso": 0, "rem_sem_aviso": 0, "rem_falta": 0, "rem_inventado": 0, "detalhe": []}
    usados = set()
    for gm in g.get("remedios") or []:
        hit = next((i for i, m in enumerate(res["meds"]) if i not in usados and _is(gm["nome"], m["nome"])), None)
        if hit is None:
            s["rem_falta"] += 1; s["detalhe"].append(f"faltou: {gm['nome']}"); continue
        usados.add(hit); m = res["meds"][hit]
        both = f"{m['dose']} {m['posologia']}"          # o modelo às vezes põe o volume na posologia ("8 mL de 12/12h")

        def same(k):          # "*": qualquer (ex.: mantido sem dose dita); números do gabarito contidos na saída
            if str(gm.get(k, "")) == "*":
                return True
            if k == "posologia" and freq(str(gm.get(k, ""))) and freq(both):           # "de manhã" = "1x/dia"
                return freq(str(gm.get(k, ""))) == freq(both)
            want, got = _nums(str(gm.get(k, ""))), _nums(both)
            return all(want.count(x) <= got.count(x) for x in set(want)) and (bool(want) or not got)
        acoes = str(gm.get("acao", "*")).split("|")                           # "ajustado|mantido": qualquer um
        ok = same("dose") and same("posologia") and ("*" in acoes or m["acao"] in acoes)
        if ok:
            s["rem_certo"] += 1; continue
        avisou = any(scribe.norm(m["nome"]).split()[0] in scribe.norm(f["texto"]) for f in flags)
        s["rem_aviso" if avisou else "rem_sem_aviso"] += 1
        s["detalhe"].append(f"{'avisado' if avisou else 'SEM AVISO'}: {gm['nome']} esperado {gm.get('dose','')} {gm.get('posologia','')} "
                            f"{gm.get('acao','')} / saiu {m['dose']} {m['posologia']} {m['acao']}")
    cad = (caso.get("paciente") or {}).get("medicacoes", "")
    s["rem_extra"] = 0
    for i, m in enumerate(res["meds"]):        # citado só para recusar/explicar (sem ação) não conta
        if i in usados or m["acao"] not in ("iniciado", "mantido", "ajustado"):
            continue
        falado = lambda txt: scribe.same_drug(m["nome"], txt) or any(
            len(w) >= 4 and w not in scribe._GENERICO and any(scribe._tok_eq(w, t) for t in scribe.tokens(txt))
            for w in scribe.tokens(m["nome"]))                   # "soro fisiológico" quando a fala diz "soro"
        if falado(script) or falado(cad) or scribe.same_drug(m["nome"].split()[0], script):
            s["rem_extra"] += 1; s["detalhe"].append(f"a mais (foi citado, não está no gabarito): {m['nome']} {m['acao']}")
        else:
            s["rem_inventado"] += 1; s["detalhe"].append(f"INVENTADO: {m['nome']}")
    rp = [m["nome"] for m in res["meds"] if m["acao"] in ("iniciado", "mantido", "ajustado")
          and any(_is(x, m["nome"]) for x in g.get("remedios_proibidos") or [])]
    s["detalhe"] += [f"REMÉDIO PROIBIDO com ação: {x}" for x in rp]
    alt = lambda v: [float(x.replace(",", ".")) for x in str(v).split("|")]          # "93|97": qualquer um
    gv = {k: alt(v) for k, v in (g.get("sinais") or {}).items()}
    ov = {k: float(v.replace(",", ".")) for k, v in res["vitals"].items()}
    ok_v = lambda k: k in ov and any(abs(ov[k] - x) < 1e-6 for x in gv[k])
    s["vit_certo"] = sum(1 for k in gv if ok_v(k))
    s["vit_total"] = len(gv)
    inv = [k for k in ov if k not in gv and not scribe._has_number(ov[k], script_nums)]
    s["vit_inventado"] = len(inv)
    s["detalhe"] += [f"sinal {k}: esperado {'|'.join(map(str, gv[k]))} / saiu {ov.get(k)}" for k in gv if not ok_v(k)]
    s["detalhe"] += [f"INVENTADO sinal {k} = {ov[k]}" for k in inv]
    gc = [[x.strip().upper() for x in str(c).split("|")] for c in g.get("cid") or []]     # "Z34|Z35": qualquer um
    oc = [c["code"].replace(".", "") for c in res["cid"]]
    hit = lambda o, alts: any(o.startswith(x.replace(".", "")) or x.replace(".", "").startswith(o) for x in alts)
    s["cid_certo"] = sum(1 for alts in gc if any(hit(o, alts) for o in oc))
    s["cid_total"] = len(gc)
    s["cid_extra"] = sum(1 for o in oc if not any(hit(o, alts) for alts in gc))
    fatos = g.get("fatos") or []
    ach = [all(_has(grp.strip(), full) for grp in f.split("+")) for f in fatos]
    s["fatos_ok"], s["fatos_total"] = sum(ach), len(fatos)
    s["detalhe"] += [f"fato ausente: {f}" for f, a in zip(fatos, ach) if not a]
    proib = [p for p in g.get("proibidos") or [] if _has(p, full)]
    s["proibidos"] = len(proib) + len(rp)
    s["detalhe"] += [f"INVENTADO (proibido): {p}" for p in proib]
    tipos = {f["tipo"] for f in flags}
    falt = [a for a in g.get("avisos") or [] if a not in tipos]
    s["avisos_faltando"] = len(falt)
    s["detalhe"] += [f"aviso esperado não veio: {a}" for a in falt]
    s["avisos"] = len(flags)
    return s


def load_cases(only=None):
    out = []
    for f in sorted(os.listdir(CASOS)):
        if f.endswith(".yaml"):
            c = yaml.safe_load(open(os.path.join(CASOS, f), encoding="utf-8"))
            if not only or any(c["id"].startswith(o) for o in only):
                out.append(c)
    return out


def run_case(caso, stt_model, llm_model):
    a, origem = audio_of(caso)
    pac = caso.get("paciente") or {}
    kw = [x.split(" ")[0] for x in re.split(r"[\n,;]+", pac.get("medicacoes", "")) if x.strip()]
    kw += [x.strip() for x in re.split(r"[\n,;]+", pac.get("problemas", "")) if x.strip()]
    kwtag = ""
    if FONTE.get("kw") == "app":              # as mesmas palavras-chave da produção (cadastro + exame físico)
        kw = scribe.keywords({"medications": pac.get("medicacoes", ""), "problems": pac.get("problemas", ""),
                              "allergies": pac.get("alergias", "")}, exame=True)
        kwtag = "|kw:" + hashlib.sha1("|".join(kw).encode()).hexdigest()[:8]
    segs, prev, t0 = [], "", time.time()
    akey = hashlib.sha1(a.tobytes()).hexdigest()[:16]
    silent, floor = 0, noise_floor(a)
    for i, (s0, s1) in enumerate(cuts(a), 1):
        if speech_ratio(a[s0:s1], floor) < 0.02:       # só silêncio: não transcreve (nem cobra)
            silent += 1; segs.append({"seq": i, "at": s0 / SR, "text": ""}); continue
        kind = "sttw" if FONTE.get("duvida") else "stt"   # sttw: com a confiança por palavra (--calibrar-duvida)
        r, hit = _cache(kind, f"{caso['id']}|{akey}|{i}|{stt_model}|{prev[-300:]}{kwtag}",
                        lambda: stt.transcribe(wav_bytes(a[s0:s1]), "audio/wav", prompt=prev, keywords=kw, model=stt_model))
        if FONTE.get("duvida"):                              # dúvidas refeitas com outro limite
            present = set(re.findall(r"[\w']+", r["text"]))
            r = dict(r, duvidas=sorted({w for w, p in r.get("palavras") or [] if p < FONTE["duvida"] and w in present}))
        if not hit:
            _add_cost((s1 - s0) / SR / 60 * STT_MIN.get(stt_model, 0.006))
        segs.append({"seq": i, "at": s0 / SR, "text": r["text"], "duvidas": r.get("duvidas") or []}); prev = r["text"] or prev
    t_stt = time.time() - t0
    nome = pac.get("nome", "")
    masked = [dict(x, text=scribe.mask(x["text"], nome)) for x in segs]
    patient = {"problems": pac.get("problemas", ""), "medications": pac.get("medicacoes", ""), "allergies": pac.get("alergias", ""),
               "age": pac.get("idade", ""), "sex": pac.get("sexo", "")}
    mode = caso.get("modo", "soap")
    t1 = time.time()
    msgs = scribe.build_messages(segs, mode, patient, caso.get("perfil", ""), "", nome)
    gen, cached = _cache("gen", f"{caso['id']}|{akey}|{stt_model}|{llm_model}|{scribe.PROMPT_VERSION}|{json.dumps(msgs, ensure_ascii=False)}",
                         lambda: chat_usage(msgs, llm_model))
    raw, usage = gen["raw"], gen.get("usage") or {}
    if not cached:
        _add_cost(llm_cost(llm_model, usage))
    t_gen = gen.get("t") if cached else round(time.time() - t1, 1)          # o tempo fica no cache: reavaliar não o perde
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = {}
    res, flags = scribe.check(parsed, masked, mode, patient)
    ref = " ".join(f for _, f in caso["falas"])
    sc = score(caso, res, flags)
    sc.update(doubt_quality(ref_text := " ".join(f for _, f in caso["falas"]), segs))
    sent = scribe.norm(msgs[1]["content"])
    first = [t for t in scribe.norm(nome).split() if len(t) >= 3][:1]
    sc["nome_vazou"] = bool(first) and re.search(r"\b" + re.escape(first[0]) + r"\b", sent) is not None
    sc["dado_vazou"] = bool(scribe._CPF.search(msgs[1]["content"]) or scribe._FONE.search(msgs[1]["content"]))
    return {"id": caso["id"], "origem": origem, "segundos": round(len(a) / SR, 1), "trechos": len(segs), "silencio": silent,
            "wer": round(wer(ref, " ".join(x["text"] for x in segs)), 3), "t_stt": round(t_stt, 1), "t_gen": t_gen,
            "in_chars": sum(len(m["content"]) for m in msgs), "out_chars": len(raw),
            "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens"),
            "tokens_raciocinio": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"), **sc,
            "texto": scribe.render_text(res), "pontos": flags}


def estimate(cases, stt_model, llm_model):
    def secs(c):                                  # sem gerar áudio pago só para estimar
        p = _audio_path(c, FONTE["voz"])
        if os.path.exists(p) or FONTE["voz"] == "mac":
            return len(audio_of(c)[0]) / SR
        return sum(len(f) for _, f in c["falas"]) / 14 + 0.7 * len(c["falas"]) + sum((c.get("pausas") or {}).values())
    sec = sum(secs(c) for c in cases)
    stt_usd = sec / 60 * STT_MIN.get(stt_model, 0.006)
    pin, pout = LLM_M.get(llm_model, (2.5, 15))
    llm_usd = len(cases) * (6000 * pin + 2500 * pout) / 1e6          # ~6k tokens de entrada, ~2,5k de saída por caso
    return sec, stt_usd, llm_usd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stt", default=config.OPENAI_STT_MODEL)
    ap.add_argument("--modelo", default=config.OPENAI_SCRIBE_MODEL)
    ap.add_argument("--casos", default="")
    ap.add_argument("--estimar", action="store_true", help="só gera o áudio e estima o custo (não chama a OpenAI)")
    ap.add_argument("--paralelo", type=int, default=4, help="casos ao mesmo tempo")
    ap.add_argument("--teto-usd", type=float, default=1.75, help="para de começar casos novos ao atingir este gasto")
    ap.add_argument("--voz", choices=("openai", "mac"), default="openai", help="voz sintética: natural (OpenAI) ou do Mac")
    ap.add_argument("--comparar", action="store_true", help="só junta os relatórios do dia numa tabela comparativa")
    ap.add_argument("--calibrar-duvida", action="store_true",
                    help="transcreve guardando a confiança por palavra e mede o limite de dúvida (só transcrição)")
    ap.add_argument("--duvida", type=float, default=None,
                    help="limite de dúvida (usa as transcrições com confiança por palavra; exige --kw app)")
    ap.add_argument("--kw", choices=("cadastro", "app"), default="cadastro",
                    help="palavras-chave da transcrição: só do cadastro (como antes) ou as da produção (+ exame físico)")
    a = ap.parse_args()
    FONTE["voz"] = a.voz
    FONTE["kw"] = a.kw
    FONTE["duvida"] = a.duvida
    if a.duvida and a.kw != "app":
        sys.exit("--duvida exige --kw app")
    if a.comparar:
        return compare()
    cases = load_cases([x.strip() for x in a.casos.split(",") if x.strip()])
    sec, su, lu = estimate(cases, a.stt, a.modelo)
    print(f"{len(cases)} casos · {sec / 60:.1f} min de áudio · estimativa US$ {su:.2f} (transcrição) + US$ {lu:.2f} (evolução)")
    if a.estimar:
        return
    if not config.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY ausente")
    TETO["usd"] = a.teto_usd
    if a.calibrar_duvida:
        curva = calibrate_doubt(cases, a.stt)
        os.makedirs(REL, exist_ok=True)
        md = [f"# Limite de dúvida da transcrição ({datetime.date.today().isoformat()}, {a.stt}, palavras-chave da produção)", "",
              f"Atual: {stt.DUVIDA}. Gasto nesta rodada: US$ {SPENT['usd']:.3f}.", "",
              "| limite | cobre os erros | precisão | palavras marcadas | erros do transcritor |", "|---|---|---|---|---|"]
        md += [f"| {c['limite']} | {c['cobre']:.0%} | {(c['precisao'] or 0):.0%} | {c['marcadas']} | {c['erros']} |" for c in curva]
        open(os.path.join(REL, f"duvida-{datetime.date.today().isoformat()}.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
        print("\n".join(md))
        return
    for c in cases:                  # áudio sintético antes (o "say" do Mac não gosta de rodar em paralelo)
        audio_of(c)
    if SPENT["usd"]:
        print(f"voz sintética gerada: US$ {SPENT['usd']:.3f}")
    rows, erros = [], []

    def one(c):
        if SPENT["usd"] >= a.teto_usd:
            erros.append(f"{c['id']}: não rodou (teto de US$ {a.teto_usd:.2f} atingido)")
            return None
        try:
            return run_case(c, a.stt, a.modelo)
        except Exception as e:  # noqa: BLE001 — um caso com erro não derruba a rodada
            erros.append(f"{c['id']}: {str(e)[:200]}")
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, a.paralelo)) as ex:
        for r in ex.map(one, cases):
            if not r:
                continue
            rows.append(r)
            print(f"{r['id']:34s} {r['origem']:9s} WER {r['wer']:.2f} · remédios {r['rem_certo']}✓ {r['rem_aviso']}⚠ "
                  f"{r['rem_sem_aviso']}✗ falta {r['rem_falta']} inv {r['rem_inventado']} · sinais {r['vit_certo']}/{r['vit_total']} · "
                  f"fatos {r['fatos_ok']}/{r['fatos_total']} · proibidos {r['proibidos']} · avisos faltando {r['avisos_faltando']}")
    if not rows:
        sys.exit("nenhum caso rodou: " + "; ".join(erros))
    tot = lambda k: sum(r[k] for r in rows)
    gens = [r["t_gen"] for r in rows if r["t_gen"] is not None]
    crit = {"2_dose_errada_sem_aviso": tot("rem_sem_aviso") == 0,
            "3_nada_inventado": tot("rem_inventado") + tot("proibidos") + tot("vit_inventado") == 0,
            "4_cobertura_95": tot("fatos_ok") >= 0.95 * max(1, tot("fatos_total")),
            "avisos_esperados": tot("avisos_faltando") == 0,
            "nome_e_documentos_nao_vazaram": not any(r["nome_vazou"] or r["dado_vazou"] for r in rows),
            "todos_os_casos_rodaram": not erros}
    resumo = {"data": datetime.date.today().isoformat(), "stt": a.stt, "modelo": a.modelo, "prompt": scribe.PROMPT_VERSION,
              "voz": a.voz, "duvida_cobre_erros": round(tot("duvida_pega_erro") / max(1, tot("tok_errados")), 3),
              "duvida_precisao": round(tot("duvida_pega_erro") / max(1, tot("tok_duvidosos")), 3),
              "geracao_s_media": round(statistics.mean([r["t_gen"] for r in rows if r["t_gen"]]), 1) if any(r["t_gen"] for r in rows) else None,
              "casos": len(rows), "wer_medio": round(statistics.mean(r["wer"] for r in rows), 3),
              "remedios": {k: tot(k) for k in ("rem_certo", "rem_aviso", "rem_sem_aviso", "rem_falta", "rem_inventado")},
              "sinais": f"{tot('vit_certo')}/{tot('vit_total')}", "cid": f"{tot('cid_certo')}/{tot('cid_total')}",
              "fatos": f"{tot('fatos_ok')}/{tot('fatos_total')}", "proibidos": tot("proibidos"),
              "geracao_s_max": round(max(gens), 1) if gens else None, "criterios": crit, "erros": erros,
              "gasto_usd_nesta_rodada": round(SPENT["usd"], 3)}
    os.makedirs(REL, exist_ok=True)
    name = f"{resumo['data']}-{a.voz}-{a.stt}-{a.modelo}" + ("-kw-app" if a.kw == "app" else "") + (f"-d{a.duvida}" if a.duvida else "") + f"-p{scribe.PROMPT_VERSION.split('.')[-1]}"
    json.dump({"resumo": resumo, "casos": rows}, open(os.path.join(REL, name + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    md = [f"# Avaliação da gravação — {resumo['data']} · {a.stt} + {a.modelo} · prompt {scribe.PROMPT_VERSION}", "",
          "| Critério | Passou? |", "|---|---|"] + [f"| {k} | {'sim' if v else '**não**'} |" for k, v in crit.items()]
    md += ["", f"WER médio {resumo['wer_medio']} · remédios {resumo['remedios']} · sinais {resumo['sinais']} · CID {resumo['cid']} · "
               f"fatos {resumo['fatos']} · proibidos {resumo['proibidos']}", ""]
    for r in sorted(rows, key=lambda r: r["id"]):
        md += [f"## {r['id']} ({r['origem']}, {r['segundos']} s, WER {r['wer']})", ""]
        md += [f"- {d}" for d in r["detalhe"]] or ["- sem divergências"]
        md += [f"- ponto para conferir [{p['nivel']}] {p['tipo']}: {p['texto']}" for p in r["pontos"]]
        md += ["", "```", *[f"{k.upper()}: {v}" for k, v in r["texto"].items()], "```", ""]
    md += [f"- ERRO {e}" for e in erros]
    open(os.path.join(REL, name + ".md"), "w", encoding="utf-8").write("\n".join(md))
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


def compare():
    """Tabela das rodadas do dia (uma por transcritor × modelo) em relatorios/comparacao-<data>.md."""
    day = datetime.date.today().isoformat()
    rs = [json.load(open(os.path.join(REL, f), encoding="utf-8"))["resumo"] for f in sorted(os.listdir(REL))
          if f.startswith(day) and f.endswith(".json")]
    rs = [r for r in rs if r.get("voz")]
    if not rs:
        sys.exit("nenhum relatório de hoje")
    head = ("| Voz | Transcritor | Evolução | Prompt | Dose errada sem aviso | Remédio inventado | Remédio faltando | Fatos | Sinais | CID | "
            "WER | Dúvida pega erro | Precisão da dúvida | Geração (média/máx s) | Critérios |")
    lines = [f"# Comparação — {day}", "", head, "|" + "---|" * 15]
    for r in sorted(rs, key=lambda r: (r["voz"], r["stt"], r["modelo"])):
        rm = r["remedios"]; c = r["criterios"]
        lines.append(f"| {r['voz']} | {r['stt']} | {r['modelo']} | {r['prompt']} | {rm['rem_sem_aviso']} | {rm['rem_inventado']} | {rm['rem_falta']} | "
                     f"{r['fatos']} | {r['sinais']} | {r['cid']} | {r['wer_medio']} | {r.get('duvida_cobre_erros')} | "
                     f"{r.get('duvida_precisao')} | {r.get('geracao_s_media')}/{r.get('geracao_s_max')} | "
                     f"{sum(bool(v) for v in c.values())}/{len(c)} |")
    out = os.path.join(REL, f"comparacao-{day}.md")
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
