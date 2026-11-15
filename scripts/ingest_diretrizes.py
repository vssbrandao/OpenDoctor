"""Ingestão das diretrizes brasileiras em PDF (SBC e PCDTs do Ministério da Saúde) na base do assistente.

    python -m scripts.ingest_diretrizes --dry-run [--cache PASTA]              # baixa, extrai e mostra os chunks
    python -m scripts.ingest_diretrizes --db test --embed                      # banco de TESTES (com a marca)
    python -m scripts.ingest_diretrizes --db prod --embed --sim-producao       # produção: só com o flag explícito

O --dry-run não toca banco nem OpenAI. O --embed GASTA CRÉDITO (embeddings): só com o ok do usuário.
Baixa só as URLs fixas de FONTES (sem crawler), com timeout, teto de tamanho e conferência de que é PDF.
Idempotente: o documento é identificado pelo sha256 do texto extraído (source + content_hash); se já está no banco,
nem embeda de novo; a mesma URL com outro texto (versão nova) também não entra sozinha. Licenças conferidas e registradas em sources.yaml e em documents.license.
"""
import argparse
import hashlib
import math
import os
import re
import statistics
import sys
import tempfile
import time
import unicodedata
import urllib.parse
from collections import Counter

# ----- fontes (só estas URLs são baixadas) -----

LIC_SBC = "CC BY 4.0 (Arq Bras Cardiol/SciELO)"
LIC_PCDT = "Ato oficial (Lei 9.610/98, art. 8º, IV); gov.br CC BY-ND 3.0"

FONTES = [
    {"slug": "sbc-hipertensao-2025", "source": "sbc", "source_type": "guideline", "license": LIC_SBC,
     "title": "Diretriz Brasileira de Hipertensão Arterial – 2025", "date": "2025-10-10",
     "doi": "10.36660/abc.20250624",
     "pdf": "https://abccardiol.org/wp-content/uploads/articles_xml/0066-782X-abc-122-09-e20250624/"
            "0066-782X-abc-122-09-e20250624.x69353.pdf"},
    # o link do pedido (wp-content/uploads/2025/09/...–-2025_Port.x66747.pdf) dá 404; este é o PDF em português
    # da página do DOI, no mesmo padrão do de hipertensão
    {"slug": "sbc-dislipidemias-2025", "source": "sbc", "source_type": "guideline", "license": LIC_SBC,
     "title": "Diretriz Brasileira de Dislipidemias e Prevenção da Aterosclerose – 2025", "date": "2025-10-14",
     "doi": "10.36660/abc.20250640",
     "pdf": "https://abccardiol.org/wp-content/uploads/articles_xml/0066-782X-abc-122-09-e20250640/"
            "0066-782X-abc-122-09-e20250640.x69353.pdf"},
    {"slug": "pcdt-has-2025", "source": "conitec_pcdt", "source_type": "protocol", "license": LIC_PCDT,
     "title": "Protocolo Clínico e Diretrizes Terapêuticas da Hipertensão Arterial Sistêmica", "date": "2025-07-23",
     "ato": "Portaria SECTICS/MS nº 49, de 23/07/2025",
     "pdf": "https://www.gov.br/conitec/pt-br/midias/protocolos/pcdt-hipertensao-arterial-sistemica.pdf/@@download/file"},
    {"slug": "pcdt-dm2-2026", "source": "conitec_pcdt", "source_type": "protocol", "license": LIC_PCDT,
     "title": "Protocolo Clínico e Diretrizes Terapêuticas do Diabete Melito Tipo 2", "date": "2026-02-21",
     "ato": "Portaria SCTIE/MS nº 13, de 21/02/2026",
     "pdf": "https://www.gov.br/conitec/pt-br/midias/protocolos/2026/pcdt-diabete-melito-tipo-2/@@download/file"},
    {"slug": "pcdt-drc-2024", "source": "conitec_pcdt", "source_type": "protocol", "license": LIC_PCDT,
     "title": "Protocolo Clínico e Diretrizes Terapêuticas das Estratégias para Atenuar a Progressão da Doença Renal "
              "Crônica", "date": "2024-09-16",
     "ato": "Portaria Conjunta SAES/SECTICS nº 11, de 16/09/2024",
     "pdf": "https://www.gov.br/conitec/pt-br/midias/protocolos/"
            "pcdt-de-estrategias-para-atenuar-a-progressao-da-doenca-renal-cronica/@@display-file/file"},
]
URLS = {f["pdf"] for f in FONTES}
HOSTS = {urllib.parse.urlsplit(u).hostname for u in URLS}      # redirecionamento só dentro destes
MAX_BYTES = 30 * 1024 * 1024
TIMEOUT_S = 60                                                  # por leitura; o download inteiro tem PRAZO_S
PRAZO_S = 240
UA = "OpenDoctor-ingest/1.0 (+https://opendoctor.app)"

