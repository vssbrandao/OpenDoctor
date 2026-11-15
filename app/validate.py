"""Validação determinística por frase (spec §6.1). Funções puras, testáveis.

Aplicadas a cada frase já fechada (ou bloco: tabela, ```plano), ANTES de enviá-la ao cliente:
 1. validate_sentence / strip_invalid: todo [n] citado deve existir entre os trechos
    enviados ao LLM (citação a trecho inexistente → só o [n] sai; o texto fica).
 2. ground_citations (linha a linha): FIDELIDADE da citação — se a frase cita [n] e contém
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


def _drop_cites(text, ns):
    """Tira os [n] de ns (e o espaço antes deles), sem mexer no resto do texto (recuo, tabela, quebras)."""
    if not ns:
        return text
    return re.sub(r"[ \t]*\[(\d+)\]", lambda m: "" if int(m.group(1)) in ns else m.group(0), text)


def strip_invalid(text, allowed_ns):
    """Tira só os [n] fora dos trechos enviados; o texto continua (uma citação errada não derruba a tabela inteira).
    Devolve (texto, removidas:set)."""
    invalid = citations(text) - set(allowed_ns)
    return _drop_cites(text, invalid), invalid


MAX_CITES_JUNTAS = 2
_GRUPO_CITE = re.compile(r"(?:[ \t]*\[\d+\]){2,}")


def thin_citations(text):
    """Menos ruído de citação (a v5 chegava a 61 por resposta, com "[1][2]" em toda célula):
    - um grupo "[1][2][3][4]" fica com as MAX_CITES_JUNTAS primeiras, sem repetir número;
    - numa tabela ou num bloco ``` (o plano), cada [n] fica só na 1ª vez em que aparece no bloco.
    Só tira [n]; o texto não muda. Devolve (texto, quantas_tiradas)."""
    tiradas = 0

    def junta(m):
        nonlocal tiradas
        ns = []
        for n in re.findall(r"\[(\d+)\]", m.group(0)):
            if n not in ns:
                ns.append(n)
        tiradas += len(re.findall(r"\[\d+\]", m.group(0))) - min(len(ns), MAX_CITES_JUNTAS)
        lead = re.match(r"[ \t]*", m.group(0)).group(0)
        return lead + "".join(f"[{n}]" for n in ns[:MAX_CITES_JUNTAS])

    text = _GRUPO_CITE.sub(junta, text)
    linhas = text.splitlines(keepends=True)
    bloco = any(ln.lstrip().startswith(("|", "```", "~~~")) for ln in linhas)
    if bloco:
        vistos, out = set(), []
        for ln in linhas:
            def uma_vez(m):
                nonlocal tiradas
                n = m.group(1)
                if n in vistos:
                    tiradas += 1
                    return ""
                vistos.add(n)
                return m.group(0)
            out.append(re.sub(r"[ \t]*\[(\d+)\]", uma_vez, ln) if ln.lstrip().startswith(("|", "-", "*")) or
                       re.match(r"\s*\d+\.", ln) else ln)
        text = "".join(out)
    return text, tiradas


_BASTIDOR = re.compile(r"(c)[áa]lculo determin[íi]stico(?: do sistema)?", re.I)


def sem_bastidor(text):
    """Termo interno que vazava para o médico ("cálculo determinístico do sistema" → "cálculo")."""
    return _BASTIDOR.sub(lambda m: m.group(1) + "álculo", text)


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


def _ground_line(line, text_by_n, extra_text):
    cites = citations(line)
    doses = dose_tokens(line)
    if not cites or not doses:
        return line, set()
    pool = _numbers_in(" ".join(text_by_n.get(n, "") for n in cites) + " " + (extra_text or ""))
    pct_pool = pool + _percent_forms(pool)
    if all(_supported(num, pct_pool if unit == "%" else pool) for num, unit in doses):
        return line, set()
    # número sem respaldo nos trechos citados → tira a atribuição falsa
    return _drop_cites(line, cites), cites


# linha que começa um bloco próprio (item, título, tabela, cerca, citação): nunca é continuação da anterior
_BLOCK_START = re.compile(r"^(?:\d+[.)]\s|[-*+•]\s|\*\*|#|\||```|~~~|>)")


def _continues(prev, nxt):
    """A linha nxt continua a frase de prev (frase quebrada no meio, ex.: '100 mg\\nao dia [1].')?"""
    p, n = prev.strip(), nxt.strip()
    return bool(p and n) and p[0] not in "|#`~>" and not p.endswith((".", "!", "?", ":")) \
        and not _BLOCK_START.match(n)


def _logical_lines(text):
    """Linhas do bloco, juntando a frase quebrada em duas linhas (a citação na 2ª vale para a dose da 1ª)."""
    out = []
    for line in text.splitlines(keepends=True):
        if out and _continues(out[-1].splitlines()[-1], line):
            out[-1] += line
        else:
            out.append(line)
    return out


def ground_citations(sentence, text_by_n, extra_text=""):
    """Remove citações [n] não sustentadas por números da frase — linha a linha (linha de tabela, item de lista),
    para um número sem respaldo só tirar o [n] da própria linha; a frase quebrada em duas linhas conta como uma.
    Devolve (texto_final, removidas:set). extra_text: dados do médico/cálculo."""
    out, removed = [], set()
    for line in _logical_lines(sentence):
        line, r = _ground_line(line, text_by_n, extra_text)
        out.append(line)
        removed |= r
    return "".join(out), removed


