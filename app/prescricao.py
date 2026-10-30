"""Possíveis prescrições (aba Prescrições): a partir do perfil da paciente, o modelo propõe manter, ajustar, iniciar ou
suspender cada remédio, com o artigo da base do assistente que sustenta a sugestão. Antes de mostrar, conferências sem
IA: fonte obrigatória para mudar algo, remédio conhecido, alergia do cadastro (inclusive família e marca) e dose fora da
faixa usual — as mesmas tabelas da gravação (app/scribe.py).

O nome da paciente nunca vai ao modelo: o perfil leva só idade, sexo, problemas, remédios, alergias e os últimos sinais e
exames (e ainda passa por scribe.mask). É apoio à decisão: nada entra na receita sem o clique do médico.
"""
import collections
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import threading
import time

from . import config, llm, scribe, search

PROMPT_VERSION = "2026-10-17.1"
with open(os.path.join(scribe._DATA, "prescricao_prompt.txt"), encoding="utf-8") as _arq:
    SYSTEM = _arq.read().strip()
ACOES = ("manter", "ajustar", "iniciar", "suspender")
MAX_FONTES, MAX_NOVOS = 12, 2     # possíveis prescrições: só remédios novos para a paciente, no máximo 2
MIN_SIM = 0.35            # trecho menos parecido com a pergunta fica de fora (o ajuste renal trazia cálculo renal, anticoagulante…)

_VIT = (("pa", "PA", "mmHg"), ("fc", "FC", "bpm"), ("peso", "peso", "kg"), ("imc", "IMC", "kg/m²"), ("glicemia", "glicemia", "mg/dL"),
        ("spo2", "SpO₂", "%"), ("temp", "temperatura", "°C"))
_LAB = (("hba1c", "HbA1c", "%"), ("ldl", "LDL", "mg/dL"), ("hdl", "HDL", "mg/dL"), ("tg", "triglicerídeos", "mg/dL"),
        ("ct", "colesterol total", "mg/dL"), ("creat", "creatinina", "mg/dL"), ("rac", "albuminúria (RAC)", "mg/g"),
        ("pot", "potássio", "mEq/L"), ("sod", "sódio", "mEq/L"), ("au", "ácido úrico", "mg/dL"), ("tsh", "TSH", "mUI/L"),
        ("hb", "hemoglobina", "g/dL"), ("alt", "TGP", "U/L"))
# termos em inglês para a busca por palavra (o corpus é inglês; a busca vetorial já entende o português)
_EN = (("hipertens", "hypertension antihypertensive treatment"), ("diabet", "type 2 diabetes glucose-lowering therapy"),
       ("obes", "obesity pharmacotherapy weight"), ("dislipid|colesterol", "dyslipidemia statin LDL"),
       ("renal|rim|drc", "chronic kidney disease"), ("insufici.ncia card", "heart failure therapy"),
       ("fibrila", "atrial fibrillation anticoagulation"), ("asma", "asthma inhaled therapy"), ("dpoc", "COPD bronchodilator"),
       ("hipotireo", "hypothyroidism levothyroxine"), ("depress", "depression antidepressant"), ("gota|hiperuric", "gout urate"))


def _num(s):
    try:
        return scribe._f(str(s).strip())
    except (TypeError, ValueError):
        return None


def _fmt(v, dec=1):
    return (f"{v:.{dec}f}".rstrip("0").rstrip(".") if dec else str(round(v))).replace(".", ",")


def _dia(d):
    return d.strftime("%d/%m/%Y") if d else ""


def _quando(n):
    """Data da evolução (consulta da agenda ou atualização)."""
    for k in ("event_start", "updated_at"):
        try:
            return datetime.date.fromisoformat(str(n.get(k) or "")[:10])
        except ValueError:
            pass
    return None


def idade(birth):
    try:
        b = datetime.date.fromisoformat(str(birth or "")[:10])
    except ValueError:
        return None
    t = datetime.date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def tfg(creat, anos, sexo):
    """TFG pela CKD-EPI 2021 (sem raça), em mL/min/1,73 m², como a tela (tfgOf): idade em anos fracionados.
    None sem os três dados ou antes dos 18 anos."""
    if not creat or anos is None or anos < 18 or sexo not in ("F", "M"):
        return None
    k, a = (0.7, -0.241) if sexo == "F" else (0.9, -0.302)
    r = creat / k
    return 142 * min(r, 1) ** a * max(r, 1) ** -1.2 * 0.9938 ** anos * (1.012 if sexo == "F" else 1)