MIN_CHARS, MAX_CHARS = 800, 1600
EMBED_BATCH = 64
TEST_MARKER = "ambiente_de_teste"                               # o mesmo de tests/conftest.py e scripts/setup_test_db


# ----- download -----

def _e_pdf(path):
    """O arquivo já baixado é um PDF dentro do teto? (o da pasta de cache passa pelas mesmas conferências)"""
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return False
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def baixar(fonte, pasta, cliente=None):
    """Baixa o PDF da fonte (só URL de FONTES) para pasta/<slug>.pdf; reaproveita o que já está lá."""
    url = fonte["pdf"]
    if url not in URLS:
        raise ValueError("URL fora da lista de fontes")
    destino = os.path.join(pasta, fonte["slug"] + ".pdf")
    if _e_pdf(destino):
        return destino
    import httpx

    def _confere_host(req):
        if req.url.scheme != "https" or req.url.host not in HOSTS:
            raise RuntimeError(f"redirecionamento para fora das fontes: {req.url.host}")

    c = cliente or httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=15), follow_redirects=True,
                                headers={"User-Agent": UA}, event_hooks={"request": [_confere_host]})
    fim, dados = time.monotonic() + PRAZO_S, bytearray()
    try:
        with c.stream("GET", url) as r:
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            tipo = r.headers.get("content-type", "").lower()
            if "pdf" not in tipo and "octet-stream" not in tipo:
                raise RuntimeError(f"não é PDF ({tipo or 'sem content-type'})")
            if int(r.headers.get("content-length") or 0) > MAX_BYTES:
                raise RuntimeError("PDF maior que o teto")
            for parte in r.iter_bytes():
                dados += parte
                if len(dados) > MAX_BYTES:
                    raise RuntimeError("PDF maior que o teto")
                if time.monotonic() > fim:
                    raise RuntimeError("download passou do prazo")
    finally:
        if cliente is None:
            c.close()
    if not dados.startswith(b"%PDF-"):
        raise RuntimeError("conteúdo não começa com %PDF-")
    tmp = destino + ".part"
    with open(tmp, "wb") as fh:
        fh.write(dados)
    os.replace(tmp, destino)
    return destino


def extrair(path):
    """Texto de cada página (pypdf)."""
    from pypdf import PdfReader
    return [(p.extract_text() or "") for p in PdfReader(path).pages]


# ----- limpeza -----

_TROCAS = {"️": "", "­": ""," ": " ", "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "‑": "-",
           "": "•", "": "•", "▪": "•", "−": "-", "‐": "-", "\t": " "}
_NUM_PAG = re.compile(r"^(p[áa]g(ina)?\.?\s*)?\d{1,4}(\s*(de|/)\s*\d{1,4})?$", re.I)


def _normaliza(linha):
    linha = unicodedata.normalize("NFKC", linha)                     # 𝑇𝐹𝐺 → TFG, ligaduras
    for a, b in _TROCAS.items():
        linha = linha.replace(a, b)
    linha = re.sub(r"/uni[0-9A-Fa-f]{4}", "", linha)                 # nome de glifo que o pypdf deixa
    linha = re.sub(r"[-]", "•", linha)                   # marcador de lista em fonte privada
    linha = re.sub(r"(?<=[A-Za-zÀ-ü]) -(?=[A-Za-zÀ-ü])|(?<=\d) -(?=\d)", "-", linha)   # "órgãos -alvo" → "órgãos-alvo"
    linha = re.sub(r" +([,;.)])(?=\s|$)", r"\1", linha)              # "CV ," → "CV,"
    return re.sub(r" {2,}", " ", linha).strip()


def _chave(linha):
    return linha.lower()


def limpar_paginas(paginas, topo=5, pe=3):
    """Linhas de cada página sem cabeçalho/rodapé repetidos nem número de página (só nas pontas da página)."""
    pags = [[_normaliza(x) for x in p.splitlines()] for p in paginas]
    cont = Counter()
    for linhas in pags:
        cheias = [x for x in linhas if x]
        cont.update({_chave(x) for x in cheias[:topo] + cheias[-pe:]})
    corte = max(3, math.ceil(0.3 * len(pags)))
    repetida = {k for k, n in cont.items() if n >= corte}

    def lixo(x):
        return not x or _chave(x) in repetida or bool(_NUM_PAG.match(x))

    saida = []
    for linhas in pags:
        ini, fim, vistas = 0, len(linhas), 0
        while ini < fim and vistas < topo and lixo(linhas[ini]):
            vistas += bool(linhas[ini])
            ini += 1
        vistas = 0
        while fim > ini and vistas < pe and lixo(linhas[fim - 1]):
            vistas += bool(linhas[fim - 1])
            fim -= 1
        saida.append(linhas[ini:fim])
    return saida


