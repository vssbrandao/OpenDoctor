import zipfile

from scripts import cmed_import


def _xlsx(path, linhas):
    """Planilha mínima no formato do Excel (texto compartilhado), como a da CMED."""
    textos = sorted({c for l in linhas for c in l if c})
    si = "".join(f"<si><t>{t}</t></si>" for t in textos)
    rows = ""
    for i, l in enumerate(linhas, 1):
        cs = "".join(f'<c r="{cmed_import._col(j)}{i}" t="s"><v>{textos.index(c)}</v></c>' for j, c in enumerate(l, 1) if c)
        rows += f'<row r="{i}">{cs}</row>'
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f"<sst {ns}>{si}</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{rows}</sheetData></worksheet>")


def test_marcas_e_principios_sem_o_sal(tmp_path):
    p = tmp_path / "lista.xlsx"
    _xlsx(p, [["PREÇOS MÁXIMOS DE MEDICAMENTOS"], [],
              ["SUBSTÂNCIA", "CNPJ", "LABORATÓRIO", "PRODUTO", "APRESENTAÇÃO"],
              ["DIPIRONA MONOIDRATADA;CITRATO DE ORFENADRINA;CAFEÍNA", "1", "X", "DORFLEX", "CX 10 CPR"],
              ["CLORIDRATO DE METFORMINA", "2", "Y", "GLIFAGE XR", "500 MG"],
              ["LOSARTANA POTÁSSICA", "3", "Z", "LOSARTANA POTÁSSICA", "50 MG"],
              ["LOSARTANA POTÁSSICA + HIDROCLOROTIAZIDA", "4", "W", "ARADOIS H", "50 MG"],
              ["DIPIRONA", "5", "V", "AB", "1 G"]])                          # nome curto demais: fica de fora
    m = cmed_import.build(str(p))
    assert m["dorflex"] == {"dipirona", "orfenadrina", "cafeina"}
    assert m["glifage xr"] == {"metformina"} and m["losartana potassica"] == {"losartana"}
    assert m["aradois h"] == {"losartana", "hidroclorotiazida"} and "ab" not in m