def ultimos(notes):
    """Último valor de cada sinal e exame registrado nas evoluções, com a data: {chave: (valor, data)}."""
    out = {}
    for n in sorted(notes or [], key=lambda n: _quando(n) or datetime.date.min, reverse=True):
        d = n.get("data") if isinstance(n.get("data"), dict) else {}
        quando = _quando(n)
        vit = d.get("vitals") if isinstance(d.get("vitals"), dict) else {}
        s, di = _num(vit.get("pa_s")), _num(vit.get("pa_d"))
        if s and di and "pa" not in out:
            out["pa"] = (f"{_fmt(s, 0)}/{_fmt(di, 0)}", quando)
        for k in ("fc", "peso", "glicemia", "spo2", "temp", "altura"):
            v = _num(vit.get(k))
            if v and k not in out:
                out[k] = (v, quando)
        labs = d.get("labs") if isinstance(d.get("labs"), dict) else {}
        lv = labs.get("v") if isinstance(labs.get("v"), dict) else {}
        try:
            ld = datetime.date.fromisoformat(str(labs.get("date") or "")[:10])
        except ValueError:
            ld = quando
        for k, _, _ in _LAB:
            v = _num(lv.get(k))
            if v is not None and k not in out:
                out[k] = (v, ld)
    if "peso" in out and "altura" in out:
        h = out["altura"][0] / 100 if out["altura"][0] > 3 else out["altura"][0]
        if h:
            out["imc"] = (out["peso"][0] / (h * h), out["peso"][1])
    return out


def perfil(p, notes, usados=()):
    """Texto do perfil para o modelo (sem nome) e os números usados nas conferências. usados: remédios das receitas
    emitidas que não estão em uso (o modelo só sugere remédio que a paciente ainda não usou)."""
    anos, sexo = idade(p.get("birth_date")), p.get("sex") or ""
    u = ultimos(notes)
    linhas = ["Paciente: " + ", ".join(x for x in ({"F": "mulher", "M": "homem"}.get(sexo, ""), f"{anos} anos" if anos is not None else "") if x) + "."]
    for rot, campo in (("Problemas", "problems"), ("Em uso", "medications"), ("Alergias", "allergies")):
        itens = [x.strip() for x in (p.get(campo) or "").split("\n") if x.strip()]
        linhas.append(f"{rot}: " + ("; ".join(itens) if itens else "nenhum registrado") + ".")
    ja = [u for u in dict.fromkeys(_txt(x, 120) for x in usados) if u and not scribe.same_drug(u, p.get("medications") or "")]
    linhas.append("Já usou (receitas anteriores): " + ("; ".join(ja) if ja else "nenhum registrado") + ".")
    sinais = [f"{rot} {v[0] if isinstance(v[0], str) else _fmt(v[0])} {un} ({_dia(v[1])})" for k, rot, un in _VIT for v in [u.get(k)] if v]
    if sinais:
        linhas.append("Últimos sinais: " + "; ".join(sinais) + ".")
    exames = [f"{rot} {_fmt(v[0], 2)} {un} ({_dia(v[1])})" for k, rot, un in _LAB for v in [u.get(k)] if v]
    g = None
    try:
        nasc = datetime.date.fromisoformat(str(p.get("birth_date") or "")[:10])
        if "creat" in u:                                    # idade na data do exame, como a tela
            g = tfg(u["creat"][0], ((u["creat"][1] or datetime.date.today()) - nasc).days / 365.25, sexo)
    except ValueError:
        pass
    if g:
        exames.append(f"TFG {_fmt(g, 0)} mL/min/1,73 m² (CKD-EPI 2021, da creatinina)")
    linhas.append("Últimos exames: " + ("; ".join(exames) if exames else "nenhum registrado") + ".")
    return scribe.mask("\n".join(linhas), p.get("name") or ""), {"tfg": g, "anos": anos}