_PREFIXOS = set("anti pós pos pré pre pró pro não bem mal auto contra extra infra inter intra micro macro multi neo "
                "pan pseudo semi sobre sub super supra ultra vice ex co".split())
_CLITICOS = set("se lhe lhes lo la los las no na nos nas me te o a os as".split())


def junta_hifen(esq, dir_, vocab):
    """Junta 'esq-' (fim de linha) com 'dir_' (início da seguinte). Hífen de verdade fica (anti-hipertensivo,
    recomenda-se); hífen de quebra de linha sai (hiperten-são → hipertensão). Decide pelo vocabulário do documento."""
    if dir_.startswith("-"):                                        # norma: hífen repetido na linha de baixo
        return esq + dir_[1:]
    raiz = esq[:-1]
    m1, m2 = re.search(r"[\wÀ-ü]+$", raiz), re.match(r"[\wÀ-ü]+", dir_)
    if not m1 or not m2:
        return esq + dir_
    a, b = m1.group(0), m2.group(0)
    com, sem = f"{a}-{b}".lower(), f"{a}{b}".lower()
    if sem in vocab and com not in vocab:
        return raiz + dir_
    if com in vocab or b.lower() in _CLITICOS or a.lower() in _PREFIXOS or not b[0].islower() \
            or any(ch.isupper() or ch.isdigit() for ch in a + b):
        return esq + dir_                                           # sigla (LDL-colesterol), prefixo, clítico
    return raiz + dir_


def junta_partidas(linha, cont):
    """'c laudicação' → 'claudicação', 'a lto' → 'alto' (o pypdf parte palavras de PDFs do Word): junta dois pedaços
    quando a palavra inteira aparece no documento bem mais vezes que o pedaço mais raro."""
    def troca(m):
        a, b = m.group(1), m.group(2)
        n = cont.get((a + b).lower(), 0)
        return a if n >= 2 and 2 * min(cont.get(a.lower(), 0), cont.get(b.lower(), 0)) <= n else m.group(0)
    return re.sub(r"(?<![\wÀ-ü-])([a-zà-ü]+) (?=([a-zà-ü]+)(?![A-Za-zÀ-ü-]))", troca, linha)


def _contagem(texto):
    return Counter(re.findall(r"[a-zà-ü]+", texto.lower()))


def _vocab(texto):
    return set(re.findall(r"[\wÀ-ü]+(?:-[\wÀ-ü]+)*", texto.lower()))


def _filtra_lixo_de_figura(linhas, run=5):
    """Tira sequências longas de linhas curtíssimas (rótulos e números de gráfico)."""
    curta = [bool(x) and len(x) <= 30 and len(x.split()) <= 3 and not x.endswith(".") and not x.startswith("•")
             and not _e_titulo_numerado(x) and not _CAB_REC.match(x) and not _SO_FORCA.match(x) for x in linhas]
    saida, i = [], 0
    while i < len(linhas):
        j = i
        while j < len(linhas) and (curta[j] or (not linhas[j] and j > i)):
            j += 1
        if sum(curta[i:j]) >= run:
            i = j
            continue
        saida.append(linhas[i])
        i += 1
    return saida


# ----- títulos e blocos -----

_MAIUS = "A-ZÁÉÍÓÚÂÊÔÃÕÇÀÜ"
_RE_NUM = re.compile(rf"^(\d{{1,2}}(?:\.\d{{1,2}}){{0,4}})(\.?)\s+([{_MAIUS}].*)$")
_CONECTORES = set("e ou de da do das dos à às a o em na no nas nos para com por sem sobre entre".split())
_FORCA = re.compile(r"\b(FORTE|CONDICIONAL|FRACA)(\s+(A FAVOR|CONTRA))?\s+(ALTA|MODERADA|BAIXA|MUITO BAIXA)\s*$")
_SO_FORCA = re.compile(r"^(FORTE|CONDICIONAL|FRACA)(\s+(A FAVOR|CONTRA))?(\s+(ALTA|MODERADA|BAIXA|MUITO BAIXA))?$")
_CAB_REC = re.compile(r"^(Recomendações?|Força da|Forca da|recomendação|Certeza da|evidência|Certeza da evidência|"
                      r"Força da recomendação|Recomendação Força da)$")