def _own_has_dose(num, unit, own):
    return re.search(rf"(?<![\d.,]){re.escape(num)}\s*{re.escape(unit)}(?![A-Za-zÀ-ÿ])", own, re.IGNORECASE) is not None


def _restates_own(line, own_text):
    """A linha só repete dados do próprio paciente/pergunta (fármacos e doses que o médico já escreveu)?"""
    if not own_text:
        return False
    own = own_text.lower().replace(",", ".")
    ln = line.replace(",", ".")
    if any(m.lower() not in own for m in drug_mentions(ln)):
        return False
    return all(_own_has_dose(num, unit, own) for num, unit in dose_tokens(ln))


def is_ungrounded_claim(sentence, own_text=""):
    """Frase com conteúdo clínico (dose/número/fármaco) e sem nenhuma citação. Não conta a linha que só repete os
    dados/remédios do paciente informados pelo médico (own_text): fármaco ou dose nova continua contando."""
    return is_clinical(sentence) and not citations(sentence) and not _restates_own(sentence, own_text)


def ungrounded_lines(text, own_text=""):
    """Quantas linhas do bloco são afirmação clínica sem fonte (tabela/lista contam linha a linha)."""
    return sum(1 for ln in _logical_lines(text) if is_ungrounded_claim(ln, own_text))


# ------- buffer de frases para o streaming -------
# corte de frase dentro da linha: .!? seguido de espaço/tab (a quebra de linha é tratada à parte)
_BOUNDARY = re.compile(r"(?<=[.!?])[ \t]+")
_LIST_MARK = re.compile(r"^[ \t]*(?:\d+[.)]|[-*+]|#+)[ \t]*")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")


class SentenceBuffer:
    """Acumula deltas e devolve pedaços completos, com o texto EXATO do modelo (espaços e quebras de linha), para o
    Markdown não se desmontar no cliente (que só concatena):
     - linha comum: sai a cada frase (.!? + espaço) ou no fim da linha, com as quebras que vierem depois;
     - item de lista: o marcador ("1.", "-") nunca vira frase sozinho;
     - tabela (linhas com "|") e bloco ``` (ex.: ```plano) saem inteiros, quando terminam."""

    def __init__(self):
        self.buf = ""
        self.pend = ""          # pedaço só de espaços (ex.: linha "   "): vai junto do próximo, o texto não perde nada

    @staticmethod
    def _end_with_breaks(buf, i):
        """i = índice logo após um '\n'. Engole as quebras seguintes; None se ainda não dá para saber onde acabam."""
        j = i
        while j < len(buf) and buf[j] == "\n":
            j += 1
        return j if j < len(buf) else None

    def _take(self):
        """Um pedaço pronto do início do buffer (e o tira dele), ou None."""
        b = self.buf
        nl = b.find("\n")
        first = b if nl < 0 else b[:nl]
        m = _FENCE.match(first)
        if m:
            # bloco cercado: espera a cerca de fechamento (mesma marca) numa linha própria
            if nl < 0:
                return None
            pos = nl + 1
            while True:
                nxt = b.find("\n", pos)
                if nxt < 0:
                    return None
                if b[pos:nxt].strip().startswith(m.group(1)):
                    end = self._end_with_breaks(b, nxt + 1)
                    break
                pos = nxt + 1
        elif first.lstrip().startswith("|"):
            # tabela: até a primeira linha completa que não começa com "|" (linhas em branco depois vão junto)
            if nl < 0:
                return None
            pos = nl + 1
            while True:
                nxt = b.find("\n", pos)
                rest = (b[pos:] if nxt < 0 else b[pos:nxt]).lstrip(" \t")
                if nxt < 0 and not rest:
                    return None                 # ainda não dá para saber se a tabela continua
                if rest.startswith("|"):
                    if nxt < 0:
                        return None
                    pos = nxt + 1
                    continue
                end = self._end_with_breaks(b, pos) if not rest else pos
                break
        else:
            # linha comum: corta na frase (sem cortar logo após o marcador de lista) ou no fim da linha
            # (a frase quebrada no meio segue na linha de baixo: sai junto, para a citação valer para a frase toda)
            mark = _LIST_MARK.match(first)
            start = mark.end() if mark else 0
            ls, end = 0, None                   # ls: início da linha em exame
            while end is None:
                nl = b.find("\n", ls)
                line = b[ls:] if nl < 0 else b[ls:nl]
                for bm in _BOUNDARY.finditer(line, start if ls == 0 else 0):
                    if re.search(r"[A-Za-zÀ-ÿ]", b[start:ls + bm.start()]):
                        end = ls + bm.end()
                        break
                if end is not None:
                    break
                if nl < 0:
                    return None
                nxt = b[nl + 1:]
                if not nxt or ("\n" not in nxt and len(nxt.strip()) < 4):
                    return None                 # ainda não dá para saber se a próxima linha continua a frase
                if nxt[0] != "\n" and _continues(line, nxt.split("\n", 1)[0]):
                    ls = nl + 1
                    continue
                end = self._end_with_breaks(b, nl + 1)
                if end is None:
                    return None
        if end is None:
            return None
        out, self.buf = b[:end], b[end:]
        return out

    def feed(self, delta):
        self.buf += delta
        out = []
        while True:
            piece = self._take()
            if piece is None:
                break
            if piece.strip():
                out.append(self.pend + piece)
                self.pend = ""
            else:
                self.pend += piece
        return out

    def flush(self):
        s = (self.pend + self.buf).rstrip()
        self.buf = self.pend = ""
        return s if s.strip() else ""
