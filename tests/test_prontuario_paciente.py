"""O prontuário abre no paciente certo (sem banco, sem rede): a "Maria Silva" fictícia nunca captura uma Maria
Silva de verdade pelo nome, consulta de paciente excluído abre pelo nome, a evolução de uma consulta não troca de
paciente, e a tela só sugere a paciente de exemplo quando a conta tem uma."""
import os
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app import auth, db, integrations, server

MARIA = {"id": 5, "name": "Maria Silva", "key": db.EXAMPLE_KEY, "example": True}     # a de exemplo
REAL = {"id": 9, "name": "Maria Silva", "key": "maria silva", "example": False}       # homônima de verdade
PAGINA = os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-agenda.html")


def _logado(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "log_access", lambda *a, **k: None)
    monkeypatch.setattr(db, "touch_patient", lambda *a, **k: None)
    return TestClient(server.app)


def _pacientes(monkeypatch):
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict({5: MARIA, 9: REAL}[pid])
                        if uid == "u1" and pid in (5, 9) else None)


def test_consultas_da_de_exemplo_nunca_vem_pelo_nome(monkeypatch):
    c = _logado(monkeypatch)
    _pacientes(monkeypatch)
    pedidos = []
    monkeypatch.setattr(db, "find_patients", lambda uid, name: [dict(REAL)])
    monkeypatch.setattr(db, "connected_providers", lambda uid: {"google": "ana@gmail.com"})
    monkeypatch.setattr(db, "notes_by_event", lambda uid, ids: {})
    monkeypatch.setattr(integrations, "patient_events", lambda uid, prov, pid, name: pedidos.append((pid, name)) or [])
    assert c.post("/prontuario/visits", json={"patient_id": 5}).json() == {"connected": True, "visits": []}
    assert c.post("/prontuario/visits", json={"patient_id": 9}).json() == {"connected": True, "visits": []}
    assert pedidos == [(5, None), (9, "Maria Silva")]          # eventos antigos "— Maria Silva" só para a real


def test_consulta_de_paciente_excluido_abre_pelo_nome(monkeypatch):
    c = _logado(monkeypatch)
    novo = {"id": 12, "name": "João Teste", "key": "joao teste", "example": False}
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: None)                     # o id do evento não existe mais
    monkeypatch.setattr(db, "ensure_patient", lambda uid, name: (dict(novo), True))
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: [])
    monkeypatch.setattr(db, "has_example", lambda uid: False)
    r = c.post("/prontuario/list", json={"patient_id": 3, "patient": "João Teste"})
    assert r.status_code == 200 and r.json()["patient"]["id"] == 12 and "key" not in r.json()["patient"]
    assert c.post("/prontuario/list", json={"patient_id": 3}).status_code == 400          # sem nome: não adivinha

    def homonimos(uid, name):
        raise db.AmbiguousPatient()
    monkeypatch.setattr(db, "ensure_patient", homonimos)
    r = c.post("/prontuario/list", json={"patient_id": 3, "patient": "João Teste"})
    assert r.status_code == 409 and r.json()["ambiguous"]


def test_lista_diz_se_a_conta_tem_a_de_exemplo(monkeypatch):
    c = _logado(monkeypatch)
    _pacientes(monkeypatch)
    tem = {"v": True}
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: [])
    monkeypatch.setattr(db, "has_example", lambda uid: tem["v"])
    assert c.post("/prontuario/list", json={"patient_id": 9}).json()["has_example"] is True
    tem["v"] = False                                            # conta antiga, ou a de exemplo foi excluída
    assert c.post("/prontuario/list", json={"patient_id": 9}).json()["has_example"] is False
    assert c.post("/prontuario/list", json={"patient_id": 5}).json()["has_example"] is True


def test_evolucao_de_outro_paciente_na_consulta_da_409_proprio(monkeypatch):
    c = _logado(monkeypatch)
    _pacientes(monkeypatch)

    def outro(*a, **k):
        raise db.NoteOtherPatient()

    def finalizada(*a, **k):
        raise db.NoteLocked()
    monkeypatch.setattr(db, "upsert_note", outro)
    r = c.post("/prontuario/notes", json={"patient_id": 9, "event_id": "ev1", "content": "S: dor"})
    assert r.status_code == 409 and r.json()["other_patient"] is True
    monkeypatch.setattr(db, "upsert_note", finalizada)
    r = c.post("/prontuario/notes", json={"patient_id": 9, "event_id": "ev1", "content": "S: dor"})
    assert r.status_code == 409 and "other_patient" not in r.json()


