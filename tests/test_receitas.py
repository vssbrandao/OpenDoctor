"""Receitas (aba Prescrições): rotas /prontuario/receitas*, /me/medico e a conferência de cada item
(app/prescricao.conferir). Banco em memória (tests/fake_receitas.py); nada toca banco de verdade nem a OpenAI."""
import pytest
from fastapi.testclient import TestClient

from app import auth, db, prescricao as pr, server
from tests.fake_receitas import FakeReceitas

UID, OUTRO = "u-1", "u-2"
PACIENTES = {7: {"id": 7, "key": "maria silva", "name": "Maria Silva", "birth_date": "1968-03-14", "sex": "F",
                 "allergies": "Penicilina", "problems": "", "medications": ""},
             8: {"id": 8, "key": "joao", "name": "João", "birth_date": "", "sex": "M", "allergies": "", "problems": "", "medications": ""}}
NOTAS = {70: 7, 80: 8}                                  # evolução → paciente
MEDICO = {"name": "Dra. Ana Souza", "crm": "123456", "crm_uf": "SP"}
LOS = {"nome": "Losartana", "dose": "50 mg", "posologia": "1 comprimido de 12/12 h", "quantidade": "60 comprimidos"}


@pytest.fixture
def cli(monkeypatch):
    fake = FakeReceitas({UID: dict(MEDICO)})
    fake.install(monkeypatch.setattr)
    quem = {"u": UID}
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": quem["u"], "email": "medica@exemplo.com", "sv": 0})
    donos = {7: UID, 8: UID}
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict(PACIENTES[pid]) if donos.get(pid) == uid else None)
    monkeypatch.setattr(db, "get_note", lambda uid, nid: {"id": nid, "patient_id": NOTAS[nid]} if nid in NOTAS and uid == UID else None)
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: [])
    acessos = []
    monkeypatch.setattr(db, "log_access", lambda uid, action, pid=None, nid=None, dedupe_minutes=0: acessos.append((action, pid, nid)))
    c = TestClient(server.app)
    c.fake, c.quem, c.acessos = fake, quem, acessos
    return c


def nova(cli, **kw):
    r = cli.post("/prontuario/receitas", json=dict({"patient_id": 7, "note_id": 70, "itens": [LOS]}, **kw))
    assert r.status_code == 200, r.text
    return r.json()["receita"]


def test_rascunho_cria_lista_muda_e_apaga(cli):
    rx = nova(cli)
    assert rx["status"] == "rascunho" and rx["note_id"] == 70 and rx["itens"][0]["nome"] == "Losartana"
    assert rx["itens"][0]["origem"] == "manual" and rx["itens"][0]["via"] == ""          # limpo pelo servidor
    r = cli.patch(f"/prontuario/receitas/{rx['id']}", json={"itens": [LOS, {"nome": "  "}, {"nome": "Metformina", "via": "x"}]})
    assert [i["nome"] for i in r.json()["receita"]["itens"]] == ["Losartana", "Metformina"]
    assert [x["id"] for x in cli.get("/prontuario/receitas?patient_id=7").json()["receitas"]] == [rx["id"]]
    assert cli.delete(f"/prontuario/receitas/{rx['id']}").status_code == 200
    assert cli.get("/prontuario/receitas?patient_id=7").json()["receitas"] == []


def test_renovacao_sem_consulta_e_evolucao_de_outro_paciente(cli):
    assert nova(cli, note_id=None)["note_id"] is None
    assert cli.post("/prontuario/receitas", json={"patient_id": 7, "note_id": 80}).status_code == 400   # evolução do João
    assert cli.post("/prontuario/receitas", json={"patient_id": 9}).status_code == 400


def test_receita_de_outro_medico_nao_aparece(cli):
    rx = nova(cli)
    cli.quem["u"] = OUTRO
    assert cli.patch(f"/prontuario/receitas/{rx['id']}", json={"itens": [LOS]}).status_code == 404
    assert cli.delete(f"/prontuario/receitas/{rx['id']}").status_code == 404
    assert cli.post(f"/prontuario/receitas/{rx['id']}/emitir", json={}).status_code == 404
    assert cli.get("/prontuario/receitas?patient_id=7").status_code == 400
    assert cli.patch("/prontuario/receitas/nao-e-uuid", json={}).status_code == 404


def test_emitir_separa_por_tipo_e_trava(cli):
    rx = nova(cli)
    itens = [LOS, {"nome": "Sertralina", "dose": "50 mg"}, {"nome": "Azitromicina", "dose": "500 mg"}]
    r = cli.post(f"/prontuario/receitas/{rx['id']}/emitir", json={"itens": itens})
    assert r.status_code == 200, r.text
    out = r.json()["receitas"]
    assert [(x["tipo"], [i["nome"] for i in x["itens"]]) for x in out] == [
        ("simples", ["Losartana"]), ("especial", ["Sertralina"]), ("antimicrobiano", ["Azitromicina"])]
    assert all(x["status"] == "emitida" and x["note_id"] == 70 and x["emitida_em"] for x in out) and out[0]["id"] == rx["id"]
    assert cli.acessos == [("receita_emitida", 7, 70)]
    # emitida não muda nem sai
    assert cli.patch(f"/prontuario/receitas/{rx['id']}", json={"itens": [LOS]}).status_code == 409
    assert cli.delete(f"/prontuario/receitas/{rx['id']}").status_code == 409
    assert cli.post(f"/prontuario/receitas/{rx['id']}/emitir", json={}).status_code == 409


