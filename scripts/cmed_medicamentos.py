"""Base de medicamentos da receita (aba Prescrições): a Lista de Preços da CMED/Anvisa (pública, mensal) → um arquivo
compacto só com o que a receita usa, sem preços: app/data/medicamentos.tsv.gz.

    .venv/bin/pip install openpyxl==3.1.5      # só para rodar este script (o servidor não usa)
    .venv/bin/python -m scripts.cmed_medicamentos lista_PMC__AAAAMMDD.xlsx

Baixe a planilha em gov.br/anvisa → CMED → Preços ("Lista de preços de medicamentos - PMC"). Fica de fora o que tem
restrição hospitalar. Cada linha: substância, marca (PRODUTO; no genérico é o próprio nome da substância), laboratório,
tipo (Genérico, Similar, Novo…), tarja, se foi comercializado no último ano, a dose, a forma e a quantidade da
embalagem lidas da APRESENTAÇÃO (ex.: "850 MG COM REV CT BL AL PLAS TRANS X 30" → 850 mg · comprimido revestido · 30
comprimidos) e a apresentação original.
"""
import gzip
import os
import re
import sys

SAIDA = os.path.join(os.path.dirname(__file__), "..", "app", "data", "medicamentos.tsv.gz")

# abreviações da CMED → forma farmacêutica (a mais longa primeiro); "plural" é como a quantidade é contada
FORMAS = [
    ("COM REV LIB PROL", "comprimido revestido de liberação prolongada", "comprimidos"),
    ("COM REV LIB RETARD", "comprimido revestido de liberação retardada", "comprimidos"),
    ("COM LIB PROL", "comprimido de liberação prolongada", "comprimidos"),
    ("COM LIB RETARD", "comprimido de liberação retardada", "comprimidos"),
    ("COM REV", "comprimido revestido", "comprimidos"),
    ("COM EFEV", "comprimido efervescente", "comprimidos"),
    ("COM MAST", "comprimido mastigável", "comprimidos"),
    ("COM ORODISP", "comprimido orodispersível", "comprimidos"),
    ("COM SUBL", "comprimido sublingual", "comprimidos"),
    ("COM DISP", "comprimido dispersível", "comprimidos"),
    ("COM", "comprimido", "comprimidos"),
    ("CAP DURA LIB PROL", "cápsula de liberação prolongada", "cápsulas"),
    ("CAP DURA LIB RETARD", "cápsula de liberação retardada", "cápsulas"),
    ("CAP LIB PROL", "cápsula de liberação prolongada", "cápsulas"),
    ("CAP LIB RETARD", "cápsula de liberação retardada", "cápsulas"),
    ("CAP DURA", "cápsula", "cápsulas"),
    ("CAP MOLE", "cápsula mole", "cápsulas"),
    ("CAP GEL DURA", "cápsula", "cápsulas"),
    ("CAP GEL MOLE", "cápsula mole", "cápsulas"),
    ("CAP", "cápsula", "cápsulas"),
    ("DRG", "drágea", "drágeas"),
    ("PAST", "pastilha", "pastilhas"),
    ("SUP", "supositório", "supositórios"),
    ("OVL", "óvulo", "óvulos"),
    ("ADES", "adesivo", "adesivos"),
    ("PO SUS OR", "pó para suspensão oral", ""),
    ("PO SOL OR", "pó para solução oral", ""),
    ("PO LIOF SOL INJ", "pó para solução injetável", ""),
    ("PO SOL INJ", "pó para solução injetável", ""),
    ("PO SUSP OR", "pó para suspensão oral", ""),
    ("PÓ P/ SUSP ORAL", "pó para suspensão oral", ""),
    ("SUSP INJ", "suspensão injetável", ""),
    ("SUSP OR", "suspensão oral", ""),
    ("SUSP OFT", "suspensão oftálmica (colírio)", ""),
    ("SOL INJ", "solução injetável", ""),
    ("SUS INJ", "suspensão injetável", ""),
    ("SOL OR", "solução oral", ""),
    ("SUS OR", "suspensão oral", ""),
    ("SOL GOT", "solução oral em gotas", ""),
    ("SUS GOT", "suspensão oral em gotas", ""),
    ("XPE", "xarope", ""),
    ("ELX", "elixir", ""),
    ("SOL OFT", "solução oftálmica (colírio)", ""),
    ("SUS OFT", "suspensão oftálmica (colírio)", ""),
    ("POM OFT", "pomada oftálmica", ""),
    ("SOL NAS", "solução nasal", ""),
    ("SUS NAS", "suspensão nasal", ""),
    ("SPR NAS", "spray nasal", ""),
    ("SOL SPR NAS", "spray nasal", ""),
    ("SUS AER OR", "aerossol oral (bombinha)", ""),
    ("AER", "aerossol", ""),
    ("PO INAL", "pó para inalação", ""),
    ("SOL INAL", "solução para inalação", ""),
    ("CREM DERM", "creme", ""),
    ("CREM VAG", "creme vaginal", ""),
    ("CREM", "creme", ""),
    ("EMU DERM", "emulsão", ""),
    ("POM DERM", "pomada", ""),
    ("POM", "pomada", ""),
    ("GEL DERM", "gel", ""),
    ("GEL", "gel", ""),
    ("LOC", "loção", ""),
    ("SOL TOP", "solução tópica", ""),
    ("SOL DERM", "solução tópica", ""),
    ("SH", "xampu", ""),
    ("GRAN", "granulado", ""),
    ("SOL", "solução", ""),
    ("SUS", "suspensão", ""),
]
_FORMA_RE = re.compile(r"\s(" + "|".join(re.escape(f[0]) for f in FORMAS) + r")(?=\s|$)")
_UNIDADE = {"MG": "mg", "G": "g", "MCG": "mcg", "UI": "UI", "ML": "mL", "MEQ": "mEq", "%": "%", "U": "U", "UI/ML": "UI/mL",
            "MG/ML": "mg/mL", "MG/G": "mg/g", "MCG/ML": "mcg/mL", "MG/GOTA": "mg/gota", "MCG/DOSE": "mcg/dose", "MG/DOSE": "mg/dose"}