# ===== a página =====
def _html():
    with open(PAGINA, encoding="utf-8") as f:
        return f.read()


def test_agenda_nao_liga_a_de_exemplo_pelo_nome():
    """sameName/byKey da página (rodados no node): digitar "Maria Silva" nunca escolhe a fictícia sozinho."""
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node")
    html = _html()
    pnorm = re.search(r"^ *function pnorm\(v\).*$", html, re.M).group(0)
    busca = re.search(r"^ *function sameName\(name\) \{.*?^ *function byKey\(name\)[^\n]*", html, re.M | re.S).group(0)
    js = pnorm + "\n" + busca + """
      var patients = [{ id: 5, name: 'Maria Silva', example: true }, { id: 2, name: 'Ana Souza' }], out = [];
      out.push(byKey('Maria Silva'), sameName('maria  silva').length, byKey('Ana Souza').id);
      patients.push({ id: 9, name: 'Maria Silva' });
      out.push(byKey('Maria Silva').id, sameName('Maria Silva').length);
      console.log(JSON.stringify(out));"""
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[null,0,2,9,1]"


def test_agenda_lista_a_de_exemplo_por_ultimo_sem_destaque():
    """Lista do campo Paciente (exampleLast rodado no node): a fictícia vai para o fim e nunca é a do Enter, então
    "Maria Silva" + Enter cria/escolhe a de verdade; com o mouse ou as setas ela continua escolhível."""
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node")
    html = _html()
    m = re.search(r"^ *function exampleLast\(hits\) \{.*?^ *\}\n", html, re.M | re.S)
    assert m, "a lista do campo Paciente não põe a de exemplo por último"
    js = m.group(0) + """
      var M = { id: 5, name: 'Maria Silva', example: true }, A = { id: 2, name: 'Ana Souza' }, R = { id: 9, name: 'Maria Silva' };
      var ids = function (o) { return [o.list.map(function (p) { return p.id; }), o.first]; };
      console.log(JSON.stringify([ids(exampleLast([M, A])), ids(exampleLast([M])), ids(exampleLast([M, R, A])), ids(exampleLast([]))]));"""
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    # só a de exemplo: a padrão é a opção seguinte ("Criar paciente"); com uma de verdade, é ela
    assert r.stdout.strip() == "[[[2,5],0],[[5],1],[[9,2,5],0],[[],0]]"
    # a lista usa a ordem, o destaque e o Enter sem destaque vão para essa opção (não para a primeira da lista)
    assert "exampleLast(list.filter(" in html and "plFirst = ord.first;" in html
    assert "markP(plFirst)" in html and "markP(0)" not in html
    assert "plItems[plActive >= 0 ? plActive : plFirst]" in html


def test_pagina_exemplo_e_troca_de_paciente():
    html = _html()
    # a lista do campo Paciente marca a fictícia
    assert re.search(r"option\('', initialsOf\(p\.name\), p\.name \+ \(p\.example \? ' \(exemplo\)' : ''\)", html)
    # Pacientes: a de exemplo tem a lixeira, mesmo com o histórico fictício
    assert re.search(r"if \(!p\.notes \|\| p\.example\) acts\.appendChild\(iconBtn\('Excluir'", html)
    # 409 de outro paciente: mensagem própria, sem recarregar (recarregar reenviava o rascunho e dava 409 de novo)
    ramo = re.search(r"res\.j\.other_patient\) \{(.*?)\} else if \(res\.status === 409\) \{\n([^\n]*)", html, re.S)
    assert ramo and "load()" not in ramo.group(1) and "outro paciente" in ramo.group(1)
    assert re.search(r"apos409 = true;.*load\(\)", ramo.group(2))
    assert "reenvia = !apos409; apos409 = false;" in html and "if (d && reenvia && !locked()" in html
    # "experimente na paciente de exemplo" só quando a conta tem uma
    assert html.count("experimente na paciente de exemplo") == 1
    assert "(temExemplo ? ': experimente na paciente de exemplo.' : '.')" in html
    assert "temExemplo = !!res.j.has_example;" in html
