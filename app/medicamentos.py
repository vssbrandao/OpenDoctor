"""Busca na base de medicamentos da receita (app/data/medicamentos.tsv.gz, gerada da Lista de Preços CMED/Anvisa por
scripts/cmed_medicamentos.py) para a barra "Adicionar remédio…" da aba Prescrições.

O médico escolhe a SUBSTÂNCIA (todas as apresentações dela, de qualquer laboratório) ou uma MARCA. Na receita, a marca
vai como "Marca (substância)" (decisão do usuário). Cada resultado traz as apresentações: dose, forma e as quantidades
de embalagem (para sugerir dose e quantidade na linha do item).
"""
import gzip
import os
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
                        ap = g["aps"].setdefault((r["dose"], r["forma"] or r["apresentacao"]), set())
                        if r["quantidade"]:
                            ap.add(r["quantidade"])
        for g in list(subs.values()) + list(marcas.values()):
            g["busca"] = scribe.norm(g["marca"] + " " + g["substancia"])
        _BASE = (list(subs.values()), list(marcas.values()))
        return _BASE


def _qtd_ordem(q):
    n = q.split(" ")[0]
    return (0, int(n)) if n.isdigit() else (1, q)


def _saida(g):
    marca = g["marca"]
    aps = [{"dose": d, "forma": f, "quantidades": sorted(qs, key=_qtd_ordem)}
           for (d, f), qs in sorted(g["aps"].items(), key=lambda kv: (kv[0][1], _dose_ordem(kv[0][0])))]
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
    """Substâncias e marcas que batem com todas as palavras de q (ao menos 2 letras). Primeiro o que começa com o
    termo; a substância antes das marcas dela; as comercializadas no último ano antes."""
    termos = scribe.norm(q or "").split()
    if not termos or len(" ".join(termos)) < 2:
        return []
    subs, marcas = _carrega()
    acha = [g for g in subs + marcas if all(t in g["busca"] for t in termos)]

    def ordem(g):
        alvo = scribe.norm(g["marca"] or g["substancia"])
        return (not alvo.startswith(termos[0]), not any(w.startswith(termos[0]) for w in alvo.split()), not g["com"],
                bool(g["marca"]), alvo)
    return [_saida(g) for g in sorted(acha, key=ordem)[:limite]]
