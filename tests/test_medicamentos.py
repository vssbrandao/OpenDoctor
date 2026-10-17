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


@pytest.mark.parametrize("d,esperado", [
    ("(100,0 + 25,0) mg", "100 mg + 25 mg"), ("(100+25) mg", "100 mg + 25 mg"), ("50 mg / ml", "50 mg/mL"),
    ("500 mg pó liof", "500 mg"), ("12,5 mg", "12,5 mg"), ("29 ui/g + 3 mg/g", "29 UI/g + 3 mg/g"), ("", ""),
])
def test_a_dose_num_jeito_so(d, esperado):
    assert m.dose_limpa(d) == esperado


def test_numero_na_busca_filtra_a_dose():
    r = m.buscar("losartana 50")
    assert r[0]["nome"] == "Losartana potássica" and [a["dose"] for a in r[0]["apresentacoes"]] == ["50 mg"]
    assert all(any("50" in a["dose"] for a in x["apresentacoes"]) for x in r)
    assert [a["dose"] for a in m.buscar("amoxicilina 500mg")[0]["apresentacoes"]] == ["500 mg"]
    assert m.buscar("losartana 150") == [] and m.buscar("500") == []         # dose sem nome não busca
    doses = [a["dose"] for a in m.buscar("losartana")[1]["apresentacoes"]]   # a mesma dose escrita de 3 jeitos vira uma
    assert doses.count("100 mg + 25 mg") == 1


def test_a_busca_avisa_a_alergia_do_paciente(monkeypatch):
    from app import db
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u-1", "email": "medica@exemplo.com", "sv": 0})
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: {"id": pid, "allergies": "Penicilina"} if uid == "u-1" else None)
    r = TestClient(server.app).get("/prontuario/remedios/busca?q=amoxicilina&patient_id=7").json()["itens"]
    assert r[0]["alergias"] == ["Penicilina"]
    assert "alergias" not in TestClient(server.app).get("/prontuario/remedios/busca?q=amoxicilina").json()["itens"][0]
