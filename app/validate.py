"""Validação determinística por frase (spec §6.1). Funções puras, testáveis.

Checagens aplicadas a cada frase já fechada, ANTES de enviá-la ao cliente:
 1. Frase com conteúdo clínico (dose/número com unidade ou fármaco) precisa de ≥1 citação [n].
 2. Todo [n] citado deve estar no conjunto de trechos enviados ao LLM.
 3. Todo número-com-unidade e todo fármaco da frase deve aparecer nos TRECHOS CITADOS.

Sem 2ª chamada ao LLM. Em caso de falha, o servidor interrompe e mostra só o validado.
"""
import re

# unidades de dose / estatística reconhecidas
_UNIT = (r"mg/kg/dia|mg/kg|mcg/kg|mg/dia|mg/dL|mmol/L|mmHg|mcg|µg|ng|mg|kg|"
         r"UI|mL|ml|L|%|anos?")
_NUM = r"\d+(?:[.,]\d+)?"
_DOSE_RE = re.compile(rf"({_NUM})\s*({_UNIT})(?![A-Za-zÀ-ÿ])", re.IGNORECASE)
_NUM_RE = re.compile(_NUM)
_CITE_RE = re.compile(r"\[(\d+)\]")

# sufixos (stems INN) para detectar fármacos de forma conservadora
_DRUG_SUFFIXES = (
    "gliflozina", "gliflozin", "gliptina", "gliptin", "sartana", "sartan",
    "statina", "statin", "vastatina", "vastatin", "parina", "parin",
    "floxacino", "floxacina", "prazol", "ciclina", "cilina", "cillin",
    "olol", "pril", "mab", "nibe", "nib",
)
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-]{4,}")


def citations(sentence):
    return set(int(n) for n in _CITE_RE.findall(sentence))


def dose_tokens(sentence):
    """Retorna lista de (numero, unidade) achados na frase."""
    return [(m.group(1), m.group(2)) for m in _DOSE_RE.finditer(sentence)]


def drug_mentions(sentence):
    out = []
    for m in _WORD_RE.finditer(sentence):
        w = m.group(0)
        wl = w.lower()
        for suf in _DRUG_SUFFIXES:
            if wl.endswith(suf) and len(wl) >= (7 if len(suf) <= 4 else 6):
                out.append(w)
                break
    return out


def _norm(s):
    return s.lower().replace(",", ".")


def _number_in(num, text):
    return _norm(num) in _norm(text)


def is_clinical(sentence):
    return bool(dose_tokens(sentence) or drug_mentions(sentence))


def validate_sentence(sentence, allowed_ns, text_by_n):
    """(ok, reason). text_by_n: {n: texto do trecho}. allowed_ns: conjunto de n válidos."""
    cites = citations(sentence)

    invalid = cites - set(allowed_ns)
    if invalid:
        return False, f"citação inválida {sorted(invalid)} (fora dos trechos enviados)"

    doses = dose_tokens(sentence)
    drugs = drug_mentions(sentence)

    if (doses or drugs) and not cites:
        return False, "frase clínica sem citação [n]"

    cited_text = " ".join(text_by_n.get(n, "") for n in cites)

    for num, unit in doses:
        if not _number_in(num, cited_text):
            return False, f"número '{num} {unit}' não consta nos trechos citados"

    for drug in drugs:
        if drug.lower() not in _norm(cited_text):
            return False, f"fármaco '{drug}' não consta nos trechos citados"

    return True, None


# ------- buffer de frases para o streaming -------
_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class SentenceBuffer:
    """Acumula deltas e devolve frases completas (corte em .!? seguido de espaço)."""

    def __init__(self):
        self.buf = ""

    def feed(self, delta):
        self.buf += delta
        out = []
        while True:
            m = _BOUNDARY.search(self.buf)
            if not m:
                break
            out.append(self.buf[:m.start()].strip())
            self.buf = self.buf[m.end():]
        return [s for s in out if s]

    def flush(self):
        s = self.buf.strip()
        self.buf = ""
        return s
