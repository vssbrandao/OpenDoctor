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


# ===== áudio sintético (vozes do Mac) =====
def _say(text, voice, rate):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "f.wav")
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", p, "--file-format=WAVE",
                        "--data-format=LEI16@16000", text], check=True)
        with wave.open(p) as w:
            return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def synth(caso):
    """Monta a consulta: falas com pausas de 0,3–1,1 s, quem está longe do microfone mais baixo, ruído de fundo."""
    rng = np.random.default_rng(int(hashlib.sha1(caso["id"].encode()).hexdigest()[:8], 16))
    vozes = caso.get("vozes") or {}
    longe = set(caso.get("longe_do_microfone") or ["p", "a"])
    parts = [np.zeros(int(SR * 0.6), np.float32)]
    for quem, fala in caso["falas"]:
        v = vozes.get(quem) or {"m": "Luciana", "p": "Flo", "a": "Reed"}.get(quem, "Luciana")
        x = _say(fala, v, int(caso.get("ritmo", 180)))
        if quem in longe:
            x = x * 0.55
        parts += [x, np.zeros(int(SR * rng.uniform(0.3, 1.1)), np.float32)]
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


def audio_of(caso):
    """(áudio, origem). Gravação encenada tem prioridade sobre a voz sintética."""
    for ext in ("m4a", "wav", "webm", "mp3", "aiff"):
        p = os.path.join(GRAV, f"{caso['id']}.{ext}")
        if os.path.exists(p):
            return _read_any(p), "encenada"
    os.makedirs(AUDIO, exist_ok=True)
    p = os.path.join(AUDIO, f"{caso['id']}.wav")
    if not os.path.exists(p):
        _write_wav(p, synth(caso))
    with wave.open(p) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768, "sintética"


def _write_wav(path_or_buf, a):
    w = wave.open(path_or_buf, "wb")
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    w.close()


def wav_bytes(a):
    b = io.BytesIO(); _write_wav(b, a); return b.getvalue()


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
    r, h = _words(ref), _words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def _nums(t):
    return sorted(round(x, 3) for x in scribe.numbers(t))


def _has(alts, text):
    return any(scribe.norm(a) in text for a in alts.split("|"))


def score(caso, res, flags):
    g = caso.get("gabarito") or {}
    full = scribe.norm(" ".join(scribe.render_text(res).values()) + " " +
                       " ".join(f"{m['nome']} {m['dose']} {m['posologia']}" for m in res["meds"]))
    s = {"rem_certo": 0, "rem_aviso": 0, "rem_sem_aviso": 0, "rem_falta": 0, "rem_inventado": 0, "detalhe": []}
    usados = set()
    for gm in g.get("remedios") or []:
        alts = str(gm["nome"]).split("|")                 # "vitamina d|colecalciferol": qualquer um
        hit = next((i for i, m in enumerate(res["meds"]) if i not in usados
                    and any(scribe._near(x, scribe.norm(m["nome"])) for x in alts)), None)
        if hit is None:
            s["rem_falta"] += 1; s["detalhe"].append(f"faltou: {gm['nome']}"); continue
        usados.add(hit); m = res["meds"][hit]
        def same(k):          # "*": qualquer (ex.: mantido sem dose dita); números do gabarito contidos na saída
            if str(gm.get(k, "")) == "*":
                return True
            want, got = _nums(str(gm.get(k, ""))), _nums(m[k])
            return all(want.count(x) <= got.count(x) for x in set(want)) and (bool(want) or not got)
        ok = same("dose") and same("posologia") and gm.get("acao", "*") in ("*", m["acao"])
        if ok:
            s["rem_certo"] += 1; continue
        avisou = any(scribe.norm(m["nome"]).split()[0] in scribe.norm(f["texto"]) for f in flags)
        s["rem_aviso" if avisou else "rem_sem_aviso"] += 1
        s["detalhe"].append(f"{'avisado' if avisou else 'SEM AVISO'}: {gm['nome']} esperado {gm.get('dose','')} {gm.get('posologia','')} "
                            f"{gm.get('acao','')} / saiu {m['dose']} {m['posologia']} {m['acao']}")
    cad = scribe.norm((caso.get("paciente") or {}).get("medicacoes", ""))
    for i, m in enumerate(res["meds"]):        # citado só para recusar/explicar (sem ação) não conta como inventado
        if i not in usados and m["acao"] in ("iniciado", "mantido", "ajustado") and not scribe._near(m["nome"], cad):
            s["rem_inventado"] += 1; s["detalhe"].append(f"inventado: {m['nome']}")
    gv = {k: float(str(v).replace(",", ".")) for k, v in (g.get("sinais") or {}).items()}
    ov = {k: float(v.replace(",", ".")) for k, v in res["vitals"].items()}
    s["vit_certo"] = sum(1 for k, v in gv.items() if k in ov and abs(ov[k] - v) < 1e-6)
    s["vit_total"] = len(gv)
    s["vit_inventado"] = sum(1 for k in ov if k not in gv)
    s["detalhe"] += [f"sinal {k}: esperado {gv[k]} / saiu {ov.get(k)}" for k in gv if not (k in ov and abs(ov[k] - gv[k]) < 1e-6)]
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
    s["proibidos"] = len(proib)
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
    segs, prev, t0 = [], "", time.time()
    akey = hashlib.sha1(a.tobytes()).hexdigest()[:16]
    for i, (s0, s1) in enumerate(cuts(a), 1):
        r, _ = _cache("stt", f"{caso['id']}|{akey}|{i}|{stt_model}|{prev[-300:]}",
                      lambda: stt.transcribe(wav_bytes(a[s0:s1]), "audio/wav", prompt=prev, keywords=kw, model=stt_model))
        segs.append({"seq": i, "at": s0 / SR, "text": r["text"]}); prev = r["text"]
    t_stt = time.time() - t0
    masked = [dict(x, text=scribe.mask(x["text"], pac.get("nome", ""))) for x in segs]
    patient = {"problems": pac.get("problemas", ""), "medications": pac.get("medicacoes", ""), "allergies": pac.get("alergias", "")}
    mode = caso.get("modo", "soap")
    t1 = time.time()
    msgs = scribe.build_messages(masked, mode, patient, caso.get("perfil", ""), "")
    raw, cached = _cache("gen", f"{caso['id']}|{akey}|{stt_model}|{llm_model}|{scribe.PROMPT_VERSION}|{json.dumps(msgs, ensure_ascii=False)}",
                         lambda: scribe.llm.chat(msgs, temperature=0, max_tokens=6000, model=llm_model, json_mode=True,
                                                 reasoning=config.REASONING_EFFORT))
    t_gen = None if cached else time.time() - t1
    res, flags = scribe.check(json.loads(raw), masked, mode, patient)
    ref = " ".join(f for _, f in caso["falas"])
    sc = score(caso, res, flags)
    leak = scribe.norm(pac.get("nome", "")).split()[:1]
    sc["nome_vazou"] = bool(leak) and any(leak[0] in scribe.norm(m["content"]) for m in msgs[1:])
    return {"id": caso["id"], "origem": origem, "segundos": round(len(a) / SR, 1), "trechos": len(segs),
            "wer": round(wer(ref, " ".join(x["text"] for x in segs)), 3), "t_stt": round(t_stt, 1), "t_gen": t_gen,
            "in_chars": sum(len(m["content"]) for m in msgs), "out_chars": len(raw), **sc,
            "texto": scribe.render_text(res), "pontos": flags}


