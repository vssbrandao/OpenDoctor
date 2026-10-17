"""Busca na base de medicamentos da receita (app/data/medicamentos.tsv.gz, gerada da Lista de Preços CMED/Anvisa por
scripts/cmed_medicamentos.py) para a barra "Adicionar remédio…" da aba Prescrições.

O médico escolhe a SUBSTÂNCIA (todas as apresentações dela, de qualquer laboratório) ou uma MARCA. Na receita, a marca
vai como "Marca (substância)" (decisão do usuário). Cada resultado traz as apresentações: dose, forma e as quantidades
de embalagem (para sugerir dose e quantidade na linha do item).
"""
import gzip
import os
import re
import threading

from . import scribe

_ARQ = os.path.join(os.path.dirname(__file__), "data", "medicamentos.tsv.gz")
_LOCK = threading.Lock()
_BASE = None
CAMPOS = ("substancia", "marca", "laboratorio", "tipo", "tarja", "comercializado", "dose", "forma", "quantidade", "apresentacao")


def _carrega():
    """Agrupa a base por substância e por marca (uma vez, na primeira busca)."""
    global _BASE
    with _LOCK:
        if _BASE is not None:
            return _BASE
        subs, marcas = {}, {}
        if os.path.exists(_ARQ):
            with gzip.open(_ARQ, "rt", encoding="utf-8") as f:
                for linha in f:
                    if linha.startswith("#") or linha.startswith("substancia\t"):
                        continue
                    r = dict(zip(CAMPOS, linha.rstrip("\n").split("\t")))
                    for chave, grupo in (((r["substancia"], ""), subs), ((r["substancia"], r["marca"]), marcas if r["marca"] else None)):
                        if grupo is None:
                            continue
                        g = grupo.setdefault(chave, {"substancia": r["substancia"], "marca": chave[1], "labs": {}, "tipos": set(),
                                                     "com": False, "aps": {}, "tarja": r["tarja"]})
                        g["labs"][r["laboratorio"]] = 1
                        g["tipos"].add(r["tipo"])
                        g["com"] = g["com"] or r["comercializado"] == "1"
                        ap = g["aps"].setdefault((dose_limpa(r["dose"]), r["forma"] or r["apresentacao"]), set())
                        if r["quantidade"]:
                            ap.add(r["quantidade"])
        for g in list(subs.values()) + list(marcas.values()):
            g["busca"] = scribe.norm(g["marca"] + " " + g["substancia"])
        _BASE = (list(subs.values()), list(marcas.values()))
        return _BASE


_UNID = {"mg": "mg", "g": "g", "mcg": "mcg", "ui": "UI", "u": "U", "ml": "mL", "meq": "mEq", "%": "%"}


def dose_limpa(d):
    """A dose num jeito só, para não repetir a mesma apresentação: '(100,0 + 25,0) mg' → '100 mg + 25 mg',
    '50 mg / ml' → '50 mg/mL', '500 mg pó liof' → '500 mg'. O que não reconhece fica como veio."""
    t = re.sub(r"\s*/\s*", "/", (d or "").strip().lower())
    t = re.sub(r"\b(po|pó)\b.*$", "", t).strip()                        # sobra da forma ("pó liof", "pó p/")
    t = re.sub(r"(\d),0+\b", r"\1", t)                                   # 100,0 → 100
    m = re.fullmatch(r"\(([\d,\s+]+)\)\s*([a-z%/]+)", t) or re.fullmatch(r"([\d,]+(?:\s*\+\s*[\d,]+)+)\s*([a-z%/]+)", t)
    if m:                                                                # (100 + 25) mg, 100 + 25 mg → cada parte com a unidade
        t = " + ".join(f"{n.strip()} {m.group(2)}" for n in m.group(1).split("+"))
    partes = []
    for p in t.split("+"):
        m = re.fullmatch(r"\s*([\d,]+)\s*([a-z%/]+)\s*", p)
        if not m:
            return (d or "").strip()
        partes.append(m.group(1) + " " + "/".join(_UNID.get(u, u) for u in m.group(2).split("/")))
    return " + ".join(partes)


def _bate_dose(dose, t):
    """'50' bate com '50 mg' e '50 mg + 12,5 mg', não com '150 mg'; '500mg' pede a unidade também."""
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([a-z/%]*)", t)
    if not m:
        return t in scribe.norm(dose)
    num, un = m.group(1).replace(".", ","), m.group(2)
    return bool(re.search(r"(?<![\d,])" + re.escape(num) + r"(?![\d,])" + (r"\s*" + re.escape(un) if un else ""), scribe.norm(dose)))


def _qtd_ordem(q):
    n = q.split(" ")[0]
    return (0, int(n)) if n.isdigit() else (1, q)


def _saida(g, doses=()):
    marca = g["marca"]
    aps = [{"dose": d, "forma": f, "quantidades": sorted(qs, key=_qtd_ordem)}
           for (d, f), qs in sorted(g["aps"].items(), key=lambda kv: (kv[0][1], _dose_ordem(kv[0][0])))
           if all(_bate_dose(d, t) for t in doses)]
    return {"tipo": "marca" if marca else "substancia",
            "nome": f"{marca} ({g['substancia'][:1].lower() + g['substancia'][1:]})" if marca else g["substancia"],
            "substancia": g["substancia"], "marca": marca, "laboratorios": list(g["labs"])[:3], "tarja": g["tarja"],
            "generico": "Genérico" in g["tipos"], "apresentacoes": aps[:40]}


def _dose_ordem(d):
    n = d.split(" ")[0].replace(".", "").replace(",", ".")
    try:
        v = float(n)
    except ValueError:
        return (1, 0, d)
    return (0, v * (1000 if " g" in d and "mg" not in d else 1), d)


def buscar(q, limite=12):
    """Substâncias e marcas que batem com todas as palavras de q (ao menos 2 letras). Palavra com número filtra a
    dose ("losartana 50": só as apresentações de 50 mg; o produto sem nenhuma sai). Primeiro o que começa com o termo;
    a substância antes das marcas dela; as comercializadas no último ano antes."""
    palavras = scribe.norm(q or "").split()
    termos = [t for t in palavras if not any(c.isdigit() for c in t)]
    doses = [t for t in palavras if any(c.isdigit() for c in t)]
    if not termos or len(" ".join(termos)) < 2:
        return []
    subs, marcas = _carrega()
    acha = [g for g in subs + marcas if all(t in g["busca"] for t in termos)]

    def ordem(g):
        alvo = scribe.norm(g["marca"] or g["substancia"])
        return (not alvo.startswith(termos[0]), not any(w.startswith(termos[0]) for w in alvo.split()), not g["com"],
                bool(g["marca"]), alvo)
    out = []
    for g in sorted(acha, key=ordem):
        s = _saida(g, doses)
        if s["apresentacoes"]:
            out.append(s)
            if len(out) >= limite:
                break
    return out