def _dose(txt):
    """'850 MG' → '850 mg'; '10 MG/G + 0,443 MG/G' → '10 mg/g + 0,443 mg/g'; o que não reconhece fica como está."""
    partes = []
    for p in txt.split("+"):
        m = re.fullmatch(r"\s*([\d.,]+)\s*([A-Z%/]+)\s*", p)
        if not m:
            return txt.strip().lower()
        partes.append(f"{m.group(1)} {_UNIDADE.get(m.group(2), m.group(2).lower())}")
    return " + ".join(partes)


def apresentacao(ap):
    """APRESENTAÇÃO da CMED → (dose, forma, quantidade). Ex.: '850 MG COM REV CT BL AL PLAS TRANS X 30' →
    ('850 mg', 'comprimido revestido', '30 comprimidos'). O que não reconhece volta vazio."""
    ap = re.sub(r"\s+", " ", (ap or "").replace("\xa0", " ")).strip()
    m = _FORMA_RE.search(" " + ap)
    if not m:
        return "", "", ""
    abrev = m.group(1)
    forma, contagem = next((f[1], f[2]) for f in FORMAS if f[0] == abrev)
    dose = _dose(ap[:m.start()].strip()) if m.start() > 0 else ""
    qtd = ""
    n = re.search(r"\bX\s*(\d+)\s*$", ap)
    if contagem and n:
        q = int(n.group(1))
        qtd = f"{q} {contagem if q != 1 else contagem[:-1]}"
    elif not contagem:
        v = re.search(r"\bX\s*([\d.,]+)\s*(ML|G|L)\s*$", ap)                     # líquido, creme: "FR X 100 ML"
        if v:
            qtd = f"1 frasco de {v.group(1)} {_UNIDADE.get(v.group(2), v.group(2).lower())}" if v.group(2) in ("ML", "L") \
                else f"1 bisnaga de {v.group(1)} g"
    return dose, forma, qtd


def _nome(t):
    t = re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()
    return t[:1].upper() + t[1:].lower() if t else ""


def _marca(t):
    """'GLIFAGE XR' → 'Glifage XR' (siglas curtas ficam em maiúsculas)."""
    return " ".join(w if (len(w) <= 3 and w.isalpha() and w not in ("DE", "DA", "DO", "E")) else w.capitalize()
                    for w in re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip().split(" "))


def main(caminho):
    import openpyxl
    ws = openpyxl.load_workbook(caminho, read_only=True)["Lista PMC"]
    linhas = ws.iter_rows(values_only=True)
    cab = [str(h or "").strip() for h in next(linhas)]
    i = {h: k for k, h in enumerate(cab)}
    com = next(h for h in cab if h.startswith("COMERCIALIZA"))
    vistos, out, sem_forma = set(), [], 0
    for r in linhas:
        sub, prod, ap = r[i["SUBSTÂNCIA"]], r[i["PRODUTO"]], r[i["APRESENTAÇÃO"]]
        if not sub or not prod or not ap or str(r[i["RESTRIÇÃO HOSPITALAR"]]).strip() == "Sim":
            continue
        dose, forma, qtd = apresentacao(ap)
        sem_forma += not forma
        sub_n = _nome(str(sub).replace(";", " + "))
        tipo = str(r[i["TIPO DE PRODUTO (STATUS DO PRODUTO)"]] or "").strip().strip("-").strip()
        marca = "" if tipo == "Genérico" or _nome(prod) == _nome(sub) else _marca(prod)
        tarja = str(r[i["TARJA"]] or "").replace("Tarja ", "").replace("- (*)", "").strip()
        lab = _marca(r[i["LABORATÓRIO"]]).replace(" Ltda", "").replace(" S.a.", "").replace(" S/a", "")
        reg = (sub_n, marca, lab, tipo, tarja, "1" if str(r[i[com]]).strip() == "Sim" else "0", dose, forma, qtd,
               re.sub(r"\s+", " ", str(ap).replace("\xa0", " ")).strip())
        chave = reg[:3] + reg[6:9]
        if chave in vistos:
            continue
        vistos.add(chave); out.append(reg)
    out.sort(key=lambda x: (x[0], x[1], x[6], x[8]))
    with gzip.open(SAIDA, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write("# Lista de Preços CMED/Anvisa (" + os.path.basename(caminho) + "), sem preços: scripts/cmed_medicamentos.py\n")
        f.write("substancia\tmarca\tlaboratorio\ttipo\ttarja\tcomercializado\tdose\tforma\tquantidade\tapresentacao\n")
        for reg in out:
            f.write("\t".join(x.replace("\t", " ") for x in reg) + "\n")
    print(f"{len(out)} apresentações; {sem_forma} sem forma reconhecida; {os.path.getsize(SAIDA) // 1024} KB em {SAIDA}")


if __name__ == "__main__":
    main(sys.argv[1])
