"""Validação determinística por frase (spec §6.1). Funções puras, testáveis.

Aplicadas a cada frase já fechada, ANTES de enviá-la ao cliente:
 1. validate_sentence: todo [n] citado deve existir entre os trechos enviados
    ao LLM (citação a trecho inexistente → frase descartada).
 2. ground_citations: FIDELIDADE da citação — se a frase cita [n] e contém
    número com unidade (dose, %, mg/dL...), esse número precisa aparecer nos
    trechos citados (ou nos dados do próprio médico/cálculo do sistema), com
    tolerância de arredondamento. Se não aparecer, a CITAÇÃO é removida: a
    frase continua, mas deixa de fingir que tem fonte.
Frases clínicas sem citação são permitidas (conhecimento consolidado) e são
contadas como "sem fonte" para transparência.

Sem 2ª chamada ao LLM.
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

    # Única checagem rígida: não citar um trecho que não foi enviado ao LLM.
    # (Ancoragem de números/fármacos foi removida: o assistente pode complementar
    #  com conhecimento consolidado; cortar frases por isso empobrecia a resposta.)
    invalid = cites - set(allowed_ns)
    if invalid:
        return False, f"citação inválida {sorted(invalid)} (fora dos trechos enviados)"

    return True, None


def _to_float(s):
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _supported(num, pool_numbers):
    """O número da frase está no pool (com tolerância de arredondamento)?"""
    x = _to_float(num)
    if x is None:
        return False
    tol = max(0.5, abs(x) * 0.03)
    return any(abs(x - y) <= tol for y in pool_numbers)


def _numbers_in(text):
    out = []
    for m in _NUM_RE.finditer(text or ""):
        v = _to_float(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _percent_forms(pool):
    """Percentuais que o texto pode legitimamente derivar de uma razão (RR/HR/OR):
    'RR 0,68' → redução de 32%, '1,25' → aumento de 25%, '0,68' → 68%."""
    out = []
    for y in pool:
        if 0 < y < 5:
            out += [100 * (1 - y), 100 * (y - 1), 100 * y]
    return out


def ground_citations(sentence, text_by_n, extra_text=""):
    """Remove citações [n] não sustentadas por números da frase.
    Devolve (frase_final, removidas:set). extra_text: dados do médico/cálculo."""
    cites = citations(sentence)
    doses = dose_tokens(sentence)
    if not cites or not doses:
        return sentence, set()
    pool = _numbers_in(" ".join(text_by_n.get(n, "") for n in cites) + " " + (extra_text or ""))
    pct_pool = pool + _percent_forms(pool)
    if all(_supported(num, pct_pool if unit == "%" else pool) for num, unit in doses):
        return sentence, set()
    # número sem respaldo nos trechos citados → tira a atribuição falsa
    out = _CITE_RE.sub("", sentence)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out, cites


def is_ungrounded_claim(sentence):
    """Frase com conteúdo clínico (dose/número/fármaco) e sem nenhuma citação."""
    return is_clinical(sentence) and not citations(sentence)


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
            sent = self.buf[:m.start()].rstrip()
            sep = self.buf[m.start():m.end()]          # separador entre frases
            self.buf = self.buf[m.end():]
            if not sent:
                continue
            # preserva a estrutura do Markdown: quebra de linha → parágrafo
            sent += "\n\n" if "\n" in sep else " "
            out.append(sent)
        return out

    def flush(self):
        s = self.buf.strip()
        self.buf = ""
        return s
