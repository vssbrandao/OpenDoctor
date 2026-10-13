"""CID-10 (DATASUS, versão 2008): busca por código ("I10", "e11.9") ou descrição ("hipertensao").

A tabela vem dos CSVs oficiais do DATASUS (categorias + subcategorias), convertida para
app/data/cid10.json, mais os códigos de COVID-19 que a OMS criou depois de 2008. Fica em
memória (≈14 mil códigos) e é filtrada sem acento, por começo de palavra, aceitando siglas e
termos do dia a dia ("HAS", "DM2", "diabetes tipo 2").
"""
import functools
import json
import os
import re
import unicodedata

_PATH = os.path.join(os.path.dirname(__file__), "data", "cid10.json")
_CODE_Q = re.compile(r"[a-z]\d{0,3}x?")
_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")   # mantém compostos ("nao-insulino-dependente")

# códigos criados pela OMS depois da versão 2008 do DATASUS (usados no Brasil desde 2020)
_EXTRA = [
    ("U07.1", "COVID-19, vírus identificado"),
    ("U07.2", "COVID-19, vírus não identificado (diagnóstico clínico ou epidemiológico)"),
    ("U09.9", "Condição pós-COVID-19, não especificada"),
    ("U10.9", "Síndrome inflamatória multissistêmica associada à COVID-19, não especificada"),
]

# siglas e termos do dia a dia → palavras da descrição oficial (já sem acento)
_SYN_PHRASES = [("tipo 2", "nao-insulino-dependente"), ("tipo ii", "nao-insulino-dependente"),
                ("tipo 1", "insulino-dependente"), ("tipo i", "insulino-dependente")]
_SYN_WORDS = {
    "has": "hipertensao essencial", "hipertensao arterial": "hipertensao essencial",
    "dm": "diabetes mellitus", "dm2": "diabetes mellitus nao-insulino-dependente",
    "dm1": "diabetes mellitus insulino-dependente", "iam": "infarto agudo do miocardio",
    "avc": "acidente vascular cerebral", "ave": "acidente vascular cerebral",
    "dpoc": "doenca pulmonar obstrutiva cronica", "itu": "infeccao do trato urinario",
    "ivas": "infeccao aguda das vias aereas superiores", "icc": "insuficiencia cardiaca",
    "ic": "insuficiencia cardiaca", "drge": "refluxo gastro-esofagico", "tep": "embolia pulmonar",
    "tvp": "trombose venosa profunda", "irc": "insuficiencia renal cronica", "drc": "doenca renal cronica",
    "tag": "ansiedade generalizada", "tdah": "transtornos hipercineticos", "covid": "covid-19",
}


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).casefold().split())


def _words(s, parts=True):
    """Palavras do texto. Compostos com hífen entram inteiros e (se parts) também em partes, para
    que "insulino" ache "nao-insulino-dependente" mas "insulino-dependente" não ache o tipo 2."""
    out = []
    for w in _WORD.findall(s):
        out.append(w)
        if parts and "-" in w:
            out.extend(w.split("-"))
    return out


@functools.lru_cache(maxsize=1)
def _table():
    with open(_PATH, encoding="utf-8") as f:
        items = [tuple(x) for x in json.load(f)["items"]] + _EXTRA
    return [(code, desc, _norm(code).replace(".", ""), _words(_norm(desc)), _norm(desc))
            for code, desc in sorted(items)]


def _expand(qn):
    """Troca siglas/termos comuns pelas palavras da descrição oficial."""
    for a, b in _SYN_PHRASES:
        qn = re.sub(r"\b" + re.escape(a) + r"\b", b, qn)
    for a in sorted(_SYN_WORDS, key=len, reverse=True):
        qn = re.sub(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", _SYN_WORDS[a], qn)
    return qn


def search(q, limit=20):
    """Até `limit` códigos: primeiro os que começam com o código digitado; senão, os que têm
    todas as palavras na descrição (categorias e descrições que começam com a 1ª palavra antes)."""
    qn = _norm(q)[:80]
    if not qn:
        return []
    qcode = qn.replace(".", "").replace(" ", "")
    words = _words(_expand(qn), parts=False)
    is_code = bool(_CODE_Q.fullmatch(qcode))
    hits = []
    for code, desc, ncode, dwords, ndesc in _table():
        if is_code and ncode.startswith(qcode):
            score = (0, len(ncode), ncode)
        elif words and all(any(d.startswith(w) for d in dwords) for w in words):   # começo de palavra
            score = (1 if dwords and dwords[0].startswith(words[0]) else 2, len(ncode), ncode)
        else:
            continue
        hits.append((score, code, desc))
    hits.sort()
    return [{"code": c, "desc": d} for _, c, d in hits[:limit]]


def get(code):
    """Descrição oficial de um código (ou None)."""
    k = _norm(code).replace(".", "")
    for c, d, nc, _, _ in _table():
        if nc == k:
            return d
    return None
