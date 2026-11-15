"""New chat com um paciente escolhido (o seletor "All"): POST /ask com patient_id. O modelo recebe o perfil SEM nome
(o das Possíveis prescrições); a pergunta e o histórico passam por scribe.mask; nada do paciente vai à busca, ao
PubMed nem ao log. A busca e o modelo são simulados: nenhum teste gasta crédito nem toca o banco."""
import json

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, server

UID = 41
MARIA = {"id": 7, "key": "maria silva", "name": "Maria Silva", "birth_date": "1968-03-14", "sex": "F",
         "problems": "Hipertensão arterial\nDiabetes tipo 2", "allergies": "Dipirona",
         "medications": "Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia"}
NOTAS = [{"event_start": "2026-09-26T09:00:00", "data": {"labs": {"date": "2026-09-26", "v": {"hba1c": "6,9", "creat": "1,05"}}}}]
HIT = {"chunk_id": 1, "document_id": 1, "title": "SGLT2 inhibitors in T2D", "url": "https://pmc.example/2",
       "source_type": "pmc", "evidence": "Revisão", "publication_date": None, "section_title": None,
       "text": "SGLT2 inhibitors reduce HbA1c.", "score": 0.9, "cosine_sim": 0.9}


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": UID, "email": "medica@exemplo.com", "sv": 0})
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_ALL", False)
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict(MARIA) if uid == UID and pid == 7 else None)
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: NOTAS)
    monkeypatch.setattr(db, "list_receitas", lambda uid, pid: [{"status": "emitida", "itens": [{"nome": "Empagliflozina"}]}])
    acessos = []
    monkeypatch.setattr(db, "log_access", lambda *a, **k: acessos.append(a))
    vistos = {"plan": [], "search": [], "modelo": []}

    def plan(q, h):
        vistos["plan"].append((q, h))
        return {"medical": True, "standalone": q, "question_en": q, "terms_en": "sglt2 diabetes"}
    monkeypatch.setattr(server, "_plan", plan)

    def busca(q, k=6, fts_query=None):
        vistos["search"].append((q, fts_query))
        return {"insufficient": False, "best_sim": 0.9, "hits": [dict(HIT)], "qvec": None}
    monkeypatch.setattr(server.search, "search", busca)
    monkeypatch.setattr(server.tools, "renal_note", lambda q: None)

    def modelo(msgs):
        vistos["modelo"].append(msgs)
        yield "Pode considerar um inibidor de SGLT2 [1]. "
    monkeypatch.setattr(server.llm, "stream_chat", modelo)
    server._RL.clear()
    c = TestClient(server.app)
    c.vistos, c.acessos = vistos, acessos
    return c


def test_com_paciente_o_modelo_recebe_o_perfil_sem_nome(cli):
    r = cli.post("/ask", json={"query": "A Maria Silva pode usar empagliflozina?", "patient_id": 7,
                               "history": [{"role": "user", "content": "Oi, sobre a Maria"}]})
    assert r.status_code == 200 and "Maria" not in r.text
    msgs = json.dumps(cli.vistos["modelo"][0], ensure_ascii=False)
    assert "Maria" not in msgs and "Silva" not in msgs                       # nem na pergunta nem no histórico
    assert "Paciente escolhido pelo médico" in msgs and "mulher" in msgs and "Metformina 850 mg 2x/dia" in msgs
    assert "HbA1c 6,9 %" in msgs and "Já usou (receitas anteriores): Empagliflozina." in msgs
    # a busca e o planejamento (que gera os termos do PubMed) só veem a pergunta mascarada, sem o perfil
    q, h = cli.vistos["plan"][0]
    assert "Maria" not in q and "Maria" not in json.dumps(h, ensure_ascii=False)
    assert "Metformina" not in json.dumps(cli.vistos["search"], ensure_ascii=False)
    assert cli.acessos == [(UID, "ask_paciente", 7)]


def test_numero_do_perfil_nao_sustenta_citacao(cli, monkeypatch):
    def modelo(msgs):
        yield "A HbA1c dela é 6,9 % [1]. "
    monkeypatch.setattr(server.llm, "stream_chat", modelo)
    r = cli.post("/ask", json={"query": "Como está o controle?", "patient_id": 7})
    frases = [json.loads(l[6:])["text"] for l in r.text.splitlines() if l.startswith("data: ") and '"text"' in l]
    assert frases and "6,9" in frases[0] and "[1]" not in frases[0]        # o artigo não diz 6,9: a citação sai


def test_sem_paciente_nada_muda(cli):
    r = cli.post("/ask", json={"query": "dose de amoxicilina"})
    assert r.status_code == 200
    msgs = json.dumps(cli.vistos["modelo"][0], ensure_ascii=False)
    assert "Paciente escolhido" not in msgs and cli.acessos == []


@pytest.mark.parametrize("pid", [8, "x", "7; drop", "²", "٣", True, 10 ** 12, "", [7]])
def test_paciente_de_outro_medico_ou_invalido(cli, pid):
    assert cli.post("/ask", json={"query": "dose?", "patient_id": pid}).status_code == 400
    assert cli.vistos["modelo"] == [] and cli.acessos == []


def test_so_nas_contas_liberadas(cli, monkeypatch):
    monkeypatch.setattr(config, "SCRIBE_EMAILS", set())
    assert cli.post("/ask", json={"query": "dose?", "patient_id": 7}).status_code == 403
    monkeypatch.setattr(config, "SCRIBE_ALL", True)
    monkeypatch.setattr(config, "SCRIBE_OFF", True)
    assert cli.post("/ask", json={"query": "dose?", "patient_id": 7}).status_code == 403
    assert cli.vistos["modelo"] == []


def test_followups_com_paciente_mascaram_o_nome(cli, monkeypatch):
    vistos = []
    monkeypatch.setattr(server.llm, "chat", lambda msgs, **k: vistos.append(msgs) or "Qual a dose?\nE a TFG?\nPor quanto tempo?")
    r = cli.post("/followups", json={"query": "A Maria pode usar?", "answer": "Para a Maria Silva, sim.", "patient_id": 7})
    assert r.json()["suggestions"] and "Maria" not in json.dumps(vistos, ensure_ascii=False)
    assert cli.post("/followups", json={"query": "x", "answer": "y", "patient_id": 8}).json() == {"suggestions": []}


def test_o_log_nao_leva_o_perfil(cli, capsys):
    cli.post("/ask", json={"query": "A Maria pode usar empagliflozina?", "patient_id": 7})
    out = capsys.readouterr().out
    assert "Maria" not in out and "Metformina" not in out and "Losartana" not in out
