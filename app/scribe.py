"""Gravação da consulta → evolução: máscara, prompt, chamada ao modelo e conferências sem IA.

Fluxo: trechos transcritos (numerados) → máscara (nome do paciente, CPF, telefone, e-mail, CNS) → modelo
devolve JSON com cada frase ligada aos trechos que a sustentam → conferências determinísticas →
campos para a tela + pontos para o médico conferir.

Limites assumidos (estão no RIPD): a máscara não anonimiza — apelidos e nomes de terceiros escapam, e o
transcritor já recebeu o áudio. O modelo só documenta o que foi dito: não sugere diagnóstico nem conduta.
"""
import json
import os
import re
import unicodedata

from . import cid10, config, llm

PROMPT_VERSION = "2026-10-15.7"
MASK = "[PACIENTE]"
FIELDS = ("s", "o", "a", "p")
VITALS = ("pa_s", "pa_d", "fc", "fr", "temp", "spo2", "peso", "altura", "glicemia")
# faixas plausíveis (as mesmas do RANGE da tela): fora delas é erro de transcrição ou de digitação
RANGE = {"pa_s": (50, 300), "pa_d": (20, 200), "fc": (20, 250), "fr": (4, 80), "temp": (30, 45), "spo2": (40, 100),
         "peso": (0.3, 400), "altura": (0.3, 250), "glicemia": (10, 1500)}