def fontes(p, tfg_=None):
    """Trechos da base do assistente para os problemas da paciente (tratamento e escolha do remédio) e, com a TFG
    abaixo de 60, para a escolha de remédios na doença renal (o modelo só sugere remédio novo com fonte)."""
    probs = [x.strip() for x in (p.get("problems") or "").split("\n") if x.strip()][:4]
    consultas = [(f"{pr}: tratamento farmacológico, metas e escolha do remédio",
                  next((en for pat, en in _EN if re.search(pat, scribe.norm(pr))), None)) for pr in probs]
    if tfg_ is not None and tfg_ < 60:
        consultas.append((f"escolha e dose de remédios na doença renal crônica com TFG de {round(tfg_)} mL/min",
                          "chronic kidney disease eGFR drug dosing"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:            # as buscas em paralelo (cada uma ~3 s)
        res = list(ex.map(lambda qe: search.search(qe[0], k=3, fts_query=qe[1])["hits"], consultas))
    vistos, out = set(), []
    for hits in res:
        for h in hits:
            if h["chunk_id"] not in vistos and len(out) < MAX_FONTES and (h.get("cosine_sim") or 0) >= MIN_SIM:
                vistos.add(h["chunk_id"])
                out.append(h)
    return [dict(h, rotulo=f"F{i + 1}") for i, h in enumerate(out)]


def build_messages(perfil_txt, fts):
    corpo = "\n\n".join(f"[{h['rotulo']}] {h.get('title') or ''} ({str(h.get('publication_date') or '')[:4]})\n"
                        f"{(h.get('text') or '')[:900]}" for h in fts)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"<perfil>\n{perfil_txt}\n</perfil>\n\n<fontes>\n{corpo or '(nenhuma fonte encontrada)'}\n</fontes>"}]


def ask_model(msgs, model=None):
    """Chamada síncrona (o servidor a roda em outra thread: o Render tem um processo só)."""
    return llm.chat(msgs, temperature=0, max_tokens=3000, model=model or config.OPENAI_PRESC_MODEL, json_mode=True,
                    reasoning=config.REASONING_EFFORT)


# ----- função renal (app/data/ajuste_renal.tsv): só avisa; vale o menor limite que ainda fica acima da TFG -----
_RENAL = sorted(((k, float(v.split("\t")[0]), v.split("\t")[1].strip()) for k, v in scribe._pares("ajuste_renal.tsv")),
                key=lambda r: r[1])
_NAO_INICIAR = re.compile(r"não iniciar|contraindicad|evitar")


def aviso_renal(nome, tfg_):
    if tfg_ is None:
        return ""
    return next((msg for k, lim, msg in _RENAL if tfg_ < lim and scribe.same_drug(k, nome)), "")


def _txt(v, n):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def finish(raw, p, fts, tfg_=None, usados=()):
    """Confere a resposta do modelo: só remédio NOVO ("iniciar"), no máximo 2, cada um com fonte, conhecido, fora do
    que está em uso e do que a paciente já usou, sem alergia e sem contraindicação pela função renal. Dose fora da faixa
    usual e ajuste renal viram aviso. O resto (manter, ajustar, suspender) não entra: os remédios em uso ficam no
    Histórico e no cadastro."""
    try:
        out = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        out = {}
    rot = {h["rotulo"] for h in fts}
    meds_txt, alergias, ja_txt = p.get("medications") or "", p.get("allergies") or "", "\n".join(usados)
    itens, descartados = [], 0
    for m in out.get("itens") if isinstance(out.get("itens"), list) else []:
        if not isinstance(m, dict):
            continue
        nome = _txt(m.get("nome"), 120)
        fs = [f for f in (m.get("fontes") if isinstance(m.get("fontes"), list) else []) if f in rot][:3]
        ren = aviso_renal(nome, tfg_) if nome else ""
        if (m.get("acao") != "iniciar" or not nome or not fs or scribe.same_drug(nome, meds_txt) or (ja_txt and scribe.same_drug(nome, ja_txt))
                or scribe.allergy_hits(nome, alergias) or _NAO_INICIAR.search(ren) or scribe.drug_lookup(nome)[0] != "ok"
                or any(scribe.same_drug(nome, x["nome"]) for x in itens) or len(itens) >= MAX_NOVOS):
            descartados += 1
            continue
        dose = _txt(m.get("dose"), 60)
        odd = scribe.dose_incomum(nome, dose)
        itens.append({"acao": "iniciar", "nome": nome[:1].upper() + nome[1:], "dose": dose, "posologia": _txt(m.get("posologia"), 160),
                      "quantidade": _txt(m.get("quantidade"), 60), "motivo": _txt(m.get("motivo"), 300), "fontes": fs,
                      "alergias": [], "faixa": list(odd[1]) if odd else None, "renal": ren})
    usadas = {f for it in itens for f in it["fontes"]}
    return {"itens": itens, "observacoes": _txt(out.get("observacoes"), 400), "descartados": descartados,
            "fontes": {h["rotulo"]: {"titulo": _txt(h.get("title"), 200), "url": h.get("url") or "",
                                     "ano": str(h.get("publication_date") or "")[:4], "nivel": h.get("evidence") or ""}
                       for h in fts if h["rotulo"] in usadas},
            "prompt": PROMPT_VERSION, "modelo": config.OPENAI_PRESC_MODEL}


