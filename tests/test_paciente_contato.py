"""Novo paciente com e-mail, telefone, particular/convênio e plano (sem banco, sem rede): o servidor valida e limpa os
campos, o plano só existe no convênio, a criação só com o nome continua igual, sem a migração 0021 o cadastro com esses
campos espera (503) e o erro do banco ao gravar nunca vai para o log com os dados do paciente."""
from fastapi.testclient import TestClient

from app import auth, db, server

PAC = {"id": 7, "name": "Joana Teste", "key": "joana teste", "example": False}


def _logado(monkeypatch, criados):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "log_access", lambda *a, **k: None)
    monkeypatch.setattr(db, "find_by_cpf", lambda *a, **k: None)
    monkeypatch.setattr(db, "find_patients", lambda uid, name: [])

    def criar(uid, name, birth_date=None, sex=None, cpf=None, phone=None, key=None, email=None, coverage=None,
              health_plan=None):
        criados.append({"uid": uid, "name": name, "birth_date": birth_date, "sex": sex, "phone": phone, "email": email,
                        "coverage": coverage, "health_plan": health_plan})
        return dict(PAC, email=email, coverage=coverage, health_plan=health_plan, phone=phone)
    monkeypatch.setattr(db, "create_patient", criar)
    return TestClient(server.app)


def test_so_com_o_nome_continua_igual(monkeypatch):
    criados = []
    c = _logado(monkeypatch, criados)
    r = c.post("/patients", json={"name": "Joana Teste"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert criados == [{"uid": "u1", "name": "Joana Teste", "birth_date": None, "sex": None, "phone": None,
                        "email": None, "coverage": None, "health_plan": None}]


def test_campos_novos_limpos_e_gravados(monkeypatch):
    criados = []
    c = _logado(monkeypatch, criados)
    r = c.post("/patients", json={"name": "  Joana   Teste ", "email": "  Joana.Teste@Exemplo.COM ", "phone": " (11)  91234-5678 ",
                                  "coverage": "convenio", "health_plan": "  Unimed   Nacional  "})
    assert r.status_code == 200
    assert criados[0]["name"] == "Joana Teste" and criados[0]["email"] == "joana.teste@exemplo.com"
    assert criados[0]["phone"] == "(11) 91234-5678" and criados[0]["coverage"] == "convenio"
    assert criados[0]["health_plan"] == "Unimed Nacional"
    assert r.json()["patient"]["health_plan"] == "Unimed Nacional" and "key" not in r.json()["patient"]


def test_particular_nao_tem_plano(monkeypatch):
    criados = []
    c = _logado(monkeypatch, criados)
    assert c.post("/patients", json={"name": "Joana Teste", "coverage": "particular", "health_plan": "Unimed"}).status_code == 200
    assert criados[0]["coverage"] == "particular" and criados[0]["health_plan"] is None
    assert c.post("/patients", json={"name": "Joana Teste", "health_plan": "Unimed"}).status_code == 200   # sem escolha
    assert criados[1]["health_plan"] == "Unimed"         # só o plano (sem escolher): fica como veio; a tela não manda assim


def test_validacao(monkeypatch):
    criados = []
    c = _logado(monkeypatch, criados)
    casos = [({"email": "joana@"}, "e-mail inválido"), ({"email": "sem arroba.com"}, "e-mail inválido"),
             ({"coverage": "sus"}, "escolha particular ou convênio"),
             ({"coverage": ["convenio"]}, "escolha particular ou convênio"), ({"coverage": {"a": 1}}, "escolha particular ou convênio"),
             ({"email": "a" * 60 + "@" + "b" * 189 + ".com.br"}, "e-mail inválido"),     # 257: cortar daria outro endereço
             ({"coverage": "convenio"}, "informe o plano do convênio"),
             ({"coverage": "convenio", "health_plan": "   "}, "informe o plano do convênio")]
    for extra, erro in casos:
        r = c.post("/patients", json=dict({"name": "Joana Teste"}, **extra))
        assert r.status_code == 400 and r.json()["error"] == erro, (extra, r.json())
    assert criados == []                                   # nada gravado com campo inválido


def test_editar_convenio_sem_mandar_o_plano_nao_apaga(monkeypatch):
    """PATCH parcial: trocar para convênio sem mandar o plano não dá erro (o plano que já existe fica); particular apaga."""
    c = _logado(monkeypatch, [])
    vistos = []
    monkeypatch.setattr(db, "update_patient", lambda uid, pid, fields: vistos.append(dict(fields)) or dict(PAC))
    assert c.patch("/patients/7", json={"coverage": "convenio"}).status_code == 200
    assert c.patch("/patients/7", json={"coverage": "particular"}).status_code == 200
    assert c.patch("/patients/7", json={"coverage": "convenio", "health_plan": ""}).status_code == 400
    assert vistos == [{"coverage": "convenio"}, {"coverage": "particular", "health_plan": None}]


def test_sem_a_migracao_espera(monkeypatch):
    c = _logado(monkeypatch, [])

    def falta(*a, **k):
        raise db.MigracaoPendente("0021_paciente_contato.sql")
    monkeypatch.setattr(db, "create_patient", falta)
    monkeypatch.setattr(db, "update_patient", falta)
    r = c.post("/patients", json={"name": "Joana Teste", "email": "joana@exemplo.com"})
    assert r.status_code == 503 and "ainda não está disponível" in r.json()["error"]
    assert c.patch("/patients/7", json={"email": "joana@exemplo.com"}).status_code == 503


def test_erro_do_banco_nao_vai_ao_log_com_os_dados(monkeypatch, capsys):
    c = _logado(monkeypatch, [])

    def quebra(*a, **k):                                   # como o psycopg: a mensagem traz a linha inteira
        raise RuntimeError('new row violates check constraint DETAIL: Failing row contains (Joana Teste, joana@exemplo.com, Unimed)')
    monkeypatch.setattr(db, "create_patient", quebra)
    monkeypatch.setattr(db, "update_patient", quebra)
    r = c.post("/patients", json={"name": "Joana Teste", "email": "joana@exemplo.com", "coverage": "convenio", "health_plan": "Unimed"})
    assert r.status_code == 500 and r.json() == {"error": "não foi possível criar o paciente"}
    assert c.patch("/patients/7", json={"email": "joana@exemplo.com"}).status_code == 500
    saida = capsys.readouterr()
    log = saida.out + saida.err
    assert "RuntimeError" in log and "joana" not in log.lower() and "unimed" not in log.lower()


def test_contato_nao_vai_ao_modelo():
    """A gravação e as possíveis prescrições montam o perfil campo a campo: e-mail, convênio e plano não entram."""
    from app import prescricao
    p = {"id": 7, "name": "Joana Teste", "birth_date": "1980-01-01", "sex": "F", "problems": "Asma", "medications": "",
         "allergies": "", "phone": "(11) 91234-5678", "email": "joana@exemplo.com", "coverage": "convenio",
         "health_plan": "Unimed Nacional"}
    texto = str(prescricao.perfil(p, []))
    for dado in ("joana@exemplo.com", "Unimed", "convenio", "91234"):
        assert dado not in texto, dado