_INI_REC = re.compile(r"^Recomendações (para|sobre|no|na|nos|nas|de|do|da|dos|das|em|quanto)\b")
_REC_N = re.compile(r"^Recomendação (\d{1,2})\s*[:.–-]")
_CAPITULO = re.compile(r"^Capítulo \d{1,2}\s*[–-]\s*\S")
_LEGENDA = re.compile(r"^(Legenda|Fonte|Notas?|Adaptad[oa])\b|^[A-Z][\w\-/()αβ+]{0,15}: \S.*;")
_LEGENDA_TAB = re.compile(r"^(Legenda|Fonte|Notas?|Adaptad[oa])\b|^[A-Z][\w\-/()αβ+]{0,15}: \S")
_TABELA = re.compile(r"^(Quadro|Tabela|Figura|Fluxograma)\s+\d{1,2}(\.\d{1,2})?\.?\s*([–—-]|\.|:)?\s*\S")
_SUMARIO = re.compile(r"\.{5,}\s*\d*\s*$")
_PULA = re.compile(r"^(\d{1,2}\.?\s+)?(REFERÊNCIAS|Referências|REFERÊNCIAS BIBLIOGRÁFICAS|TERMO DE ESCLARECIMENTO|"
                   r"APÊNDICE \d+\s*[–-]\s*HISTÓRICO|HISTÓRICO DE ALTERAÇÕES|Declaração de potencial conflito)", re.I)
_VOLTA = re.compile(r"^(APÊNDICE|ANEXO)\b")
_REFS = re.compile(r"^(\d{1,2}\.?\s+)?(Referências|REFERÊNCIAS)( Bibliográficas| BIBLIOGRÁFICAS)?$")


def _inicio_refs(linhas, i):
    """linhas[i] é a referência 1 da lista final (às vezes vem antes do título 'Referências', pela ordem das colunas)?"""
    x = linhas[i]
    if not re.match(r"^1\.\s+[A-ZÀ-Ü]", x) or not re.search(r"\. |, ", x[3:]):
        return False
    return any(re.search(r"\bdoi\b|\d{4};\s?\d|\[Internet\]", y, re.I) for y in linhas[i:i + 5])


def _prosa(linhas):
    """Três linhas de texto corrido quebrado (longas, terminando no meio da frase)?"""
    return len(linhas) == 3 and all(len(y) >= 50 and re.search(r"[a-zà-ü,]$", y) for y in linhas)


def _e_titulo_numerado(x):
    m = _RE_NUM.match(x)
    if not m or len(x) > 140 or x[-1] in ".;,":
        return False
    nums, ponto, texto = m.group(1), m.group(2), m.group(3)
    if "." not in nums and not ponto:                               # "1 Hipertensão" sem ponto: linha de tabela
        return False
    if int(nums.split(".")[0]) > 30 or ". " in texto or texto.count(",") >= 2 or _SUMARIO.search(x):
        return False
    if "." not in nums and any(ch.islower() for ch in texto) and not _titulo_capitalizado(texto):
        return False                                                # "4. Avaliação do RCV geral, …": item de lista
    return sum(ch.isalpha() for ch in texto) >= 3


def _titulo_capitalizado(texto):
    longas = [p for p in texto.split() if len(p) >= 4 and p[0].isalpha()]
    return bool(longas) and sum(p[0].isupper() for p in longas) >= 0.6 * len(longas)


def _e_titulo_maiusculo(x):
    letras = [ch for ch in x if ch.isalpha()]
    if len(letras) < 10 or len(x) > 120 or x.endswith(".") or _SO_FORCA.match(x):
        return False
    if any(ch.islower() for ch in letras):
        return False
    palavras = x.split()
    return (len(palavras) >= 3 or bool(_VOLTA.match(x))) and any(len(p) >= 5 for p in palavras)


def e_titulo(x):
    return _e_titulo_numerado(x) or _e_titulo_maiusculo(x)


def _continua_titulo(titulo, prox):
    """A linha `prox` é a continuação de um título quebrado em duas linhas?"""
    if not prox or len(prox) > 80 or prox[-1] in ".;,:" or _e_titulo_numerado(prox) or _RE_NUM.match(prox):
        return False
    if titulo.isupper() or not any(ch.islower() for ch in titulo):
        return not any(ch.islower() for ch in prox) and sum(ch.isalpha() for ch in prox) >= 3
    palavras = prox.split()
    if len(palavras) > 12 or not (prox[0].isupper() or palavras[0] in _CONECTORES):
        return False
    ultima = titulo.split()[-1].lower()
    capitalizadas = all(p[0].isupper() or p.lower() in _CONECTORES or len(p) < 4 for p in palavras if p[0].isalpha())
    return capitalizadas or (ultima in _CONECTORES and len(palavras) <= 6)