def test_emitir_exige_dados_do_medico(cli):
    cli.fake.medicos[UID] = {"name": "Dra. Ana Souza"}
    r = cli.post(f"/prontuario/receitas/{nova(cli)['id']}/emitir", json={})
    assert r.status_code == 409 and r.json()["faltam"] == ["CRM", "UF do CRM"]


def test_emitir_recusa_o_que_pede_talao_e_receita_vazia(cli):
    r = cli.post(f"/prontuario/receitas/{nova(cli)['id']}/emitir", json={"itens": [LOS, {"nome": "Clonazepam", "dose": "2 mg"}]})
    assert r.status_code == 409 and r.json()["talao"] == ["Clonazepam: Notificação de Receita B (azul)"]
    assert cli.post(f"/prontuario/receitas/{nova(cli, itens=[])['id']}/emitir", json={}).status_code == 400


def test_cancelar_so_emitida_e_com_motivo(cli):
    rx = nova(cli)
    assert cli.post(f"/prontuario/receitas/{rx['id']}/cancelar", json={"motivo": "erro"}).status_code == 409   # rascunho
    cli.post(f"/prontuario/receitas/{rx['id']}/emitir", json={})
    assert cli.post(f"/prontuario/receitas/{rx['id']}/cancelar", json={"motivo": "  "}).status_code == 400
    r = cli.post(f"/prontuario/receitas/{rx['id']}/cancelar", json={"motivo": "Dose  errada"})
    assert r.json()["receita"]["status"] == "cancelada" and r.json()["receita"]["motivo_cancelamento"] == "Dose errada"
    assert cli.acessos[-1] == ("receita_cancelada", 7, 70)


def test_conferir_avisa_cada_item(cli):
    r = cli.post("/prontuario/receitas/conferir", json={"patient_id": 7, "itens": [
        {"nome": "Amoxicilina", "dose": "500 mg"}, {"nome": "Losartana", "dose": "500 mg"}, {"nome": "losartana potássica"},
        {"nome": "Tramadol", "dose": "50 mg"}, {"nome": "Remediox"}]})
    amox, los, los2, tram, x = r.json()["avisos"]
    assert amox["alergias"] == ["Penicilina"] and amox["tipo"] == "antimicrobiano"
    assert los["faixa"] == [12.5, 100.0] and los["repetido"] and los2["repetido"]
    assert tram["tipo"] == "especial" and tram["lista"].startswith("A2")
    assert x["nome"].startswith("Remédio fora da lista")


def test_conferir_funcao_renal():
    (met,) = pr.conferir(pr.itens_limpos([{"nome": "Metformina", "dose": "850 mg"}]), "", 38)
    assert met["renal"].startswith("TFG entre 30 e 44")


def test_medico_configuracoes(cli):
    r = cli.get("/me/medico").json()
    assert r["medico"]["crm"] == "123456" and r["faltam"] == []
    r = cli.patch("/me/medico", json={"crm": "CRM-SP 98.765", "crm_uf": "rj", "consultorio_telefone": " (11) 99999-0000 ",
                                      "especialidade": "Clínica médica", "x": "ignora"}).json()
    assert r["medico"]["crm"] == "98765" and r["medico"]["crm_uf"] == "RJ" and r["medico"]["consultorio_telefone"] == "(11) 99999-0000"
    assert cli.patch("/me/medico", json={"crm_uf": "XX"}).status_code == 400
    assert cli.patch("/me/medico", json={"name": " "}).status_code == 400
    assert cli.patch("/me/medico", json={"crm": ""}).json()["faltam"] == ["CRM"]


@pytest.mark.parametrize("metodo,rota", [("get", "/prontuario/receitas?patient_id=7"), ("post", "/prontuario/receitas"),
                                         ("post", "/prontuario/receitas/conferir"), ("get", "/me/medico"), ("patch", "/me/medico")])
def test_exige_login(monkeypatch, metodo, rota):
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    assert getattr(TestClient(server.app), metodo)(rota).status_code == 401


def test_remedios_para_sugerir(cli):
    nomes = cli.get("/prontuario/remedios").json()["nomes"]
    assert "Losartana" in nomes and "Metformina" in nomes and len(nomes) > 500 and nomes == sorted(set(nomes), key=lambda x: pr.scribe.norm(x))


def test_da_gravacao_so_o_que_continua():
    itens = pr.da_gravacao([{"nome": "losartana", "dose": "50 mg", "posologia": "12/12h", "acao": "mantido"},
                            {"nome": "metformina", "acao": "suspenso"}, {"nome": "dapagliflozina", "dose": "10 mg", "acao": "iniciado"}, "x"])
    assert [(i["nome"], i["continuo"], i["origem"]) for i in itens] == [("Losartana", True, "gravacao"), ("Dapagliflozina", False, "gravacao")]
