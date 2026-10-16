"""Gera app/data/cmed.tsv a partir da lista de preços da CMED/Anvisa (planilha PMC, pública, em
https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos). Usado pelo escriba para conhecer os nomes
comerciais e saber o que cada marca leva (alergia a dipirona → aviso em qualquer marca com dipirona).

  python -m scripts.cmed_import /caminho/lista_PMC__AAAAMMDD.xlsx

Lê o .xlsx só com a biblioteca padrão (é um zip de XML). A planilha não entra no git; o .tsv gerado entra.
Cada linha do .tsv: marca<TAB>princípio ativo; princípio ativo… (sem sal: "cloridrato de metformina" → metformina).
"""
import os
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data", "cmed.tsv")

# sal, hidratação e forma química não dizem o remédio: saem do nome do princípio ativo
SAL = set("""cloridrato dicloridrato bromidrato iodidrato maleato dimaleato besilato mesilato succinato hemissuccinato tartarato
bitartarato citrato fumarato hemifumarato sulfato fosfato difosfato acetato diacetato propionato dipropionato valerato furoato
butirato lactato gluconato glicinato aspartato nitrato oxalato pamoato palmitato estearato tosilato embonato hiclato docusato
benzoato salicilato trometamol meglumina sodico sodica dissodico dissodica potassico potassica calcico calcica magnesico
magnesica zinco ferroso ferrico monoidratado monoidratada diidratado diidratada triidratado triidratada hemi-hidratado
hidratado hidratada anidro anidra sesqui-hidratado de do da e""".split())
# "princípio" que não é remédio de verdade ou não serve para conferir nome
NAO = re.compile(r"^(associacao|associado|extrato|oleo|tintura|vitaminas?|sais minerais|polivitaminico)")


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", s))


def ativo(s):
    """'CLORIDRATO DE METFORMINA' → 'metformina'; 'LOSARTANA POTÁSSICA' → 'losartana'."""
    t = [w for w in norm(s).split() if w not in SAL]
    return " ".join(t)


def rows(path):
    """Linhas da primeira planilha, como listas de texto (lê em fluxo: a planilha tem dezenas de milhares de linhas)."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for _, el in ET.iterparse(z.open("xl/sharedStrings.xml")):
                if el.tag == NS + "si":
                    shared.append("".join(x.text or "" for x in el.iter(NS + "t")))
                    el.clear()
        sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
        for _, el in ET.iterparse(z.open(sheet)):
            if el.tag != NS + "row":
                continue
            out = {}
            for c in el.iter(NS + "c"):
                col = re.match(r"[A-Z]+", c.get("r", "")).group(0)
                v = c.find(NS + "v")
                if c.get("t") == "s" and v is not None:
                    txt = shared[int(v.text)]
                elif c.get("t") == "inlineStr":
                    txt = "".join(x.text or "" for x in c.iter(NS + "t"))
                else:
                    txt = v.text if v is not None else ""
                out[col] = txt or ""
            el.clear()
            if out:
                idx = lambda k: sum((ord(ch) - 64) * 26 ** i for i, ch in enumerate(reversed(k)))
                n = max(idx(k) for k in out)
                yield [out.get(_col(i), "") for i in range(1, n + 1)]


def _col(i):
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def build(path):
    head, marcas = None, {}
    for r in rows(path):
        if head is None:
            h = [norm(x) for x in r]
            if "substancia" in h and "produto" in h:
                head = {k: h.index(k) for k in ("substancia", "produto")}
            continue
        sub, prod = r[head["substancia"]] if head["substancia"] < len(r) else "", r[head["produto"]] if head["produto"] < len(r) else ""
        marca = norm(prod)
        ativos = [a for a in (ativo(x) for x in re.split(r"[;+]", sub)) if a and not NAO.match(a)]
        if len(marca) < 4 or not ativos:
            continue
        marcas.setdefault(marca, set()).update(ativos)
    if head is None:
        sys.exit("não achei o cabeçalho (SUBSTÂNCIA, PRODUTO) na planilha")
    return marcas


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    marcas = build(sys.argv[1])
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(f"# Gerado por scripts/cmed_import.py de {os.path.basename(sys.argv[1])} (lista de preços CMED/Anvisa).\n")
        f.write("# marca<TAB>princípios ativos (sem o sal), separados por \"; \". Não editar à mão: rodar o script de novo.\n")
        for m in sorted(marcas):
            f.write(f"{m}\t{'; '.join(sorted(marcas[m]))}\n")
    print(f"{len(marcas)} marcas → {OUT}")


if __name__ == "__main__":
    main()