class Bloco:
    __slots__ = ("tipo", "texto", "titulo")

    def __init__(self, tipo, texto, titulo=None):
        self.tipo, self.texto, self.titulo = tipo, texto, titulo      # tipo: h (título), p, t (tabela), r (recomendação)

    def __repr__(self):
        return f"Bloco({self.tipo!r}, {self.texto[:40]!r})"


def montar_blocos(linhas, vocab=None):
    """Linhas limpas → blocos. Pula sumário, frente (até '1. Introdução'), referências, termo de esclarecimento e
    histórico de alterações. Tabela e caixa de recomendação viram um bloco só (não se cortam no meio)."""
    vocab = vocab if vocab is not None else _vocab("\n".join(linhas))
    linhas = [x for x in linhas if not _SUMARIO.search(x)]
    linhas = _filtra_lixo_de_figura(linhas)
    # começa no '1. Introdução' do corpo (o da lista de autores vem seguido de 'Membros:'/'Coordenadores:')
    ini = next((i for i, x in enumerate(linhas) if re.match(r"^1\.?\s+(INTRODUÇÃO|Introdução)\s*$", x)
                and not re.match(r"^(Membros|Coordenador)", next((y for y in linhas[i + 1:i + 3] if y), ""))), 0)
    linhas = linhas[ini:]

    blocos, para, tab, rec = [], [], [], []
    principal, em_rec, pulando, legenda = None, False, False, [False]

    def junta(partes):
        txt = ""
        for x in partes:
            if not txt:
                txt = x
            elif re.search(r"[\wÀ-ü]-$", txt):
                txt = junta_hifen(txt, x, vocab)
            else:
                txt += " " + x
        return txt

    def fecha_para():
        if para:
            blocos.append(Bloco("p", junta(para)))
            para.clear()

    def fecha_tab():
        legenda[0] = False
        if tab:
            blocos.append(Bloco("t", "\n".join(tab)))
            tab.clear()

    def fecha_rec():
        if rec:
            blocos.append(Bloco("r", junta(rec)))
            rec.clear()

    def fecha_tudo():
        fecha_para()
        fecha_tab()
        fecha_rec()

    def titulo(t, sub=False):
        fecha_tudo()
        blocos.append(Bloco("h", t, f"{principal} › {t}" if sub and principal else t))

    i = 0
    while i < len(linhas):
        x = linhas[i]
        i += 1
        if pulando:
            if _VOLTA.match(x) and _e_titulo_maiusculo(x) and not _PULA.match(x):
                pulando = False
            else:
                continue
        if not x:
            if not tab:
                fecha_para()
            continue
        if _REFS.match(x) or _inicio_refs(linhas, i - 1):         # referências: pula até o próximo apêndice/anexo
            fecha_tudo()
            pulando = True
            continue
        prox = next((y for y in linhas[i:i + 2] if y), "")
        # título em maiúsculas sem número só depois de linha em branco (no meio do texto é cabeçalho de tabela/figura)
        maiusculo_solto = not _e_titulo_numerado(x) and not _VOLTA.match(x) and i >= 2 and bool(linhas[i - 2])
        if e_titulo(x) and not maiusculo_solto and not _CAB_REC.match(x) \
                and not (prox[:1].islower() and not _PULA.match(x) and not _continua_titulo(x, prox)):
            t = x
            for _ in range(2):
                if not (i < len(linhas) and _continua_titulo(t, linhas[i])):
                    break
                # continuação que termina em "da", "e"…: só se vier mais título depois (senão é o começo de uma frase)
                if linhas[i].split()[-1].lower() in _CONECTORES and \
                        not (i + 1 < len(linhas) and _continua_titulo(t + " " + linhas[i], linhas[i + 1])):
                    break
                t += " " + linhas[i]
                i += 1
            if _PULA.match(t):
                fecha_tudo()
                pulando = True
                continue
            em_rec = False
            principal = t
            titulo(t)
            continue
        if _CAPITULO.match(x) and len(x) <= 140:
            em_rec = False
            titulo(x, sub=True)
            continue
        if _INI_REC.match(x) and not x.endswith(".") and len(x) <= 180:
            t = re.sub(r"\s*(Força|Forca) da\s*$", "", x)
            for _ in range(2):                                          # título quebrado: no máximo 2 linhas curtas
                if not (i < len(linhas) and not re.search(r"(Força|Forca) da\s*$", x) and linhas[i]
                        and len(linhas[i]) <= 60 and not linhas[i].startswith("Recomenda")
                        and not _CAB_REC.match(linhas[i]) and not linhas[i].endswith(".")):
                    break
                x = linhas[i]
                t += " " + re.sub(r"\s*(Força|Forca) da\s*$", "", x)
                i += 1
            while i < len(linhas) and (_CAB_REC.match(linhas[i]) or linhas[i].startswith("Recomendação Força")):
                i += 1
            em_rec = True
            titulo(t.strip(), sub=True)
            continue
        if _CAB_REC.match(x):
            continue
        if _REC_N.match(x):
            titulo(f"Recomendação {_REC_N.match(x).group(1)}", sub=True)
            para.append(x)
            continue
        if _SO_FORCA.match(x):                                       # força solta: cola no bloco anterior
            alvo = rec or para or tab
            if alvo:
                alvo.append(x)
            elif blocos and blocos[-1].tipo != "h":
                blocos[-1].texto += " " + x
            if rec:
                fecha_rec()
            continue
        if em_rec:
            if _LEGENDA.match(x) or _TABELA.match(x):
                fecha_rec()
                em_rec = False
            else:
                rec.append(x)
                if _FORCA.search(x) or len(" ".join(rec)) > 1400:
                    fecha_rec()
                continue
        if _TABELA.match(x):
            fecha_tudo()
            tab.append(x)
            continue
        if tab and len(tab) > 1 and not legenda[0] and _prosa(linhas[i - 1:i + 2]):
            fecha_tab()                                               # tabela sem legenda: o texto corrido voltou
        if tab:
            tab.append(x)
            # a legenda fecha a tabela: termina na linha com ponto final
            if (_LEGENDA_TAB.match(x) or legenda[0]) and x.endswith("."):
                fecha_tab()
            elif _LEGENDA_TAB.match(x):
                legenda[0] = True
            elif len("\n".join(tab)) > 4000:
                fecha_tab()
            continue
        novo = x.startswith(("•", "- ", "‒ ", "– ")) or re.match(r"^[a-z]\)\s|^[a-z] [–-] ", x)
        if para and (novo or (re.search(r"[.!?:;]$", para[-1]) and (x[0].isupper() or x[0].isdigit()
                                                                       or x[0] in "“\"("))):
            fecha_para()
        para.append(x)
    fecha_tudo()
    return blocos


