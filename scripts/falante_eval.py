"""Avaliação de quem fala em cada fala (app/falante.py, docs/falante-contrato.md) com as consultas FICTÍCIAS de
evals/scribe/casos/*.yaml. GASTA CRÉDITO (aprovado pelo usuário até ~US$ 2); o --dry-run não chama nada.

Sem áudio e sem transcrição: cada caso tem as falas de referência ([quem, texto], quem em m/p/a). O script junta as
falas em trechos de 15–30 s como o navegador cortaria (corte no silêncio entre falas depois de 15 s; fala longa que
passaria de 30 s é cortada no fim de uma frase), junta o texto de cada trecho SEM rótulo, como o transcritor
devolveria, e rotula com o mesmo caminho da produção (falante.preparar → modelo → falante.ler → falante.montar, com o
fim do trecho anterior já rotulado como contexto). Compara fala a fala com a referência:
- acerto por caractere ponderado (cada caractere, sem espaços, conta com o rótulo da fala em que caiu);
- matriz referência × rotulador (m/p/a e "sem" = trecho que ficou sem rótulo), em caracteres;
- acerto por fala (o rótulo da maioria dos caracteres da fala de referência dentro do trecho).
O custo vem dos tokens que a OpenAI devolve (preços de app/scribe_eval.LLM_M).

    python -m scripts.falante_eval --dry-run              # não chama nada: quantas chamadas e o custo estimado
    python -m scripts.falante_eval [--max-casos 5] [--casos 01,04] [--modelo gpt-5.4-mini] [--teto-usd 2]

Relatório: evals/scribe/relatorios/falante-AAAA-MM-DD.md (e .json ao lado).
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import threading
import time

from app import config, falante, scribe_eval

Q = ("m", "p", "a")
COLS = Q + ("sem",)
SEG_MIN, SEG_MAX = 15.0, 30.0            # os cortes do navegador (docs/gravacao.md)
CHARS_S, PAUSA_S = 14.0, 0.7             # a mesma conta de scribe_eval.estimate: ~14 caracteres por segundo + pausa
# estimativa do --dry-run (o real vem do "usage" de cada resposta): ~3,5 caracteres por token em português; saída
# ~10 tokens por fala; raciocínio "low" do modelo barato, ~250 tokens por chamada (conferir no relatório real)
CHARS_TOKEN, SAIDA_FRASE, RACIOCINIO = 3.5, 10, 250
_LOCK = threading.Lock()
GASTO = {"usd": 0.0}


def unidades(caso):
    """As frases de cada fala de referência: [(fala_idx, quem, texto, segundos)] em ordem."""
    out = []
    for k, (quem, texto) in enumerate(caso["falas"]):
        texto = str(texto).strip()
        if quem not in Q or not texto:
            continue
        for f in falante.frases(texto):
            t = f.strip()
            if t:
                out.append((k, quem, t, len(t) / CHARS_S))
        if out and out[-1][0] == k:
            out[-1] = out[-1][:3] + (out[-1][3] + PAUSA_S,)        # a pausa entre uma fala e a próxima
    return out


def trechos(caso):
    """Os trechos de 15–30 s: [{"at", "dur", "text", "ref": [(ini, fim, quem, fala_idx)]}], texto sem rótulo."""
    us, out, atual, at = unidades(caso), [], [], 0.0

    def fecha():
        nonlocal atual, at
        if not atual:
            return
        text, ref, pos = "", [], 0
        for k, quem, t, _ in atual:
            if text:
                text += " "
                pos += 1
            ref.append((pos, pos + len(t), quem, k))
            text += t
            pos += len(t)
        dur = sum(u[3] for u in atual)
        out.append({"at": round(at, 1), "dur": round(dur, 1), "text": text, "ref": ref})
        at += dur
        atual = []
    for i, u in enumerate(us):
        if atual and sum(x[3] for x in atual) + u[3] > SEG_MAX:
            fecha()                                   # passaria de 30 s: corta antes (no fim de uma frase)
        atual.append(u)
        fim_da_fala = i + 1 == len(us) or us[i + 1][0] != u[0]
        if fim_da_fala and sum(x[3] for x in atual) >= SEG_MIN:
            fecha()                                   # silêncio entre falas depois de 15 s
    fecha()
    return out


def rotulos_por_caractere(text, falas):
    """O rótulo previsto de cada caractere do texto (None = sem rótulo), achando cada fala em ordem no texto."""
    out, pos = [None] * len(text), 0
    for f in falas or []:
        i = text.find(f["t"], pos)
        if i < 0:
            return [None] * len(text)                 # não deveria acontecer: montar confere o texto
        for j in range(i, i + len(f["t"])):
            out[j] = f["q"]
        pos = i + len(f["t"])
    return out


def comparar(trecho, falas):
    """Matriz em caracteres (sem espaços) e o acerto por fala de referência dentro do trecho."""
    pred, text = rotulos_por_caractere(trecho["text"], falas), trecho["text"]
    matriz = {r: {c: 0 for c in COLS} for r in Q}
    falas_ok = falas_n = 0
    for ini, fim, quem, _ in trecho["ref"]:
        votos = {c: 0 for c in COLS}
        for j in range(ini, fim):
            if text[j].isspace():
                continue
            c = pred[j] or "sem"
            matriz[quem][c] += 1
            votos[c] += 1
        falas_n += 1
        falas_ok += max(votos, key=votos.get) == quem
    return matriz, falas_ok, falas_n


def custo(model, usage):
    return scribe_eval.llm_cost(model, usage or {})


def roda_caso(caso, model, teto):
    """Rotula os trechos do caso em ordem (o contexto é o trecho anterior já rotulado)."""
    nome = (caso.get("paciente") or {}).get("nome") or ""
    prev, linhas = {"text": "", "falas": []}, []
    for n, tr in enumerate(trechos(caso), 1):
        with _LOCK:
            if GASTO["usd"] >= teto:
                linhas.append({"n": n, "erro": "teto", "falas": [], "usage": {}, "t": 0})
                continue
        pedacos, msgs = falante.preparar(tr["text"], nome, prev)
        vaz = scribe_eval.vazamentos(nome, json.dumps(msgs or [], ensure_ascii=False))
        falas, usage, erro, t0 = [], {}, "", time.time()
        if msgs is None:
            erro = "não foi ao modelo"
        else:
            try:
                r = falante.chamar(msgs, model)
                usage = r["usage"]
                cortes = falante.ler(r["raw"], len(pedacos))
                falas = (falante.montar(tr["text"], pedacos, cortes, tr["at"], tr["dur"]) if cortes else None) or []
                erro = "" if falas else "resposta recusada"
            except Exception as e:  # noqa: BLE001 — um trecho com erro conta como sem rótulo
                erro = type(e).__name__
        t = round(time.time() - t0, 2)
        if t > falante.TIMEOUT_S and not erro:
            erro = "passou de 8 s"                    # na produção o servidor teria cortado: fica sem rótulo
            falas = []
        with _LOCK:
            GASTO["usd"] += custo(model, usage)
        matriz, ok, nf = comparar(tr, falas)
        linhas.append({"n": n, "at": tr["at"], "dur": tr["dur"], "frases": len(pedacos), "falas": falas, "usage": usage,
                       "t": t, "erro": erro, "matriz": matriz, "falas_ok": ok, "falas_n": nf, "vazamentos": vaz})
        prev = {"text": tr["text"], "falas": falas}
    return {"id": caso["id"], "titulo": caso.get("titulo", ""), "trechos": linhas}


def soma_matriz(ms):
    out = {r: {c: 0 for c in COLS} for r in Q}
    for m in ms:
        for r in Q:
            for c in COLS:
                out[r][c] += m[r][c]
    return out


def acerto(m):
    tot = sum(sum(v.values()) for v in m.values())
    return sum(m[q][q] for q in Q) / tot if tot else 0.0


def estimativa(cases, model):
    """Sem chamar nada: as chamadas que faria e o custo estimado (a máscara roda local)."""
    pin, pout = scribe_eval.LLM_M.get(model, (2.5, 15))
    chamadas, tin, tout = 0, 0, 0
    for c in cases:
        nome = (c.get("paciente") or {}).get("nome") or ""
        prev = {"text": "", "falas": []}
        for tr in trechos(c):
            pedacos, msgs = falante.preparar(tr["text"], nome, prev)
            if msgs is None:
                continue
            chamadas += 1
            tin += sum(len(m["content"]) for m in msgs) / CHARS_TOKEN
            tout += SAIDA_FRASE * len(pedacos) + RACIOCINIO
            # contexto: na rodada real é o trecho anterior rotulado; aqui, a referência (o tamanho é parecido)
            prev = {"text": tr["text"], "falas": [{"q": q, "t": tr["text"][a:b]} for a, b, q, _ in tr["ref"]]}
    return chamadas, int(tin), int(tout), (tin * pin + tout * pout) / 1e6


def relatorio(res, model, t_total):
    hoje = datetime.date.today().isoformat()
    todas = [tr for c in res for tr in c["trechos"] if "matriz" in tr]
    m = soma_matriz([tr["matriz"] for tr in todas])
    usd = sum(custo(model, tr["usage"]) for c in res for tr in c["trechos"])
    tin = sum((tr["usage"] or {}).get("prompt_tokens", 0) for c in res for tr in c["trechos"])
    tout = sum((tr["usage"] or {}).get("completion_tokens", 0) for c in res for tr in c["trechos"])
    tr_ok = sum(1 for tr in todas if tr["falas"])
    fok, fn = sum(tr["falas_ok"] for tr in todas), sum(tr["falas_n"] for tr in todas)
    tempos = sorted(tr["t"] for tr in todas if tr.get("t"))
    p50 = tempos[len(tempos) // 2] if tempos else 0
    p95 = tempos[min(len(tempos) - 1, int(len(tempos) * 0.95))] if tempos else 0
    erros = {}
    for tr in todas:
        if tr["erro"]:
            erros[tr["erro"]] = erros.get(tr["erro"], 0) + 1
    vaz = sorted({v for tr in todas for v in tr.get("vazamentos") or []})
    md = [f"# Quem fala em cada fala ({hoje}, {model}, prompt {falante.PROMPT_VERSION})", "",
          f"{len(res)} casos · {len(todas)} trechos de 15–30 s montados das falas de referência (sem transcrição) · "
          f"{t_total:.0f} s no total.", "",
          f"- **Acerto por caractere (ponderado): {acerto(m):.1%}**",
          f"- Acerto por fala (rótulo da maioria dos caracteres): {fok}/{fn} ({(fok / fn if fn else 0):.1%})",
          f"- Trechos com rótulo: {tr_ok}/{len(todas)}" + (f" · sem rótulo: " + ", ".join(f"{k} {v}" for k, v in sorted(erros.items())) if erros else ""),
          f"- Tempo por chamada: mediana {p50:.1f} s, p95 {p95:.1f} s (teto da produção: {falante.TIMEOUT_S} s)",
          f"- Custo: US$ {usd:.3f} ({tin} tokens de entrada, {tout} de saída, com o raciocínio)"
          + (f" · US$ {usd / len(todas):.4f} por trecho" if todas else ""),
          f"- Nome do paciente no que foi ao modelo: {', '.join(vaz) if vaz else 'nenhum'}", "",
          "## Matriz (caracteres; linha = referência, coluna = rotulador)", "",
          "| referência | médico | paciente | acompanhante | sem rótulo | acerto |", "|---|---|---|---|---|---|"]
    for q, nome in zip(Q, ("médico", "paciente", "acompanhante")):
        tot = sum(m[q].values())
        md.append(f"| {nome} | " + " | ".join(str(m[q][c]) for c in COLS) + f" | {(m[q][q] / tot if tot else 0):.1%} |")
    md += ["", "## Por caso", "", "| caso | trechos | com rótulo | acerto (caracteres) | falas certas | US$ |", "|---|---|---|---|---|---|"]
    for c in res:
        ts = [tr for tr in c["trechos"] if "matriz" in tr]
        mc = soma_matriz([tr["matriz"] for tr in ts])
        fo, fnn = sum(tr["falas_ok"] for tr in ts), sum(tr["falas_n"] for tr in ts)
        md.append(f"| {c['id']} | {len(ts)} | {sum(1 for tr in ts if tr['falas'])} | {acerto(mc):.1%} | {fo}/{fnn} | "
                  f"{sum(custo(model, tr['usage']) for tr in c['trechos']):.4f} |")
    md += ["", "Casos fictícios; a referência é o falante de cada fala do caso. A evolução continua lendo o texto sem "
           "rótulo: usar os rótulos nela só se este acerto for suficiente (docs/falante-contrato.md)."]
    os.makedirs(scribe_eval.REL, exist_ok=True)
    base = os.path.join(scribe_eval.REL, f"falante-{hoje}")
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"modelo": model, "prompt": falante.PROMPT_VERSION, "casos": res}, f, ensure_ascii=False, indent=1)
    return base + ".md", "\n".join(md)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Avaliação de quem fala (gasta crédito; --dry-run não chama nada)")
    ap.add_argument("--modelo", default=config.OPENAI_FALANTE_MODEL)
    ap.add_argument("--casos", default="", help="prefixos dos casos, separados por vírgula (ex.: 01,04)")
    ap.add_argument("--max-casos", type=int, default=0, help="no máximo este número de casos (0 = todos)")
    ap.add_argument("--dry-run", action="store_true", help="não chama nada: mostra as chamadas e o custo estimado")
    ap.add_argument("--teto-usd", type=float, default=2.0, help="para de chamar ao atingir este gasto")
    ap.add_argument("--paralelo", type=int, default=4, help="casos ao mesmo tempo (os trechos de um caso vão em ordem)")
    a = ap.parse_args(argv)
    cases = scribe_eval.load_cases([x.strip() for x in a.casos.split(",") if x.strip()])
    if a.max_casos > 0:
        cases = cases[:a.max_casos]
    n, tin, tout, usd = estimativa(cases, a.modelo)
    ntr = sum(len(trechos(c)) for c in cases)
    print(f"{len(cases)} casos · {ntr} trechos de 15–30 s · {n} chamadas ao {a.modelo}")
    print(f"estimativa: ~{tin} tokens de entrada + ~{tout} de saída (com ~{RACIOCINIO} de raciocínio por chamada) "
          f"= US$ {usd:.3f} (teto US$ {a.teto_usd:.2f})")
    if a.dry_run:
        print("dry-run: nada foi chamado")
        return 0
    if not config.OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY ausente")
    if usd > a.teto_usd:
        sys.exit(f"a estimativa (US$ {usd:.2f}) passa do teto (US$ {a.teto_usd:.2f}): use --max-casos ou --teto-usd")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max(1, a.paralelo)) as ex:
        res = list(ex.map(lambda c: roda_caso(c, a.modelo, a.teto_usd), cases))
    path, md = relatorio(res, a.modelo, time.time() - t0)
    print(md)
    print(f"\nrelatório: {path} · gasto US$ {GASTO['usd']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
