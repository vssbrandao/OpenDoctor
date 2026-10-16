"""Aba Prescrições: possíveis prescrições = renovação do uso contínuo (scribe.renovacao + POST /prontuario/renovacao).
Só repete o que está em "Medicações em uso", com os avisos de alergia e dose da gravação. Nada de IA, nada gravado."""
import pytest
from fastapi.testclient import TestClient

from app import auth, db, scribe, server

UID = 41
PACIENTES = {7: {"id": 7, "name": "Maria Silva", "allergies": "Dipirona\nPenicilina",
                 "medications": "Losartana 50 mg 12/12h\nAmoxicilina 500 mg 8/8h\nLosartana 500 mg 1x/dia\nDorflex 1 cp 6/6h"}}


def test_separa_nome_dose_posologia():
    a, b, c = scribe.renovacao("Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia\n\n Atorvastatina 20 mg à noite ", "")
    assert (a["nome"], a["dose"], a["posologia"]) == ("Losartana", "50 mg", "12/12h")
    assert (b["nome"], b["dose"], b["posologia"]) == ("Metformina", "850 mg", "2x/dia")
    assert (c["texto"], c["posologia"]) == ("Atorvastatina 20 mg à noite", "à noite")
    assert not any(x["alergias"] or x["faixa"] for x in (a, b, c))


def test_sem_mg_fica_tudo_na_posologia_ou_no_nome():
    insulina, spray = scribe.renovacao("Insulina NPH 20 UI à noite\nSalbutamol spray SOS", "")
    assert (insulina["nome"], insulina["dose"], insulina["posologia"]) == ("Insulina NPH", "", "20 UI à noite")
    assert (spray["nome"], spray["dose"], spray["posologia"]) == ("Salbutamol spray SOS", "", "")


def test_avisa_alergia_da_familia_e_da_marca():
    amox, dorflex, losartana = scribe.renovacao("Amoxicilina 500 mg 8/8h\nDorflex 1 cp 6/6h\nLosartana 50 mg 1x/dia", "Penicilina\nDipirona")
    assert amox["alergias"] == ["Penicilina"]                 # mesma família (betalactâmico)
    assert dorflex["alergias"] == ["Dipirona"]                # a marca leva dipirona
    assert losartana["alergias"] == []
    assert scribe.renovacao("Amoxicilina 500 mg 8/8h", "Nega alergias")[0]["alergias"] == []


def test_avisa_dose_fora_da_faixa_usual():
    (x,) = scribe.renovacao("Losartana 500 mg 1x/dia", "")
    assert x["faixa"] == [12.5, 100.0]


def test_limita_tamanho():
    itens = scribe.renovacao("\n".join("Remédio %d %s" % (i, "x" * 300) for i in range(50)), "")
    assert len(itens) == 30 and all(len(i["texto"]) <= 200 for i in itens)


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": UID, "email": "medica@exemplo.com", "sv": 0})
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict(PACIENTES[pid]) if uid == UID and pid in PACIENTES else None)
    return TestClient(server.app)


def test_rota_devolve_itens_conferidos(cli):
    r = cli.post("/prontuario/renovacao", json={"patient_id": 7})
    assert r.status_code == 200
    itens = r.json()["itens"]
    assert [i["nome"] for i in itens] == ["Losartana", "Amoxicilina", "Losartana", "Dorflex"]
    assert itens[1]["alergias"] == ["Penicilina"] and itens[2]["faixa"] == [12.5, 100.0] and itens[3]["alergias"] == ["Dipirona"]
    assert "Maria" not in r.text                               # o nome da paciente não volta


@pytest.mark.parametrize("body", [{"patient_id": 8}, {"patient_id": "x"}, {}])
def test_rota_recusa_paciente_de_outro_ou_invalido(cli, body):
    assert cli.post("/prontuario/renovacao", json=body).status_code == 400


def test_rota_exige_login(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    assert TestClient(server.app).post("/prontuario/renovacao", json={"patient_id": 7}).status_code == 401