# ----- chunks -----

def _frases(texto):
    return [f for f in re.split(rf"(?<=[.!?])\s+(?=[{_MAIUS}0-9“(])", texto) if f]


def _quebra(bloco, teto=MAX_CHARS):
    """Bloco maior que o teto → pedaços ≤ teto: tabela por linha, texto por frase; em último caso, por palavra."""
    if len(bloco.texto) <= teto:
        return [bloco]
    sep = "\n" if bloco.tipo == "t" else " "
    partes = bloco.texto.split("\n") if bloco.tipo == "t" else _frases(bloco.texto)
    miudas = []
    for p in partes:
        if len(p) <= teto:
            miudas.append(p)
            continue
        cur = ""
        for w in p.split(" "):
            if cur and len(cur) + 1 + len(w) > teto:
                miudas.append(cur)
                cur = ""
            cur = f"{cur} {w}" if cur else w[:teto]
        if cur:
            miudas.append(cur)
    out, cur = [], ""
    for p in miudas:
        if cur and len(cur) + len(sep) + len(p) > teto:
            out.append(Bloco(bloco.tipo, cur))
            cur = ""
        cur = f"{cur}{sep}{p}" if cur else p
    if cur:
        out.append(Bloco(bloco.tipo, cur))
    return out


def montar_chunks(blocos, minimo=MIN_CHARS, teto=MAX_CHARS):
    """Blocos → [(section_title, texto)], cada um ≤ teto e, quando dá, ≥ mínimo. Um título começa chunk novo se o
    atual já tem o mínimo; texto corrido completa o chunk por frase; tabela e recomendação nunca são cortadas
    (só se sozinhas passarem do teto). O título do chunk é o da seção que mais ocupa o texto dele."""
    chunks, buf = [], []                                              # buf: [(texto, título da seção, é título?)]
    atual = None

    def tam():
        return sum(len(x) for x, _, _ in buf) + max(0, len(buf) - 1)

    def fecha():
        if not buf:
            return
        texto = "\n".join(x for x, _, _ in buf)
        if all(h for _, _, h in buf):                                 # só título (fim de seção): cola no anterior
            if chunks and len(chunks[-1][1]) + 1 + len(texto) <= teto:
                chunks[-1] = (chunks[-1][0], chunks[-1][1] + "\n" + texto)
        else:
            peso = Counter()
            for x, t, _ in buf:
                peso[t] += len(x)
            chunks.append((max(peso, key=lambda t: (peso[t], -[u for _, u, _ in buf].index(t))), texto))
        buf.clear()

    for b in blocos:
        if b.tipo == "h":
            atual = b.titulo
            if tam() >= minimo or (buf and tam() + 1 + len(b.texto) > teto):
                fecha()
            buf.append((b.texto, atual, True))
            continue
        for p in _quebra(b, teto):
            if buf and tam() + 1 + len(p.texto) > teto:
                if p.tipo == "p" and tam() < minimo:                  # completa com as primeiras frases
                    frases, cabe = _frases(p.texto), []
                    while frases and tam() + 1 + len(" ".join(cabe + frases[:1])) <= teto:
                        cabe.append(frases.pop(0))
                    if cabe:
                        buf.append((" ".join(cabe), atual, False))
                        p = Bloco("p", " ".join(frases))
                fecha()
            buf.append((p.texto, atual, False))
    fecha()
    # sobra pequena (< 200): junta com o chunk anterior ou, se não couber, com o seguinte
    out, pendente = [], None
    for t, x in chunks:
        if pendente:
            if len(pendente[1]) + 1 + len(x) <= teto:
                t, x = pendente[0] if len(pendente[1]) > len(x) else t, pendente[1] + "\n" + x
            else:
                out.append(pendente)
            pendente = None
        if len(x) < 200 and out and len(out[-1][1]) + 1 + len(x) <= teto:
            out[-1] = (out[-1][0], out[-1][1] + "\n" + x)
        elif len(x) < 200:
            pendente = (t, x)
        else:
            out.append((t, x))
    if pendente:
        out.append(pendente)
    return out


