"""Base de medicamentos da receita (CMED/Anvisa → app/data/medicamentos.tsv.gz) e a busca da barra "Adicionar
remédio…" (app/medicamentos.py, GET /prontuario/remedios/busca). Usa o arquivo de verdade que vai no repositório."""
import pytest
from fastapi.testclient import TestClient

from app import auth, medicamentos as m, server
from scripts.cmed_medicamentos import apresentacao


@pytest.mark.parametrize("ap,esperado", [
    ("850 MG COM REV CT BL AL PLAS TRANS X 30\xa0", ("850 mg", "comprimido revestido", "30 comprimidos")),
    ("1G COM REV CT BL AL PLAS PVC TRANS X 30", ("1 g", "comprimido revestido", "30 comprimidos")),
    ("500 MG COM LIB PROL CT BL AL PLAS OPC X 10", ("500 mg", "comprimido de liberação prolongada", "10 comprimidos")),
    ("20 MG CAP DURA LIB RETARD CT FR PLAS OPC X 28", ("20 mg", "cápsula de liberação retardada", "28 cápsulas")),
    ("10 MG/G + 0,443 MG/G CREM DERM CT BG AL X 40 G", ("10 mg/g + 0,443 mg/g", "creme", "1 bisnaga de 40 g")),
    ("50 MG/ML SUS OR CT FR VD AMB X 150 ML", ("50 mg/mL", "suspensão oral", "1 frasco de 150 mL")),
    ("125 MG/5 ML PO SUS OR CT FR X 150 ML", ("125 mg/5 ml", "pó para suspensão oral", "1 frasco de 150 mL")),
    ("CT 1 KIT", ("", "", "")),
])
def test_le_a_apresentacao_da_cmed(ap, esperado):
    assert apresentacao(ap) == esperado


def test_busca_marca_e_substancia():
    glifage = m.buscar("glifage")
    assert [x["nome"] for x in glifage][:2] == ["Glifage (cloridrato de metformina)", "Glifage XR (cloridrato de metformina)"]
    g = glifage[0]
    assert g["tipo"] == "marca" and g["laboratorios"] == ["Merck"]
    doses = {a["dose"]: a for a in g["apresentacoes"]}
    assert {"500 mg", "850 mg"} <= set(doses) and "30 comprimidos" in doses["850 mg"]["quantidades"]
    metf = m.buscar("metformina")[0]
    assert metf["tipo"] == "substancia" and metf["nome"] == "Cloridrato de metformina" and metf["generico"]
    assert any(x["nome"].startswith("Glifage") for x in m.buscar("metformina glifage"))     # todas as palavras
    assert m.buscar("") == [] and m.buscar("a") == [] and m.buscar("xyzwq") == []


def test_rota_da_busca(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u-1", "email": "medica@exemplo.com", "sv": 0})
    r = TestClient(server.app).get("/prontuario/remedios/busca?q=losartana").json()["itens"]
    assert r[0]["nome"] == "Losartana potássica" and any(x["tipo"] == "marca" for x in r)
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    assert TestClient(server.app).get("/prontuario/remedios/busca?q=losartana").status_code == 401