# ----- a receita: cada item limpo e conferido (inclusive os digitados à mão) e separado por tipo para emitir -----
# app/data/controlados.tsv (Portaria 344) e antimicrobianos.tsv (RDC 471/2021): só avisam e separam; revisão médica.
_CONTROLE = [(k, *(c.strip() for c in v.split("\t")[:2])) for k, v in scribe._pares("controlados.tsv")]
_ANTIMICROB = scribe._linhas("antimicrobianos.tsv")
TALAO = {"notificacao_a": "Notificação de Receita A (amarela)", "notificacao_b": "Notificação de Receita B (azul)",
         "notificacao_b2": "Notificação de Receita B2 (azul)", "notificacao_c2": "Notificação de Receita de retinoide"}
TIPOS = ("simples", "especial", "antimicrobiano")
VIAS = ("oral", "sublingual", "tópica", "inalatória", "nasal", "oftálmica", "otológica", "vaginal", "retal", "subcutânea",
        "intramuscular", "intravenosa", "transdérmica")
ORIGENS = ("ia", "uso", "manual", "anterior", "gravacao")
MAX_ITENS = 20
# o que sai no papel: o que o médico manda além disso é recusado (erro_itens), nunca cortado
LIMITE = {"nome": 120, "dose": 60, "forma": 80, "posologia": 500, "quantidade": 60}
_CAMPO = {"nome": "o nome", "dose": "a dose", "forma": "a forma", "posologia": "a posologia", "quantidade": "a quantidade"}


def item_limpo(it):
    """Um item da receita só com os campos conhecidos e tamanhos limitados. None sem nome."""
    if not isinstance(it, dict) or not _txt(it.get("nome"), LIMITE["nome"]):
        return None
    return {**{k: _txt(it.get(k), n) for k, n in LIMITE.items()}, "via": it.get("via") if it.get("via") in VIAS else "",
            "continuo": bool(it.get("continuo")), "origem": it.get("origem") if it.get("origem") in ORIGENS else "manual",
            "fonte": _txt(it.get("fonte"), 240), "ia": _txt(it.get("ia"), 60)}


def itens_limpos(itens):
    return [x for x in (item_limpo(i) for i in (itens if isinstance(itens, list) else [])[:MAX_ITENS]) if x]


def erro_itens(itens):
    """Por que os itens do médico não cabem na receita, ou "". O servidor não corta o que sai no papel (a folha
    impressa é a resposta do servidor): recusa e diz o quê, para a tela mostrar ("Não foi possível emitir: …")."""
    its = [i for i in (itens if isinstance(itens, list) else []) if item_limpo(i)]
    if len(its) > MAX_ITENS:
        return f"a receita passou do limite de {MAX_ITENS} remédios (emita os demais em outra receita)"
    for it in its:
        for k, n in LIMITE.items():
            if len(_txt(it.get(k), n + 1)) > n:
                quem = " ".join(x for x in (_txt(it.get("nome"), 60), _txt(it.get("dose"), 60)) if x)
                return f"{_CAMPO[k]} de {quem} passou do limite de {n} caracteres"
    return ""