ACOES = ("mantido", "iniciado", "suspenso", "ajustado")
# gravidade de cada ponto para conferir (a tela ordena por ela)
NIVEL = {"pa_coloquial": "info", "alergia": "alto", "numero": "alto", "remedio": "alto", "remedio_nome": "alto", "remedio_desconhecido": "medio", "vital": "alto", "privacidade": "alto", "dose_incomum": "alto",
         "duvida_grave": "alto", "duvida": "medio",
         "dose_longe": "medio", "vital_longe": "medio", "sem_origem": "medio", "inferido": "medio", "cid": "medio",
         "pendencia": "medio", "cadastro": "info"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


_DATA = os.path.join(os.path.dirname(__file__), "data")


def _linhas(nome):
    """Linhas de uma tabela de app/data/, sem os comentários (#) e as linhas vazias. As tabelas clínicas ficam
    fora do código para o médico revisor conferir sem ler Python."""
    with open(os.path.join(_DATA, nome), encoding="utf-8") as f:
        return [x for x in (l.split("#")[0].strip() for l in f) if x]


def _pares(nome):
    """Tabela de duas colunas separadas por TAB: [(chave, valor)], na ordem do arquivo."""
    return [tuple(c.strip() for c in l.split("\t", 1)) for l in _linhas(nome)]


def _lev(a, b):
    """Distância de edição (erros de grafia do transcritor: "losartan" ~ "losartana")."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ===== máscara =====
_PARTICULAS = {"de", "da", "do", "dos", "das", "e", "di", "du", "del"}
_TRATAMENTO = {"dona", "seu", "senhor", "senhora", "sr", "sra", "dr", "dra", "doutor", "doutora", "tia", "tio"}
# sobrenomes que também são palavras comuns (clínicas inclusive): só mascara com maiúscula no meio da frase,
# junto de outro nome, depois de "dona/seu" ou como vocativo
_COMUNS = {"dias", "campos", "leite", "rosa", "clara", "luz", "paz", "cruz", "costa", "lima", "rocha", "reis",
           "santos", "ramos", "flores", "branco", "branca", "franco", "fontes", "neves", "prado", "vale", "serra",
           "sales", "pinto", "sol", "mar", "gloria", "vitoria", "graca", "aparecida", "esperanca", "bispo", "nunes",
           "jesus", "barros", "mendes", "machado", "ferreira", "pereira", "oliveira", "moreira", "salgado", "rios",
           "marcos", "domingos", "jardim", "monte", "coelho", "cordeiro", "carneiro", "pinheiro", "matos", "estrela", "flor",
           "amor", "mel", "lago", "aurora", "celeste", "bela", "linda", "nogueira", "figueira", "porto", "leal", "fortuna",
           # nomes marianos e sobrenomes que são palavras da consulta: "Maria das Dores" não pode apagar "dores no peito"
           "dores", "remedios", "chagas", "angustias", "gracas", "socorro", "prazeres", "anjos", "milagres", "penha",
           "passos", "pimenta", "canela", "cravo", "guerra", "alegria"}
# doença, sinal ou síndrome com nome de pessoa ("doença de Chagas", "doença de Wilson"): nunca é o paciente
_EPONIMO = {"doenca", "sindrome", "mal", "sinal", "teste", "manobra", "escala", "paralisia", "linfoma", "tireoidite",
            "molestia", "reacao", "fenomeno", "criterios", "classificacao"}
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ']+")
# CPF e CNS: com pontuação ou dígitos juntos sempre; separados só por espaço, apenas logo depois de "CPF"/"CNS"/
# "cartão do SUS" — senão "glicemias de 100 120 130 14" viraria um CPF e o modelo perderia os valores
_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{11}\b|(?<=cpf)[^\d\n]{0,15}\b\d{3}\s?\d{3}\s?\d{3}[-\s]?\d{2}\b", re.I)
# telefone: celular (9 + 4 + 4, com ou sem DDD), fixo com hífen ou com DDD entre parênteses, ou qualquer 8 dígitos logo
# depois de "telefone/celular/zap". Dois números de 4 dígitos soltos ("leucócitos 8500 9200", "2019 2020") não são telefone.
_FONE = re.compile(r"(?:\(?\b\d{2}\)?\s?)?\b9\d{4}[-\s]?\d{4}\b|\(\d{2}\)\s?\d{4}[-\s]?\d{4}\b"
                   r"|\b(?!(?:19|20)\d\d-(?:19|20)\d\d\b)\d{4}-\d{4}\b"
                   r"|(?:fone|celular|zap|whatsapp|contato)[^\d\n]{0,12}\b\d{4}\s\d{4}\b|\b\d{10,11}\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CNS = re.compile(r"\b\d{15}\b|(?<=cns|sus)[^\d\n]{0,15}\b\d{3}\s?\d{4}\s?\d{4}\s?\d{4}\b", re.I)
_PLACEHOLDERS = ("[CPF]", "[TELEFONE]", "[E-MAIL]", "[CNS]")


def mask_docs(text):
    """Tira CPF, CNS, telefone e e-mail (sem mexer em nomes)."""
    text = _EMAIL.sub("[E-MAIL]", str(text or ""))
    text = _CNS.sub(lambda m: re.sub(r"\d[\d\s]*\d", "[CNS]", m.group(0)), text)
    text = _CPF.sub(lambda m: re.sub(r"\d[\d.\s-]*\d", "[CPF]", m.group(0)), text)
    return _FONE.sub(lambda m: re.sub(r"[(\d][\d\s()-]*\d", "[TELEFONE]", m.group(0)), text)


def mask(text, patient_name=""):
    """Troca o nome do paciente (e diminutivos do primeiro nome) por [PACIENTE] e tira CPF, CNS, telefone e
    e-mail. Nome que também é palavra comum ("Rosa", "Dias", "Dores", "Remédios") só é trocado com maiúscula no meio
    da frase, junto de outro nome, depois de "dona/seu" ou como vocativo — para não apagar palavra clínica; e nunca
    num epônimo ("doença de Chagas")."""
    text = mask_docs(text)
    toks = [t for t in (norm(x) for x in _WORD.findall(patient_name or "")) if len(t) >= 3 and t not in _PARTICULAS]
    if not toks:
        return text
    first = toks[0]
    # diminutivo: em português costuma cair a vogal (ou o "os") do fim: Teresa → Teresinha, Carlos → Carlinhos, Ana → Aninha
    # (de qualquer nome do paciente: muita gente é chamada pelo segundo nome — Luiz Carlos → Carlinhos)
    stems = {x for t in toks for x in (t, t[:-1] if t[-1:] in "aeo" else t, t[:-2] if t.endswith(("os", "as", "es")) else t)
             if len(x) >= 2}
    words = list(_WORD.finditer(text))

    def is_name(i):
        w = words[i].group(0)
        n = norm(w)
        if n in toks:
            return w[:1].isupper() or n not in _COMUNS          # "maria" minúsculo também; "rosa" minúsculo não
        return w[:1].isupper() and any(n.startswith(x) and 3 <= len(n) - len(x) <= 6 for x in stems) and \
            n.endswith(("inha", "inho", "inhas", "inhos", "zinha", "zinho", "ita", "ito"))
    cand = [is_name(i) for i in range(len(words))]
    keep = []
    ws = [norm(w.group(0)) for w in words]

    def nb(i, d):                                        # vizinho, pulando "de/da/dos": "Maria das Dores"
        j = i + d
        while 0 <= j < len(words) and ws[j] in _PARTICULAS:
            j += d
        return j if 0 <= j < len(words) else None
    for i, w in enumerate(words):
        if not cand[i]:
            continue
        if i >= 2 and ws[i - 1] in ("de", "do", "da") and ws[i - 2] in _EPONIMO:
            continue                                     # "doença de Chagas", "doença de Wilson"
        if ws[i] in _COMUNS:
            before = text[:w.start()].rstrip()
            mid = bool(before) and before[-1] not in '.!?:"“(\n'
            a, b = nb(i, -1), nb(i, 1)
            near = (a is not None and cand[a]) or (b is not None and cand[b]) or (i and ws[i - 1] in _TRATAMENTO)
            voc = text[w.end():w.end() + 1] == ","            # vocativo: "Rosa, como vai?"
            if not (near or mid or voc):
                continue
        keep.append(w.span())
    out, last = [], 0
    for a, b in keep:
        out.append(text[last:a]); out.append(MASK); last = b
    out.append(text[last:])
    return re.sub(r"\[PACIENTE\](?:\s+(?:de|da|do|dos|das|e)?\s*\[PACIENTE\])+", MASK, "".join(out))


# ===== números (inclusive por extenso) =====
_UNI = {"zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
        "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
        "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19,
        "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70, "oitenta": 80,
        "noventa": 90, "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300,
        "trezentas": 300, "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500, "quinhentas": 500,
        "seiscentos": 600, "seiscentas": 600, "setecentos": 700, "setecentas": 700, "oitocentos": 800,
        "oitocentas": 800, "novecentos": 900, "novecentas": 900}
_NUM = re.compile(r"\d+(?:[.,]\d+)?$")
# token: código com letra antes do número ("a1c", "b12", "spo2", "i10", "t4") fica inteiro e NÃO é número
_TOK = re.compile(r"[a-z]+\d[a-z0-9]*|\d+(?:[.,]\d+)?|[a-z]+")


def _f(x):
    """Valor de um número escrito com algarismos: "6,9" → 6,9; "1.250" → 1250 (milhar); "0,125" → 0,125."""
    if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", x):
        return float(x.replace(".", ""))
    return float(x.replace(",", "."))


def tokens(text):
    out = []
    for t in _TOK.findall(norm(text)):
        # "128x82" vira "128", "x82": o x entre números é separador (PA, "2x"), não código
        if re.fullmatch(r"x\d+(?:[.,]\d+)?", t) and out and _NUM.match(out[-1]):
            out += ["x", t[1:]]
        else:
            out.append(t)
    return out


def _phrase(toks, i):
    """Número por extenso a partir de toks[i]: (valor, índice depois do fim) ou None."""
    n = len(toks)
    if toks[i] not in _UNI and toks[i] != "mil":
        return None
    j, total, cur = i, 0, 0
    while j < n:
        w = toks[j]
        if w in _UNI:
            # duas palavras-número seguidas sem "e" são dois números ("cento e sessenta, cento e cinquenta"),
            # exceto depois de "mil" ("mil duzentos")
            if j > i and toks[j - 1] in _UNI:
                break
            cur += _UNI[w]
        elif w == "mil":
            total += (cur or 1) * 1000; cur = 0
        elif w == "e" and j + 1 < n and toks[j + 1] in ("meio", "meia"):
            cur += 0.5; j += 1
        elif not (w == "e" and j + 1 < n and (toks[j + 1] in _UNI or toks[j + 1] == "mil")):
            break
        j += 1
    return total + cur, j


def scan(text):
    """Números de um texto com a posição em tokens(text): [(valor, início, fim inclusivo)].
    Algarismos ("6,9", "128x82", "12/12h"), por extenso ("cento e vinte e oito", "seis vírgula vinte e
    cinco", "trinta e oito e meio", "meio comprimido") e compostos ("86 quilos e 800 gramas" → 86,8)."""
    toks = tokens(text)
    vals, i, n = [], 0, len(toks)
    while i < n:
        t = toks[i]
        if _NUM.match(t):
            v, j = _f(t), i + 1
            if j + 1 < n and toks[j] == "e" and toks[j + 1] in ("meio", "meia"):     # "38 e meio"
                v, j = v + 0.5, j + 2
        elif t in ("meio", "meia") and not (i and toks[i - 1] == "e"):
            v, j = 0.5, i + 1
        else:
            p = _phrase(toks, i)
            if not p:
                i += 1
                continue
            v, j = p
        # "<número> vírgula <número>": decimal, inclusive "seis vírgula vinte e cinco" e "zero vírgula zero cinco"
        if j + 1 < n and toks[j] == "virgula":
            k, zeros = j + 1, ""
            while k < n and toks[k] == "zero":
                zeros += "0"; k += 1
            if k < n and _NUM.match(toks[k]) and "," not in toks[k] and "." not in toks[k]:
                v, j = float(f"{int(v)}.{zeros}{toks[k]}"), k + 1
            elif k < n and _phrase(toks, k):
                dv, k2 = _phrase(toks, k)
                v, j = float(f"{int(v)}.{zeros}{int(dv)}"), k2
            elif zeros:
                v, j = float(f"{int(v)}.{zeros}"), k
        vals.append((v, i, j - 1))
        i = j
    extra = []
    for (a, ia, ja), (b, ib, jb) in zip(vals, vals[1:]):
        mid = toks[ja + 1:ib]
        if mid and mid[0].startswith("quilo") and b < 1000 and jb + 1 < n and toks[jb + 1].startswith("grama"):
            extra.append((round(a + b / 1000, 3), ia, jb))
        if a == 1 and mid and mid[0].startswith("metro") and 10 <= b < 100:          # "um metro e setenta"
            extra += [(round(1 + b / 100, 2), ia, jb), (100 + b, ia, jb)]
    for v, ia, ja in vals:
        # "setenta quilos e meio", "um comprimido e meio", "dois dias e meio": o meio vem depois da unidade
        if ja + 3 < n and re.fullmatch(r"[a-z]+", toks[ja + 1]) and toks[ja + 1] not in _UNI and toks[ja + 1] != "e" \
                and toks[ja + 2] == "e" and toks[ja + 3] in ("meio", "meia"):
            extra.append((v + 0.5, ia, ja + 3))
        # altura dita "um e setenta" (1,70 m): o leitor soma 1 + 70; vale também 1,70 e 170
        if toks[ia] == "um" and ja > ia + 1 and toks[ia + 1] == "e" and 10 <= v - 1 < 100 and v == int(v):
            extra += [(round(1 + (v - 1) / 100, 2), ia, ja), (100 + v - 1, ia, ja)]
    return vals + extra


def numbers(text):
    return [v for v, _, _ in scan(text)]


def _fmt(v):
    return (f"{v:.3f}".rstrip("0").rstrip(".")).replace(".", ",")


def digitize(text):
    """Texto normalizado com os números por extenso trocados por algarismos (para comparar e medir erro)."""
    toks = tokens(text)
    spans = sorted((s for s in scan(text) if s[1] <= s[2]), key=lambda s: (s[1], -(s[2] - s[1])))
    out, i = [], 0
    for v, a, b in spans:
        if a < i:
            continue
        out += toks[i:a] + [_fmt(v)]; i = b + 1
    return " ".join(out + toks[i:])


def _has_number(x, pool):
    return any(abs(x - y) < 1e-6 for y in pool)


# ===== remédios =====
# ----- identidade: é o mesmo remédio? ("losartan" ~ "losartana"; "vitamina D" ≠ "vitamina B12") -----
# nomes que começam por palavra genérica: "vitamina D" ≠ "vitamina B12", "insulina NPH" ≠ "insulina regular"
_GENERICO = {"vitamina", "sulfato", "acido", "insulina", "cloreto", "carbonato", "citrato", "oxido", "fosfato",
             "bicarbonato", "hidroxido", "complexo", "solucao", "soro", "gluconato", "succinato", "tartarato"}
_PART = {"de", "do", "da", "dos", "das", "e", "com"}


def _drug_key(name):
    raw = [t for t in re.findall(r"[a-z0-9]+", norm(name)) if t not in _PART and not t.isdigit()]
    if not raw:
        return []
    if raw[0] in _GENERICO and len(raw) > 1:
        return raw[:2]
    return [t for t in raw if len(t) >= 3][:1]


def _tok_eq(x, y):
    """Mesma palavra, admitindo erro de grafia do transcritor: até 1 letra (2 com 12+ letras).
    "losartan" ~ "losartana"; prednisona ≠ prednisolona; clonazepam ≠ diazepam."""
    if x == y:
        return True
    m = min(len(x), len(y))
    return m >= 6 and abs(len(x) - len(y)) <= 2 and _lev(x, y) <= (2 if m >= 12 else 1)


def same_drug(a, b):
    """O texto b cita o remédio a?"""
    ka, tb = _drug_key(a), re.findall(r"[a-z0-9]+", norm(b))
    return bool(ka) and all(any(_tok_eq(k, t) for t in tb) for k in ka)


def _mentions(name, text):
    """Posições em tokens(text) em que o remédio é citado (pela palavra que o distingue)."""
    ka = _drug_key(name)
    if not ka:
        return []
    toks, anchor = tokens(text), ka[-1]
    hits = [i for i, t in enumerate(toks) if _tok_eq(anchor, t)]
    if len(ka) > 1 and len(anchor) < 3:               # "vitamina D": o "D" sozinho não basta
        hits = [i for i in hits if any(_tok_eq(ka[0], t) for t in toks[max(0, i - 3):i + 1])]
    return hits


# ----- nome conhecido: a transcrição às vezes parte ou troca ("suma triptana", "Traz Zodona") -----
_FORMA = {"comprimido", "comprimidos", "cp", "capsula", "capsulas", "creme", "pomada", "gel", "locao", "xarope", "gotas",
          "gota", "solucao", "suspensao", "spray", "aerossol", "colirio", "injetavel", "ampola", "adesivo", "supositorio",
          "ovulo", "sache", "mg", "mcg", "ml", "ui", "g", "retard", "xr", "cr", "sr", "lp", "liberacao", "prolongada", "oral",
          "topico", "topica", "vaginal", "nasal", "bombinha", "cloridrato", "maleato", "besilato", "mesilato", "succinato",
          "tartarato", "fumarato", "sodico", "sodica", "potassico", "potassica", "dissodico", "monoidratado", "bromidrato",
          "hiclato", "valerato", "propionato", "dipropionato", "furoato", "xinafoato", "acetato", "de", "do", "da", "dos",
          "das", "e", "com", "mais", "a", "o"}
_VAGO = {"acido", "sulfato", "carbonato", "cloreto", "citrato", "hidroxido", "peroxido", "oleo", "sais", "soro", "complexo",
         "vitamina", "lagrima", "sodio", "calcio", "potassio", "magnesio", "conjugados", "estrogenios", "toxina", "benzoato",
         "reidratacao", "artificial"}
_LEX = None


def _drug_tokens(s):
    return [t for t in re.findall(r"[a-z]+[0-9]*", norm(s)) if t not in _FORMA]


def _lexicon():
    """(nomes, palavras específicas, {nome sem espaço: nome para mostrar}) de app/data/remedios.txt."""
    global _LEX
    if _LEX is None:
        names, toks, glued = set(), set(), {}
        for line in _linhas("remedios.txt"):
            n = " ".join(_drug_tokens(line))
            if n:
                names.add(n); glued.setdefault(n.replace(" ", ""), line)
                toks |= {t for t in n.split() if len(t) >= 4 and t not in _VAGO}
        _LEX = (names, toks, glued)
    return _LEX


def drug_lookup(nome):
    """O nome do remédio é conhecido? ("ok", None). Juntando as partes vira um conhecido: ("junto", nome).
    Uma ou duas letras de diferença de um conhecido: ("parecido", nome). Senão ("desconhecido", None).
    Combinações ("losartana + hidroclorotiazida") são conferidas parte por parte; vale o pior resultado."""
    names, toks, glued = _lexicon()
    rank, worst = {"ok": 0, "desconhecido": 1, "parecido": 2, "junto": 2}, ("ok", None)
    nome = re.split(r"(?:^|\s)\d", norm(nome))[0]            # o nome vem antes da dose ("losartana 50 mg 12/12h")
    for part in re.split(r"\s*(?:\+|/|\bcom\b|\be\b)\s*", nome):
        t = _drug_tokens(part)
        if not t or " ".join(t) in names or any(x in toks for x in t):
            continue
        # grafia internacional do mesmo remédio ("losartan", "amlodipine", "omeprazole"): é o mesmo, não avisa
        if any(v in glued for x in t for v in (x + "a", x + "o", x[:-1], x[:-1] + "a", x[:-1] + "o") if len(x) >= 5):
            continue
        got = next((("junto", glued[t[i] + t[i + 1]]) for i in range(len(t) - 1) if t[i] + t[i + 1] in glued), None)
        if not got:
            best = None
            for w in ["".join(t)] + [x for x in t if len(x) >= 5]:
                lim = 1 if len(w) < 9 else 2
                for g in glued:
                    if g[:1] == w[:1] and abs(len(g) - len(w)) <= lim:
                        d = _lev(w, g)
                        if d <= lim and (best is None or d < best[0]):
                            best = (d, glued[g])
            got = ("parecido", best[1]) if best else ("desconhecido", None)
        if rank[got[0]] > rank[worst[0]]:
            worst = got
    return worst


# ----- alergia: o remédio bate com uma alergia do cadastro, inclusive da mesma família ou dentro de uma marca -----
_ALERGIA_FAM = [(pat, ms.split("; ")) for pat, ms in _pares("alergias.tsv")]          # família → remédios dela
_SEM_ALERGIA = re.compile(r"^\s*(nega|nao|sem|nenhuma|desconhec)")
_COMPOSICAO = {marca: ativos.split("; ") for marca, ativos in _pares("composicao.tsv")}   # "Dorflex" → dipirona…


def allergy_hits(name, allergies):
    """Alergias do cadastro que batem com o remédio (inclusive da mesma família). Compara palavra inteira:
    alergia a "sulfa" não dispara em "sulfato ferroso"."""
    mt = re.findall(r"[a-z0-9]+", norm(name))
    mn = " ".join(mt)
    for marca, ativos in _COMPOSICAO.items():                 # "Dorflex" → também dipirona e orfenadrina
        if f" {marca} " in f" {mn} ":
            mt = mt + ativos
    mn = " ".join(mt)
    hits = []
    for line in [x for x in re.split(r"[\n,;]+", allergies or "") if x.strip()]:
        an = norm(line)
        if _SEM_ALERGIA.match(an):
            continue
        fam = [m for pat, ms in _ALERGIA_FAM if re.search(pat, an) for m in ms]
        own = [t for t in re.findall(r"[a-z0-9]+", an) if len(t) >= 4 and t not in ("alergia", "alergico", "alergica")]
        def hit(f):
            if " " in f:
                return f" {f} " in f" {mn} "
            return any(t == f or (len(f) >= 7 and t.startswith(f) and not t.startswith("sulfat")) for t in mt)
        if any(hit(f) for f in fam + own):
            hits.append(line.strip())
    return hits


# ----- dose habitual (só para AVISAR; não é recomendação de dose): app/data/doses.tsv -----
_DOSE = {k: (float(lo), float(hi)) for k, v in _pares("doses.tsv") for lo, hi in [v.split("\t")]}
_UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg|miligramas?|g|gramas?|mcg|µg|ug|microgramas?)\b", re.I)
_NAO_MG = re.compile(r"\b(ml|gotas?|jatos?|puffs?|ui|unidades?|comprimidos?|caps?|capsulas?|sache|ampolas?|%)\b")


def dose_incomum(nome, dose):
    """(dose em mg, faixa) se a dose de uma tomada estiver fora da faixa usual do remédio; senão None."""
    key = next((k for k in _DOSE if same_drug(k, nome)), None)
    d = norm(dose)
    if not key or not d or _NAO_MG.search(d):
        return None
    m = _UNIT.search(d)
    if m:
        v, u = _f(m.group(1)), m.group(2).lower()
        mg = v * 1000 if u in ("g", "grama", "gramas") else v / 1000 if u in ("mcg", "µg", "ug", "micrograma", "microgramas") else v
    else:
        nums = numbers(d)
        if len(nums) != 1:
            return None
        mg = nums[0]                                    # "ciprofloxacino 5": sem unidade, lê como mg
        lo, hi = _DOSE[key]
        if not lo / 1.01 <= mg <= hi * 1.01 and lo / 1.01 <= mg / 1000 <= hi * 1.01:
            return None                                 # "levotiroxina 50": sem unidade, era micrograma
    lo, hi = _DOSE[key]
    return None if lo / 1.01 <= mg <= hi * 1.01 else (mg, (lo, hi))


# ===== perfil de escrita (sem IA; nenhum texto de outro paciente sai) =====
_SIGLAS = set(_linhas("siglas.txt"))                 # só estas saem das evoluções do médico


def writing_profile(notes):
    """Resumo do jeito de escrever do médico a partir das evoluções dele (só estatísticas e siglas de uma
    lista fixa; nenhum trecho de texto sai daqui)."""
    ns = [n for n in notes or [] if (n.get("content") or "").strip() and (n.get("data") or {}).get("kind") != "labs"][:30]
    if not ns:
        return "Sem evoluções anteriores: use frases curtas, objetivas, no estilo de prontuário."
    soap = sum(1 for n in ns if (n.get("data") or {}).get("mode") == "soap")
    words = [len((n.get("content") or "").split()) for n in ns]
    topics = sum(1 for n in ns if re.search(r"^\s*[-•*]\s", n.get("content") or "", re.M))
    cnt = {}
    for n in ns:
        for t in re.findall(r"\b[A-Z0-9]{2,5}\b", n.get("content") or ""):
            if t in _SIGLAS:
                cnt[t] = cnt.get(t, 0) + 1
    siglas = [k for k, _ in sorted(cnt.items(), key=lambda kv: -kv[1])[:12]]
    med = sorted(words)[len(words) // 2]
    return (f"Evoluções anteriores deste médico: {len(ns)}; {'SOAP' if soap * 2 >= len(ns) else 'texto livre'} na maioria; "
            f"cerca de {med} palavras por evolução; {'usa tópicos' if topics * 3 >= len(ns) else 'escreve em frases corridas'}."
            + (f" Siglas que ele usa: {', '.join(siglas)}." if siglas else ""))


# ===== prompt =====
# o texto vai ao modelo exatamente como está no arquivo; mudou o texto, sobe PROMPT_VERSION (um teste confere)
with open(os.path.join(_DATA, "escriba_prompt.txt"), encoding="utf-8") as _arq:
    SYSTEM = _arq.read()


def annotate(text, doubts):
    """Marca com (?) as palavras que o transcritor ouviu com pouca certeza."""
    for w in sorted({d for d in doubts or [] if d}, key=len, reverse=True):
        text = re.sub(r"(?<![\w(])" + re.escape(w) + r"(?![\w(?])", lambda m: m.group(0) + "(?)", text, flags=re.I)
    return text


def _stem_eq(a, b):
    """Mesma palavra ou mesmo radical ("desmaio" ~ "desmaiando"); números só iguais."""
    if a == b:
        return True
    if _NUM.match(a) or _NUM.match(b):
        return False
    m, k = min(len(a), len(b)), 0
    while k < m and a[k] == b[k]:
        k += 1
    return m >= 5 and k >= max(5, int(0.7 * m))


def build_messages(segments, mode, patient=None, profile="", last_note="", patient_name=""):
    """segments: [{"seq": 1, "at": 12.5, "text": "..."}]. patient: cadastro (problemas, medicações, alergias,
    idade, sexo). Tudo o que vai ao modelo passa pela máscara aqui (mesmo que já venha mascarado)."""
    p = patient or {}
    m = lambda t: mask(t, patient_name)
    ctx = {"modo": "SOAP" if mode == "soap" else "texto livre",
           "cadastro": {"idade": p.get("age") or "", "sexo": p.get("sex") or "", "problemas": m(p.get("problems")),
                        "medicacoes": m(p.get("medications")), "alergias": m(p.get("allergies"))},
           "perfil_de_escrita": profile or "", "ultima_evolucao": m(last_note)[:3000]}
    tx = "\n".join(f"[{s['seq']}] ({int(s.get('at', 0)) // 60}:{int(s.get('at', 0)) % 60:02d}) "
                   f"{annotate(m(s['text']), s.get('duvidas'))}" for s in segments if (s.get("text") or "").strip())
    user = ("Contexto (não é parte da consulta):\n" + json.dumps(ctx, ensure_ascii=False) +
            "\n\n<transcricao>\n" + tx + "\n</transcricao>\n\nEscreva a evolução no modo " + ctx["modo"] + ".")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


# ===== conferências (sem IA) =====
# palavras que indicam cada sinal vital perto do número (antes ou logo depois)
_VLAB = {"pa": {"pressao", "pa", "arterial", "pressaozinha"},
         "fc": {"frequencia", "fc", "pulso", "batimentos", "cardiaca", "bpm"},
         "fr": {"respiratoria", "fr", "irpm", "respiracao"},
         "temp": {"temperatura", "temp", "graus", "febre", "termometro", "axilar"},
         "spo2": {"saturacao", "saturando", "spo2", "oxigenio", "sat", "oximetro"},
         "peso": {"peso", "pesa", "pesando", "quilos", "quilo", "kg"},
         "altura": {"altura", "mede", "estatura", "comprimento", "centimetros", "cm"},
         "glicemia": {"glicemia", "glicose", "acucar", "dextro", "hgt", "capilar"}}


_LAB = {lab: k for k, labs in _VLAB.items() for lab in labs}


def _label_at(toks, i):
    t = toks[i]
    if t == "frequencia":              # "frequência respiratória" é FR; "frequência" sozinha é FC
        return "fr" if i + 1 < len(toks) and toks[i + 1].startswith("respirat") else "fc"
    return _LAB.get(t)


def _near_label(k, toks, a, b, before=8, after=3):
    """O rótulo mais próximo do número (antes; senão logo depois) é o do sinal k? Para a PA a janela é maior:
    o par "X por Y" já é forte e o médico às vezes corrige ("150 por 90... não, li errado: 140 por 90")."""
    kk = "pa" if k in ("pa_s", "pa_d") else k
    if kk == "pa":
        before = 16
    for i in range(a - 1, max(-1, a - before - 1), -1):
        lab = _label_at(toks, i)
        if lab:
            return lab == kk
    for i in range(b + 1, min(len(toks), b + 1 + after)):
        lab = _label_at(toks, i)
        if lab:
            return lab == kk
    return False


def _pa_pairs(text):
    """Pares "X por Y" / "XxY" / "X/Y" (pressão) com a posição: [(sist, diast, início, fim)]."""
    toks, sc = tokens(text), sorted(scan(text), key=lambda s: s[1])
    out = []
    for (a, ia, ja), (b, ib, jb) in zip(sc, sc[1:]):
        between = toks[ja + 1:ib]
        if ib > ja and len(between) <= 1 and all(w in ("por", "x", "sobre") for w in between):
            out.append((a, b, ia, jb))
    return out


def _pa_coloquial(s, d):
    """ "Doze por oito" é 120x80: PA dita em centímetros de mercúrio."""
    return 6 <= s <= 30 and 3 <= d <= 20 and s > d


def _same_vital(k, v, x):
    """O número v do trecho vale o x da evolução? Altura em metros ou centímetros (1,62 = 162)."""
    return abs(v - x) < 1e-6 or (k == "altura" and (abs(v * 100 - x) < 1e-6 or abs(v / 100 - x) < 1e-6))


def _vital_ok(k, x, text):
    """O valor aparece no trecho junto do rótulo certo? (pega "PA 128 por 82, FC 74" virando PA 128x74)"""
    toks = tokens(text)
    if k in ("pa_s", "pa_d"):
        return any((abs((s if k == "pa_s" else d) - x) < 1e-6 or
                    (_pa_coloquial(s, d) and abs((s if k == "pa_s" else d) * 10 - x) < 1e-6)) and _near_label(k, toks, a, b)
                   for s, d, a, b in _pa_pairs(text))
    return any(_same_vital(k, v, x) and _near_label(k, toks, a, b) for v, a, b in scan(text))


def _src_numbers(text):
    """Números do trecho, mais a PA coloquial em mmHg ("doze por oito" → 120 e 80)."""
    return numbers(text) + [y * 10 for s, d, _, _ in _pa_pairs(text) if _pa_coloquial(s, d) for y in (s, d)]


def _clean_out(t):
    """Tira das frases o que nunca pode ir para o prontuário: as marcas da máscara."""
    t = t.replace("(?)", "")
    t = re.sub(r"(^|[.!?]\s+)\[PACIENTE\]", lambda m: m.group(1) + "Paciente", t)
    t = t.replace(MASK, "paciente")
    leaked = any(p in t for p in _PLACEHOLDERS)
    for p in _PLACEHOLDERS:
        t = t.replace(p, "")
    return " ".join(t.split()), leaked


def _items(v):
    return [x for x in (v if isinstance(v, list) else []) if isinstance(x, dict)]


class _Conferencia:
    """Uma conferência da saída do modelo: os trechos (já mascarados), o cadastro e os pontos levantados. Cada parte
    da evolução tem a sua: frases, sinais vitais, CID e remédios."""

    def __init__(self, segments, patient):
        p = patient or {}
        self.seg = {int(s["seq"]): s for s in segments}
        self.alergias = p.get("allergies")
        self.cad_meds = p.get("medications") or ""
        self.cad_nums = numbers(self.cad_meds + " " + (p.get("problems") or ""))
        self.flags = []

    def flag(self, tipo, campo, texto, src=(), **kw):
        self.flags.append(dict({"tipo": tipo, "nivel": NIVEL.get(tipo, "medio"), "campo": campo, "texto": texto,
                                "src": list(src)}, **kw))

    def srcs(self, item):
        return [int(x) for x in (item.get("src") or []) if str(x).isdigit() and int(x) in self.seg]

    def pool(self, ids):
        return " ".join(self.seg[i]["text"] for i in ids)

    def doubts(self, ids):
        """Palavras duvidosas dos trechos citados que importam: 4+ letras ou número."""
        out = set()
        for i in ids:
            for d in self.seg[i].get("duvidas") or []:
                out |= {t for t in tokens(d) if len(t) >= 4 or _NUM.match(t)}
        return out

    def frases(self, lst, field):
        """Frases de um campo: sem origem saem; número fora do trecho, frase deduzida e palavra com dúvida viram ponto."""
        keep = []
        for it in _items(lst):
            t, leaked = _clean_out(" ".join(str(it.get("t") or "").split()))
            if leaked:
                self.flag("privacidade", field, "dado pessoal mascarado apareceu no texto e foi retirado")
            if not t:
                continue
            ids = self.srcs(it)
            if not ids:
                self.flag("sem_origem", field, t)
                continue
            nums_src = _src_numbers(self.pool(ids))
            for x in numbers(t):
                if not _has_number(x, nums_src):
                    self.flag("cadastro" if _has_number(x, self.cad_nums) else "numero", field, t, ids, valor=x)
            if it.get("tipo") == "inferido":
                self.flag("inferido", field, t, ids)
            dset = self.doubts(ids)
            dv = [w for w in tokens(t) if any(_stem_eq(w, d) for d in dset)]
            if dv:
                self.flag("duvida", field, f"{t} (ouvido com dúvida: {', '.join(dict.fromkeys(dv))})", ids)
            keep.append({"t": t, "src": ids, "par": bool(it.get("par"))})
        return keep

    def sinal(self, k, v):
        """Valor do sinal vital para o campo, ou None (impossível, fora do trecho ou mal formado: vira ponto)."""
        if k not in VITALS or not isinstance(v, dict) or str(v.get("v") or "").strip() == "":
            return None
        raw = str(v.get("v")).strip()
        ids = self.srcs(v)
        try:                                    # "86,8", "86.8" e "1.000" (milhar)
            x = _f(raw) if re.fullmatch(r"\d+(?:[.,]\d+)*", raw) else float(raw.replace(",", "."))
        except ValueError:
            self.flag("vital", k, f"{k} = {raw}: formato inválido (descartado)", ids)
            return None
        if k in ("pa_s", "pa_d") and x < 30 and any(_pa_coloquial(s, d) and abs((s if k == "pa_s" else d) - x) < 1e-6
                                                    for s, d, _, _ in _pa_pairs(self.pool(ids))):
            self.flag("pa_coloquial", k, f"PA dita de forma coloquial: {_fmt(x)} registrado como {_fmt(x * 10)} mmHg", ids)
            x = x * 10
        val = _fmt(x)
        lo, hi = RANGE[k]
        if not (lo <= x <= hi):
            self.flag("vital", k, f"{k} = {val} fora da faixa plausível (descartado)", ids)
            return None
        src_text = self.pool(ids)
        if any(_NUM.match(d) and abs(_f(d) - x) < 1e-6 for d in self.doubts(ids)):
            self.flag("duvida_grave", k, f"{k} = {val}: número ouvido com dúvida", ids, valor=x)
        if not ids or not any(_same_vital(k, y, x) for y in _src_numbers(src_text)):
            # não vai para o campo: num campo de PA ou peso o número pareceria medido. O médico digita, se foi dito.
            self.flag("numero", k, f"{k} = {val} não encontrado no trecho citado (não preenchido)", ids, valor=x)
            return None
        if not _vital_ok(k, x, src_text):
            self.flag("vital_longe", k, f"{k} = {val}: o número está no trecho, mas não junto de {k.split('_')[0].upper()}",
                      ids, valor=x)
        return val

    def cid(self, c, lista):
        """CID-10 conferido na tabela do DATASUS (subcódigo que ela não tem vira a categoria) e sem repetir."""
        code = str(c.get("code") or "").upper().strip()
        desc = cid10.get(code) if code else None
        if not desc and len(code) > 3 and cid10.leaf(code[:3]):       # subcódigo que a tabela do DATASUS não tem (I48.9 → I48)
            self.flag("cid", "a", f"CID {code} não existe na tabela do DATASUS: usado {code[:3]} ({cid10.get(code[:3])})", self.srcs(c))
            code, desc = code[:3], cid10.get(code[:3])
        if not desc:
            self.flag("cid", "a", f"CID {code or '?'} não existe na tabela (descartado)", self.srcs(c))
            return
        if any(x["code"] == code for x in lista):
            return
        ids = self.srcs(c)
        if not ids:
            self.flag("cid", "a", f"CID {code} sem trecho de origem: confirme se o diagnóstico foi dito")
        lista.append({"code": code, "desc": desc, "src": ids})

    def remedio(self, m, nome, names):
        """Um remédio de "meds": nome ouvido com dúvida ou desconhecido, fora da fala, alergia, dose fora do usual e
        dose/posologia que não estão junto do nome no trecho."""
        ids = self.srcs(m)
        acao = m.get("acao") if m.get("acao") in ACOES else ""
        item = {"nome": nome, "dose": str(m.get("dose") or "").strip(), "posologia": str(m.get("posologia") or "").strip(),
                "acao": acao, "src": ids}
        text = self.pool(ids)
        pos = _mentions(nome, text)
        dv = self.doubts(ids)
        key = _drug_key(nome)
        if key and any(_tok_eq(key[-1], d) for d in dv):
            self.flag("duvida_grave", "p", f"{nome}: nome do remédio ouvido com dúvida. Confira se foi este o remédio.", ids)
        for x in numbers(item["dose"] + " " + item["posologia"]):
            if any(_NUM.match(d) and abs(_f(d) - x) < 1e-6 for d in dv):
                self.flag("duvida_grave", "p", f"{nome}: {_fmt(x)} ouvido com dúvida", ids, valor=x)
        if not same_drug(nome, self.cad_meds):
            st, sug = drug_lookup(nome)
            if st in ("junto", "parecido"):
                self.flag("remedio_nome", "p", f"{nome}: nome de remédio não reconhecido. Seria {sug}? Confira na transcrição.",
                          ids, nome=nome, sugestao=sug)
            elif st == "desconhecido":
                self.flag("remedio_desconhecido", "p", f"{nome}: remédio fora da lista conhecida. Confira o nome.", ids, nome=nome)
        if not pos and not same_drug(nome, self.cad_meds):
            self.flag("remedio", "p", f"{nome}: não aparece na fala nem no cadastro", ids)
        if acao != "suspenso":
            for a in allergy_hits(nome, self.alergias):
                self.flag("alergia", "p", f"{nome} com alergia registrada a {a}", ids)
            odd = dose_incomum(nome, item["dose"])
            if odd:
                self.flag("dose_incomum", "p", f"{nome} {item['dose']}: fora da dose usual por tomada "
                          f"({_fmt(odd[1][0])}–{_fmt(odd[1][1])} mg). Confira o nome e a dose: o transcritor pode ter trocado "
                          "o remédio.", ids)
        # dose e posologia: o número precisa estar no trecho, de preferência logo depois do nome do remédio
        toks = tokens(text)
        others = [i for n2 in names if n2 and n2 != nome for i in _mentions(n2, text)]
        win = set()
        for i in pos:
            stop = min([j for j in others if j > i] + [i + 20, len(toks)])
            start = max([j for j in others if j < i] + [i - 5])
            win |= {round(v, 3) for v, a, b in scan(text) if start < a < stop and a != i}
        cad_line = next((l for l in self.cad_meds.split("\n") if same_drug(nome, l)), "")
        for x in numbers(item["dose"] + " " + item["posologia"]):
            if pos and _has_number(x, win):
                continue
            if _has_number(x, numbers(cad_line)):
                self.flag("cadastro", "p", f"{nome}: {item['dose']} {item['posologia']} (dose do cadastro: confirme se não mudou)".strip(),
                          ids, valor=x)
            elif _has_number(x, numbers(text)):
                self.flag("dose_longe", "p", f"{nome}: {_fmt(x)} está no trecho, mas não junto do nome do remédio", ids, valor=x)
            else:
                self.flag("numero", "p", f"{nome}: {item['dose']} {item['posologia']}".strip(), ids, valor=x)
        return item

    def pontos(self):
        """Os pontos sem repetição ("12/12h" tem dois 12: um aviso só), os mais importantes primeiro."""
        seen, uniq = set(), []
        for f in self.flags:
            k = (f["tipo"], f["campo"], f["texto"])
            if k not in seen:
                seen.add(k); uniq.append(f)
        order = {"alto": 0, "medio": 1, "info": 2}
        return sorted(uniq, key=lambda f: order[f["nivel"]])


def check(out, segments, mode, patient=None):
    """Valida a saída do modelo contra os trechos. Devolve (resultado para a tela, pontos para conferir)."""
    out = out if isinstance(out, dict) else {}
    c = _Conferencia(segments, patient)
    res = {"mode": mode, "fields": {}, "vitals": {}, "cid": [], "meds": [], "exames": [], "pendencias": []}
    if mode == "soap":
        soap = out.get("soap") if isinstance(out.get("soap"), dict) else {}
        for f in FIELDS:
            res["fields"][f] = c.frases(soap.get(f), f)
    else:
        res["fields"]["livre"] = c.frases(out.get("livre"), "livre")
    vit = out.get("vitals") if isinstance(out.get("vitals"), dict) else {}
    for k, v in vit.items():
        val = c.sinal(k, v)
        if val is not None:
            res["vitals"][k] = val
    for x in _items(out.get("cid")):
        c.cid(x, res["cid"])
    meds = _items(out.get("meds"))
    names = [" ".join(str(m.get("nome") or "").split()) for m in meds]
    res["meds"] = [c.remedio(m, nome, names) for m, nome in zip(meds, names) if nome]
    for e in _items(out.get("exames")):
        nome = " ".join(str(e.get("nome") or "").split())
        if nome:
            res["exames"].append({"nome": nome, "src": c.srcs(e)})
    pend = out.get("pendencias") if isinstance(out.get("pendencias"), list) else []
    res["pendencias"] = [_clean_out(" ".join(str(x).split()))[0] for x in pend if str(x).strip()][:20]
    for x in res["pendencias"]:
        c.flag("pendencia", "", x)
    return res, c.pontos()


def render_text(res):
    """Campos prontos para a tela: SOAP (s/o/a/p) ou texto livre."""
    def join(items):
        out = ""
        for it in items:
            out += ("\n" if it.get("par") and out else (" " if out else "")) + it["t"]
        return out
    return {k: join(v) for k, v in res["fields"].items()}


def finish(raw, segments, mode, patient=None, patient_name=""):
    """Resposta bruta do modelo → (resultado conferido, pontos para conferir, saída do modelo)."""
    try:
        out = json.loads(raw)
    except ValueError:
        out = {}
    masked = [dict(s, text=mask(s.get("text"), patient_name)) for s in segments]
    res, flags = check(out, masked, mode, patient)
    return res, flags, out


def ask_model(msgs, model=None):
    """Chamada síncrona ao modelo (o servidor roda em outra thread: o Render tem um processo só)."""
    return llm.chat(msgs, temperature=0, max_tokens=6000, model=model or config.OPENAI_SCRIBE_MODEL, json_mode=True,
                    reasoning=config.REASONING_EFFORT)


# termos de exame físico que o transcritor costuma errar ("abaulado" → "abalado"): app/data/termos_exame.txt
EXAME_KW = _linhas("termos_exame.txt")


def keywords(patient, exame=None):
    """Palavras que ajudam o transcritor a acertar: remédios, problemas e alergias do cadastro, sem dose
    (o nome do paciente não entra), e termos comuns de exame físico (EXAME_KW)."""
    p, out = patient or {}, []
    for k in ("medications", "problems", "allergies"):
        for line in re.split(r"[\n;,]+", p.get(k) or ""):
            w = re.split(r"\s+\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|g|ml|ui|%|gotas?|comp)\b|\s+\(", line.strip(), flags=re.I)[0].strip(" -•*.")
            if 3 <= len(w) <= 40:
                out.append(w)
    exame = config.SCRIBE_KW_EXAME if exame is None else exame
    return (out[:26] + (EXAME_KW if exame else []))[:50]