def processar(paginas, fonte=None):
    """Páginas (texto do pypdf) → (content_hash, chunks). O hash é do texto extraído, antes da limpeza."""
    bruto = "\n".join(paginas)
    linhas = [x for p in limpar_paginas(paginas) for x in p]
    cont = _contagem("\n".join(linhas))
    linhas = [junta_partidas(x, cont) for x in linhas]
    chunks = montar_chunks(montar_blocos(linhas, _vocab(bruto)))
    if fonte:
        chunks.insert(0, ("Title", fonte["title"]))                  # como no PubMed: ajuda a busca por palavra
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest(), chunks


# ----- banco -----

def _projeto(url):
    from scripts.setup_test_db import _project
    return _project(url)


def url_do_banco(alvo, sim_producao=False, env=None, prod_url=None, conectar=None):
    """URL do banco para gravar, com as travas: 'test' só com TEST_DATABASE_URL marcado como banco de testes (e que
    não seja o projeto de produção); 'prod' só com --sim-producao. Recusa com SystemExit."""
    env = os.environ if env is None else env
    if prod_url is None:
        from app import config
        prod_url = config.DATABASE_URL
    if alvo == "prod":
        if not sim_producao:
            raise SystemExit("--db prod grava na PRODUÇÃO: repita com --sim-producao para confirmar. Nada foi feito.")
        if not prod_url:
            raise SystemExit("DATABASE_URL vazio. Nada foi feito.")
        return prod_url
    if alvo != "test":
        raise SystemExit(f"--db {alvo!r} desconhecido (use test ou prod).")
    url = (env.get("TEST_DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("Defina TEST_DATABASE_URL (banco de testes). Nada foi feito.")
    if prod_url and _projeto(url) == _projeto(prod_url):
        raise SystemExit("TEST_DATABASE_URL é o mesmo projeto da produção. Nada foi feito.")
    if conectar is None:
        import psycopg
        conectar = psycopg.connect
    with conectar(url, connect_timeout=15) as c:
        marcado = c.execute("select to_regclass(%s) is not null", (f"public.{TEST_MARKER}",)).fetchone()[0]
    if not marcado:
        raise SystemExit("TEST_DATABASE_URL não tem a marca de banco de testes (pode ser produção). Nada foi feito.")
    return url


def ja_no_banco(conn, fonte, content_hash):
    """'mesmo' (source + hash já gravados), 'outra versão' (a mesma URL com outro texto: PDF novo ou outro pypdf) ou
    None. Outra versão não entra sozinha: ficariam duas cópias da mesma diretriz na busca."""
    linhas = conn.execute("select content_hash from documents where source = %s and (content_hash = %s or url = %s)",
                          (fonte["source"], content_hash, fonte["pdf"])).fetchall()
    if any(h == content_hash for (h,) in linhas):
        return "mesmo"
    return "outra versão" if linhas else None


def gravar(url, fonte, content_hash, chunks):
    """Embeda e grava um documento. Devolve (situação, n_chunks): 'gravado', 'mesmo' ou 'outra versão' (nos dois
    últimos não embeda nem grava)."""
    import psycopg
    from pgvector.psycopg import register_vector
    from app import db, embeddings
    with psycopg.connect(url, connect_timeout=15) as conn:
        register_vector(conn)
        ja = ja_no_banco(conn, fonte, content_hash)
        if ja:
            return ja, 0
        curto = fonte["title"].split(" – ")[0]
        textos = [f"{curto} — {t}\n\n{x}" if t and t != "Title" else x for t, x in chunks]
        vecs = []
        for i in range(0, len(textos), EMBED_BATCH):
            vecs += embeddings.embed(textos[i:i + EMBED_BATCH])
        novos = db.upsert_documents_bulk(conn, [(fonte["source"], fonte["source_type"], fonte["title"], fonte["pdf"],
                                                 "portuguese", fonte["date"], fonte["license"], None, content_hash)])
        did = novos.get(content_hash)
        if did is None:                                               # outro processo gravou no meio
            conn.rollback()
            return "mesmo", 0
        db.insert_chunks_bulk(conn, [(did, t, i, x, v) for i, ((t, x), v) in enumerate(zip(chunks, vecs))],
                              "portuguese")
        return "gravado", len(chunks)


# ----- CLI -----

def _amostra(t, x, n=700):
    x = x if len(x) <= n else x[:n].rstrip() + " …"
    return f"   [{t}]\n      " + x.replace("\n", "\n      ")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ingest_diretrizes")
    modo = p.add_mutually_exclusive_group(required=True)
    modo.add_argument("--dry-run", action="store_true", help="baixa, extrai e mostra os chunks; sem banco, sem OpenAI")
    modo.add_argument("--db", choices=["test", "prod"], help="grava no banco (exige --embed)")
    p.add_argument("--embed", action="store_true", help="embeda os chunks (GASTA CRÉDITO) — obrigatório com --db")
    p.add_argument("--sim-producao", action="store_true", help="confirma a gravação em produção (--db prod)")
    p.add_argument("--cache", help="pasta dos PDFs baixados (padrão: pasta temporária)")
    p.add_argument("--only", help="só a fonte com este slug")
    a = p.parse_args(argv)
    if a.db and not a.embed:
        p.error("--db exige --embed (os chunks vão com embedding)")
    if a.dry_run and (a.embed or a.sim_producao):
        p.error("--dry-run não embeda nem grava")

    url = url_do_banco(a.db, a.sim_producao) if a.db else None     # as travas antes de baixar qualquer coisa
    pasta = a.cache or tempfile.mkdtemp(prefix="diretrizes-")
    os.makedirs(pasta, exist_ok=True)
    fontes = [f for f in FONTES if not a.only or f["slug"] == a.only]
    if not fontes:
        p.error("--only não bate com nenhuma fonte")
    print(f"PDFs em {pasta}", flush=True)
    for f in fontes:
        t0 = time.monotonic()
        paginas = extrair(baixar(f, pasta))
        h, chunks = processar(paginas, f)
        tams = [len(x) for t, x in chunks[1:]] or [0]
        dentro = sum(MIN_CHARS <= n <= MAX_CHARS for n in tams)
        print(f"\n== {f['slug']} · {f['title']}\n   {len(paginas)} páginas · {len(chunks)} chunks (1 de título) · "
              f"média {statistics.mean(tams):.0f} · mediana {statistics.median(tams):.0f} · min {min(tams)} · "
              f"max {max(tams)} · {100 * dentro / len(tams):.0f}% entre {MIN_CHARS} e {MAX_CHARS} · "
              f"hash {h[:12]} · {time.monotonic() - t0:.0f}s", flush=True)
        if a.dry_run:
            corpo = chunks[1:]
            for k in sorted({len(corpo) // 5, len(corpo) // 2, (4 * len(corpo)) // 5}):
                if k < len(corpo):
                    print(_amostra(*corpo[k]))
            continue
        sit, n = gravar(url, f, h, chunks)
        print("   " + {"gravado": f"gravado: {n} chunks",
                       "mesmo": "já estava no banco (mesmo hash): nada feito",
                       "outra versão": "a mesma URL já está no banco com outro texto: nada feito (troca de versão é "
                                       "manual: apagar a antiga primeiro)"}[sit], flush=True)


if __name__ == "__main__":
    sys.exit(main())