def orientacoes_limpas(t):
    """As orientações ao paciente (texto livre da receita): linhas sem espaço sobrando, no máximo uma linha em branco
    seguida, até 1000 caracteres."""
    linhas = [re.sub(r"[ \t]+", " ", x).strip() for x in str(t or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()[:1000]


def conferir(itens, alergias, tfg_=None):
    """Avisos de cada item: alergia (família e marca), dose fora da faixa usual, função renal, remédio repetido, nome
    fora da lista conhecida e o tipo de receita: simples, controle especial (2 vias) ou antimicrobiano (2 vias); o que
    pede Notificação de Receita (talão) vem em "talao" e não é emitido pelo app."""
    out = []
    for i, it in enumerate(itens):
        nome = it["nome"]
        ctl = next(((lista, rec) for k, lista, rec in _CONTROLE if scribe.same_drug(k, nome)), None)
        anti = any(scribe.same_drug(k, nome) for k in _ANTIMICROB)
        st, sug = scribe.drug_lookup(nome)
        odd = scribe.dose_incomum(nome, it.get("dose") or "")
        rep = any(scribe.same_drug(nome, o["nome"]) or scribe.same_drug(o["nome"], nome) for j, o in enumerate(itens) if j != i)
        out.append({"alergias": scribe.allergy_hits(nome, alergias), "faixa": list(odd[1]) if odd else None,
                    "renal": aviso_renal(nome, tfg_), "repetido": rep,
                    "nome": "" if st == "ok" else (f"Seria {sug}?" if sug else "Remédio fora da lista conhecida: confira o nome."),
                    "tipo": "especial" if ctl and ctl[1] == "especial" else "antimicrobiano" if anti else "simples",
                    "lista": ctl[0] if ctl else "", "talao": TALAO.get(ctl[1], "") if ctl else ""})
    return out


def mesmo_remedio(a, b):
    """Os dois nomes são o mesmo remédio ("losartana" e "Losartana potássica")?"""
    return scribe.same_drug(a, b) or scribe.same_drug(b, a)


def da_gravacao(meds):
    """Os remédios que a gravação extraiu (scribe: meds com acao) como itens de receita, para revisar: mantido, iniciado
    e ajustado entram (mantido e ajustado como uso contínuo); suspenso não entra."""
    cap = lambda t: str(t or "").strip()[:1].upper() + str(t or "").strip()[1:]  # noqa: E731
    return itens_limpos([{"nome": cap(m.get("nome")), "dose": m.get("dose"), "posologia": m.get("posologia"),
                          "continuo": m.get("acao") in ("mantido", "ajustado"), "origem": "gravacao"}
                         for m in (meds if isinstance(meds, list) else []) if isinstance(m, dict) and m.get("acao") != "suspenso"])


def nomes_remedios():
    """Os nomes de app/data/remedios.txt para sugerir enquanto o médico digita (com a primeira letra maiúscula)."""
    return sorted({x[:1].upper() + x[1:] for x in scribe._linhas("remedios.txt")}, key=scribe.norm)


def grupos(itens, conf):
    """Separa para emitir: simples, controle especial e antimicrobiano, cada um na sua receita (nesta ordem)."""
    g = {}
    for it, c in zip(itens, conf):
        g.setdefault(c["tipo"], []).append(it)
    return [(t, g[t]) for t in TIPOS if t in g]


# ----- guarda o resultado enquanto o perfil não muda: abrir a aba de novo não gasta crédito -----
_CACHE, _LOCK, _TTL, _MAX = collections.OrderedDict(), threading.Lock(), 24 * 3600, 300


def chave(uid, pid, perfil_txt):
    return hashlib.sha256(f"{uid}|{pid}|{PROMPT_VERSION}|{config.OPENAI_PRESC_MODEL}|{perfil_txt}".encode()).hexdigest()


def guardado(k):
    with _LOCK:
        v = _CACHE.get(k)
        if v and time.time() - v[0] < _TTL:
            _CACHE.move_to_end(k)
            return v[1]
        _CACHE.pop(k, None)
    return None


def guardar(k, res):
    with _LOCK:
        _CACHE[k] = (time.time(), res)
        while len(_CACHE) > _MAX:
            _CACHE.popitem(last=False)