def estimate(cases, stt_model, llm_model):
    sec = sum(len(audio_of(c)[0]) / SR for c in cases)
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
    a = ap.parse_args()
    cases = load_cases([x.strip() for x in a.casos.split(",") if x.strip()])
    sec, su, lu = estimate(cases, a.stt, a.modelo)
    print(f"{len(cases)} casos · {sec / 60:.1f} min de áudio · estimativa US$ {su:.2f} (transcrição) + US$ {lu:.2f} (evolução)")
    if a.estimar:
        return
    if not config.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY ausente")
    rows = []
    for c in cases:
        r = run_case(c, a.stt, a.modelo); rows.append(r)
        print(f"{r['id']:34s} {r['origem']:9s} WER {r['wer']:.2f} · remédios {r['rem_certo']}✓ {r['rem_aviso']}⚠ "
              f"{r['rem_sem_aviso']}✗ falta {r['rem_falta']} inv {r['rem_inventado']} · sinais {r['vit_certo']}/{r['vit_total']} · "
              f"fatos {r['fatos_ok']}/{r['fatos_total']} · proibidos {r['proibidos']}")
    tot = lambda k: sum(r[k] for r in rows)
    gens = [r["t_gen"] for r in rows if r["t_gen"] is not None]
    crit = {"2_dose_errada_sem_aviso": tot("rem_sem_aviso") == 0,
            "3_nada_inventado": tot("rem_inventado") + tot("proibidos") + tot("vit_inventado") == 0,
            "4_cobertura_95": tot("fatos_ok") >= 0.95 * max(1, tot("fatos_total")),
            "nome_nao_vazou": not any(r["nome_vazou"] for r in rows)}
    resumo = {"data": datetime.date.today().isoformat(), "stt": a.stt, "modelo": a.modelo, "prompt": scribe.PROMPT_VERSION,
              "casos": len(rows), "wer_medio": round(statistics.mean(r["wer"] for r in rows), 3),
              "remedios": {k: tot(k) for k in ("rem_certo", "rem_aviso", "rem_sem_aviso", "rem_falta", "rem_inventado")},
              "sinais": f"{tot('vit_certo')}/{tot('vit_total')}", "cid": f"{tot('cid_certo')}/{tot('cid_total')}",
              "fatos": f"{tot('fatos_ok')}/{tot('fatos_total')}", "proibidos": tot("proibidos"),
              "geracao_s_max": round(max(gens), 1) if gens else None, "criterios": crit}
    os.makedirs(REL, exist_ok=True)
    name = f"{resumo['data']}-{a.stt}-{a.modelo}"
    json.dump({"resumo": resumo, "casos": rows}, open(os.path.join(REL, name + ".json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
