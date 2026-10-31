"""Só médicos criam conta: o cliente do CFM (respostas prontas, sem rede), o Registro profissional do cadastro por e-mail
e pelo Google, a espera das contas pendentes, a página de cadastros dos administradores e a confirmação das contas
aprovadas à mão. Nada aqui fala com o CFM, com o banco ou com o Resend (tests/conftest.py)."""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth, cfm, db, mailer, server
from tests.test_login import PW, REG, _client, _Fake, _novo, _user

CHAVE = "AbC12345"
CPF = "52998224725"


# ===================== cliente do CFM =====================

def _medico_xml(nome="ANA MARIA DE LIMA", situacao="A", crm="123456", uf="SP"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ConsultarResponse xmlns:ns2="http://servico.cfm.org.br/"><dadosMedico>
<crm>{crm}</crm><dataAtualizacao>01/10/2026</dataAtualizacao>
<especialidade>CARDIOLOGIA - RQE Nº: 1234</especialidade><especialidade>CLÍNICA MÉDICA - RQE Nº: 99</especialidade>
<nome>{nome}</nome><situacao>{situacao}</situacao><tipoInscricao>P</tipoInscricao><uf>{uf}</uf>
</dadosMedico></ns2:ConsultarResponse></S:Body></S:Envelope>"""


def _erro_xml(cod):
    return f"""<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ConsultarResponse xmlns:ns2="http://servico.cfm.org.br/"><dadosMedico><codigoErro>{cod}</codigoErro>
</dadosMedico></ns2:ConsultarResponse></S:Body></S:Envelope>"""


def _validar_xml(valor):
    return f"""<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ValidarResponse xmlns:ns2="http://servico.cfm.org.br/"><resultadoConsulta>{valor}</resultadoConsulta>
</ns2:ValidarResponse></S:Body></S:Envelope>"""


@pytest.fixture
def ws(monkeypatch):
    """Web service do CFM simulado: cada pedido recebe a próxima resposta da fila (texto XML, status HTTP ou exceção)."""
    monkeypatch.setenv("CFM_CHAVE", CHAVE)
    st = {"fila": [], "pedidos": []}

    def handler(request):
        st["pedidos"].append(request)
        r = st["fila"].pop(0) if st["fila"] else _erro_xml("2010")
        if isinstance(r, Exception):
            raise r
        if isinstance(r, int):
            return httpx.Response(r, text="erro")
        return httpx.Response(200, text=r, headers={"content-type": "text/xml; charset=utf-8"})
    monkeypatch.setattr(cfm, "_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(cfm.time, "sleep", lambda s: None)
    return st


def test_consultar_le_as_tags_conhecidas_e_monta_o_pedido_certo(ws, capsys):
    ws["fila"] = [_medico_xml()]
    r = cfm.consultar("1234", "RJ")
    assert r["status"] == "ok"
    m = r["medico"]
    assert (m["nome"], m["situacao"], m["uf"], m["atualizado"]) == ("ANA MARIA DE LIMA", "A", "SP", "01/10/2026")
    assert m["especialidades"] == ["CARDIOLOGIA - RQE Nº: 1234", "CLÍNICA MÉDICA - RQE Nº: 99"]
    p = ws["pedidos"][0]
    assert str(p.url) == cfm.URL and p.method == "POST"
    assert p.headers["soapaction"] == '""' and p.headers["content-type"] == "text/xml; charset=utf-8"
    corpo = p.content.decode()
    assert "<ser:Consultar>" in corpo and "<crm>1234</crm>" in corpo and "<uf>RJ</uf>" in corpo
    assert f"<chave>{CHAVE}</chave>" in corpo and CHAVE not in str(p.url)      # a chave vai só no corpo
    assert CHAVE not in capsys.readouterr().out                                # e nunca no log


def test_consultar_erros(ws):
    ws["fila"] = [_erro_xml("8101")]
    assert cfm.consultar("1", "SP") == {"status": "nao_encontrado"}
    for cod in ("3010", "4000", "4010", "4020"):                    # chave ou pedido: não diz nada do médico
        ws["fila"], ws["pedidos"] = [_erro_xml(cod)], []
        assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": cod} and len(ws["pedidos"]) == 1
    for cod in ("2010", "2030", "2040"):                            # passageiro: tenta mais uma vez
        ws["fila"], ws["pedidos"] = [_erro_xml(cod), _medico_xml()], []
        assert cfm.consultar("1", "SP")["status"] == "ok" and len(ws["pedidos"]) == 2
        ws["fila"], ws["pedidos"] = [_erro_xml(cod), _erro_xml(cod)], []
        assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": cod} and len(ws["pedidos"]) == 2
    ws["fila"] = [500]
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = [httpx.ConnectError("sem rede")]
    assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": "rede"}
    ws["fila"] = ['<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>']               # XML com entidades: nem lê
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = ["isto não é xml"]
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = ["<S:Envelope xmlns:S='x'><S:Body><dadosMedico><crm>1</crm></dadosMedico></S:Body></S:Envelope>"]
    assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": "resposta"}   # sem nome e situação


def test_validar(ws, capsys):
    ws["fila"] = [_validar_xml("true")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985") == {"status": "ok", "valido": True}
    corpo = ws["pedidos"][0].content.decode()
    assert "<ser:Validar>" in corpo and f"<cpf>{CPF}</cpf>" in corpo and "<dataNascimento>12/05/1985</dataNascimento>" in corpo
    ws["fila"] = [_validar_xml("false")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985") == {"status": "ok", "valido": False}
    ws["fila"] = [_erro_xml("2040"), _erro_xml("2040")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985")["status"] == "indisponivel"
    ws["fila"] = [_validar_xml("talvez")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985")["status"] == "indisponivel"
    out = capsys.readouterr().out
    assert CPF not in out and "12/05/1985" not in out and CHAVE not in out and "[cfm] Validar" in out


def test_sem_chave_nao_chama_o_cfm(monkeypatch):
    chamou = []
    monkeypatch.setattr(cfm, "_TRANSPORT", httpx.MockTransport(lambda r: chamou.append(r) or httpx.Response(200)))
    assert not cfm.configured()
    assert cfm.consultar("1", "SP")["status"] == "indisponivel" and cfm.validar("1", "SP", CPF, "01/01/1980")["status"] == "indisponivel"
    assert chamou == []


def test_separa_crm_e_uf():
    casos = {("CRM-SP 123456", ""): ("123456", "SP"), ("CRM/SP 123.456", ""): ("123456", "SP"),
             ("SP 123456", ""): ("123456", "SP"), ("123456/SP", ""): ("123456", "SP"), ("123456-SP", ""): ("123456", "SP"),
             ("52-1234/RJ", ""): ("1234", "RJ"), ("52-1234", "RJ"): ("1234", "RJ"), ("1234567-P/SP", ""): ("1234567", "SP"),
             ("1234567-P", "mg"): ("1234567", "MG"), ("300-EMFE-1234567", "SP"): ("1234567", "SP"),
             ("123456", "sp"): ("123456", "SP"), ("CRMSP123456", ""): ("123456", "SP"), ("crm-ce 4321", "SP"): ("4321", "CE"),
             ("52-1234", "SP"): ("521234", "SP")}                        # o 52- só cai no RJ
    for (texto, uf), esperado in casos.items():
        assert cfm.separa_crm(texto, uf) == esperado, texto
    assert cfm.crm_numero("0012345") == "12345" and cfm.crm_numero("1234567") == "1234567"
    for ruim in ("", "0", "12345678", "12a"):
        assert cfm.crm_numero(ruim) is None, ruim


def test_nome_confere_com_o_cfm():
    assert cfm.nome_confere("Ana Lima", "ANA MARIA DE LIMA")
    assert cfm.nome_confere("Dra. Ana  Maria Lima", "ANA MARIA DE LIMA")              # tratamento e espaços
    assert cfm.nome_confere("José da Conceição", "JOSE DA CONCEICAO SANTOS")           # acentos e conectores
    assert cfm.nome_confere("ana de lima", "Ana Maria Lima")
    assert not cfm.nome_confere("Ana Souza", "ANA MARIA DE LIMA")                     # sobrenome que não está lá
    assert not cfm.nome_confere("Maria Lima", "ANA MARIA DE LIMA")                    # primeiro nome diferente
    assert not cfm.nome_confere("Ana", "ANA MARIA DE LIMA")                           # só uma palavra
    assert not cfm.nome_confere("Ana de", "ANA MARIA DE LIMA")


# ===================== cadastro por e-mail =====================

def _cfm_simulado(monkeypatch, consulta=None, valido=True, em_uso=False):
    """CFM com chave: Consultar devolve `consulta` (padrão: médico regular ANA MARIA DE LIMA) e Validar, `valido`."""
    monkeypatch.setattr(cfm, "configured", lambda: True)
    st = {"consultas": [], "validacoes": []}

    def consultar(crm, uf):
        st["consultas"].append((crm, uf))
        return consulta or {"status": "ok", "medico": {"nome": "ANA MARIA DE LIMA", "situacao": "A"}}

    def validar(crm, uf, cpf, nasc):
        st["validacoes"].append((crm, uf, cpf, nasc))
        return valido if isinstance(valido, dict) else {"status": "ok", "valido": valido}
    monkeypatch.setattr(cfm, "consultar", consultar)
    monkeypatch.setattr(cfm, "validar", validar)
    monkeypatch.setattr(db, "crm_in_use", lambda crm, uf: em_uso)
    return st


def _avisos(monkeypatch, fake):
    monkeypatch.setattr(mailer, "send_crm_pending", lambda admins, nome, crm, uf: fake.sent.append(("admins", tuple(admins), nome, crm, uf)))
    monkeypatch.setattr(mailer, "send_crm_decision", lambda to, name="", aprovado=True: fake.sent.append((to, name, "aprovado" if aprovado else "recusado")))


def _corpo_do_tiquete(t):
    body = t.split(".")[0]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()


def test_cadastro_verificado_no_cfm(monkeypatch, capsys):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    st = _cfm_simulado(monkeypatch)
    r = c.post("/auth/signup/start", json=_novo(crm="CRM-SP 123.456", uf=""))
    assert r.status_code == 200, r.text
    assert st["consultas"] == [("123456", "SP")] and st["validacoes"] == [("123456", "SP", CPF, "12/05/1985")]
    corpo = _corpo_do_tiquete(r.json()["ticket"])
    assert CPF not in corpo and "529.982" not in corpo and "1985" not in corpo        # o CPF e o nascimento não vão no tíquete
    to, code, purpose = fake.sent[-1]
    r = c.post("/auth/signup/verify", json={"ticket": r.json()["ticket"], "code": code})
    assert r.json() == {"ok": True, "redirect": auth.HOME + "?bemvindo=1"}             # sem espera: vai para o app
    u = fake.users["novo@clinica.com.br"]
    assert (u["name"], u["crm"], u["crm_uf"], u["crm_status"], u["crm_fonte"]) == ("Ana Lima", "123456", "SP", "verificado", "cfm")
    assert [s for s in fake.sent if s[0] == "admins"] == []                             # verificado: ninguém precisa aprovar
    out = capsys.readouterr().out
    assert CPF not in out and "12/05/1985" not in out


def test_cadastro_sem_chave_fica_pendente_e_avisa_os_administradores(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "Dono@OpenDoctor.app, outro@opendoctor.app")
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    r = c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]})
    assert r.json()["ok"] and r.json()["bloqueio"] == "crm_pendente" and auth.COOKIE_NAME in r.cookies
    u = fake.users["novo@clinica.com.br"]
    assert (u["crm_status"], u["crm_fonte"], u["crm"], u["crm_uf"]) == ("pendente", None, "123456", "SP")
    aviso = [s for s in fake.sent if s[0] == "admins"]
    assert aviso == [("admins", ("dono@opendoctor.app", "outro@opendoctor.app"), "Ana Lima", "123456", "SP")]   # só nome e CRM


def test_aviso_ao_administrador_so_leva_nome_e_crm():
    subj, body, text = mailer.render("crm_pendente", nome="Ana Lima", crm="123456/SP")
    assert "Ana Lima" in body and "123456/SP" in body and "123456/SP" in subj and "opendoctor-cadastros.html" in body
    assert "@" not in text.replace("opendoctor.app", "") and CPF not in body
    subj, body, text = mailer.render("crm_aprovado", name="Ana Lima")
    assert "Ana," in body and "liberada" in body
    subj, body, text = mailer.render("crm_recusado", name="Ana Lima")
    assert "Não conseguimos confirmar seu CRM" in body


@pytest.mark.parametrize("consulta,valido,erro", [
    ({"status": "nao_encontrado"}, True, "crm_nao_encontrado"),
    ({"status": "ok", "medico": {"nome": "ANA MARIA DE LIMA", "situacao": "C"}}, True, "crm_irregular"),
    ({"status": "ok", "medico": {"nome": "BEATRIZ SOUZA", "situacao": "A"}}, True, "crm_nome"),
    (None, False, "crm_dados"),
])
def test_cadastro_recusado_nao_cria_nada(monkeypatch, consulta, valido, erro):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, consulta, valido)
    r = c.post("/auth/signup/start", json=_novo())
    assert r.status_code == 400 and r.json() == {"error": erro}
    assert fake.sent == [] and fake.codes == {} and fake.users == {}                 # nem código, nem conta


@pytest.mark.parametrize("consulta,valido", [
    ({"status": "indisponivel", "codigo": "2010"}, True),                  # CFM fora do ar
    ({"status": "indisponivel", "codigo": "3010"}, True),                  # chave vencida
    (None, {"status": "indisponivel", "codigo": "rede"}),                  # Validar sem resposta
])
def test_cfm_indisponivel_fica_pendente(monkeypatch, consulta, valido):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, consulta, valido)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    assert c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]}).json()["bloqueio"] == "crm_pendente"
    assert fake.users["novo@clinica.com.br"]["crm_status"] == "pendente"


def test_crm_de_outra_conta_fica_pendente(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, em_uso=True)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]})
    assert fake.users["novo@clinica.com.br"]["crm_status"] == "pendente"


def test_campos_do_registro(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    erros = {"nome": ["Ana", "Dra. Ana", "Ana 2 Lima", ""], "cpf": ["529.982.247-24", "111.111.111-11", "123"],
             "nascimento": ["31/02/1990", "12/05/2015", "12/05/1900", "1990-13-01", "ontem"],
             "crm": ["", "12345678", "CRM-SP"], "uf": ["", "XX", "S"]}
    for campo, ruins in erros.items():
        for v in ruins:
            r = c.post("/auth/signup/start", json=dict(_novo(), **{campo: v}))
            assert r.json() == {"error": campo}, (campo, v, r.json())
    assert fake.sent == []
    for bom in ({"nascimento": "1985-05-12"}, {"crm": "123456/rj", "uf": ""}, {"nome": "Maria D'Ávila"}, {"cpf": CPF}):
        server._RL.clear()
        assert c.post("/auth/signup/start", json=dict(_novo(), **bom)).json()["ok"], bom


def test_tiquete_de_antes_do_registro_nao_cria_conta(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    velho = auth.sign({"k": "signup", "email": "novo@clinica.com.br", "name": "Nova", "ph": auth.hash_password(PW)})
    assert c.post("/auth/signup/verify", json={"ticket": velho, "code": "123456"}).json()["error"] == "sessao_expirada"
    assert fake.users == {}


def test_limite_de_conferencias_no_cfm(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    st = _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    monkeypatch.setitem(server.RATE_LIMITS, "login_code", (100, 600))
    rs = [c.post("/auth/signup/start", json=_novo()) for _ in range(server.RATE_LIMITS["cfm"][0] + 1)]
    assert rs[-1].status_code == 429 and rs[-1].json()["error"] == "limite_ip"
    assert len(st["consultas"]) == server.RATE_LIMITS["cfm"][0]


# ===================== conta nova pelo Google =====================

def _google(monkeypatch, fake, existe=False):
    from app import integrations
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(auth, "exchange_login", lambda code: {"email": "Nova@Clinica.com.br", "name": "Nova Google",
                                                             "picture": "https://foto", "sub": "g-1"})
    if existe:
        fake.users.update(_user("nova@clinica.com.br", pw=None))
    criadas = []

    def upsert(email, name=None, picture=None, google_sub=None, crm=None):
        crm = crm or {}
        criadas.append((email, name, crm))
        u = fake.users.setdefault(email, {"id": "u-" + email, "email": email, "name": name, "sv": 0,
                                          "crm_status": crm.get("status"), "crm_fonte": crm.get("fonte")})
        return u
    monkeypatch.setattr(db, "upsert_user", upsert)
    return criadas


def _volta_do_google(c):
    import urllib.parse as up
    r = c.get("/auth/google/login", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    return c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)


def test_google_conta_nova_passa_pelo_registro(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    r = _volta_do_google(c)
    assert r.headers["location"] == "/opendoctor-login.html?registro=google"            # nada do perfil na URL
    assert auth.COOKIE_NAME not in r.cookies and criadas == [] and fake.users == {}     # a conta ainda não existe
    assert r.cookies.get(server.GREG_COOKIE)
    assert TestClient(server.app).post("/auth/google/registro", json=REG).json()["error"] == "sessao_expirada"   # outro navegador
    assert c.post("/auth/google/registro", json=dict(REG, cpf="123")).json()["error"] == "cpf"
    r = c.post("/auth/google/registro", json=REG)
    assert r.json()["ok"] and r.json()["bloqueio"] == "crm_pendente" and auth.COOKIE_NAME in r.cookies
    assert criadas == [("nova@clinica.com.br", "Ana Lima",
                        {"crm": "123456", "uf": "SP", "status": "pendente", "fonte": None, "situacao": None})]
    assert [e[1:3] for e in fake.events] == [("entrou", "cadastro")]


def test_google_registro_recusado_e_verificado(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    _volta_do_google(c)
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "crm_nao_encontrado"} and criadas == []
    _cfm_simulado(monkeypatch)
    r = c.post("/auth/google/registro", json=REG)
    assert r.json() == {"ok": True, "redirect": auth.HOME + "?bemvindo=1"}
    assert criadas[0][2]["status"] == "verificado" and fake.users["nova@clinica.com.br"]["crm_fonte"] == "cfm"


def test_google_registro_nao_entra_em_conta_que_passou_a_existir(monkeypatch):
    """O tíquete do Google só cria conta: se o e-mail ganhou uma conta no meio do caminho, ele não serve de login."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    _volta_do_google(c)
    fake.users.update(_user("nova@clinica.com.br"))
    r = c.post("/auth/google/registro", json=REG)
    assert r.json() == {"error": "sessao_expirada"} and auth.COOKIE_NAME not in r.cookies and criadas == []
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "sessao_expirada"}     # o cookie foi apagado


def test_google_conta_que_ja_existe_entra_como_sempre(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake, existe=True)
    r = _volta_do_google(c)
    assert r.headers["location"] == auth.HOME and auth.COOKIE_NAME in r.cookies
    assert not r.cookies.get(server.GREG_COOKIE) and criadas == [("nova@clinica.com.br", "Nova Google", {})]


# ===================== a espera das contas pendentes =====================

def _logado(monkeypatch, **conta):
    u = dict({"id": "u1", "email": "ana@clinica.com.br", "name": "Ana Lima", "sv": 0, "crm_status": None, "crm_fonte": None}, **conta)
    monkeypatch.setattr(db, "get_user", lambda uid: dict(u) if uid == "u1" else None)
    c = TestClient(server.app)
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u1", "sv": 0}))
    return c


@pytest.mark.parametrize("status,motivo", [("pendente", "crm_pendente"), ("recusado", "crm_recusado"), ("??", "crm_pendente")])
def test_conta_pendente_entra_mas_nao_usa_o_app(monkeypatch, status, motivo):
    c = _logado(monkeypatch, crm_status=status)
    r = c.get("/opendoctor-agenda.html", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/opendoctor-login.html?next=%2Fopendoctor-agenda.html"
    r = c.get("/cid10?q=diabetes")
    assert r.status_code == 403 and r.json() == {"error": motivo}
    assert c.get("/patients", headers={"accept": "text/html"}, follow_redirects=False).status_code == 302   # link clicado
    assert c.post("/prontuario/list", json={"patient_id": 1}).status_code == 403
    assert c.get("/vendor/x.js").status_code == 403
    me = c.get("/me").json()
    assert me["logged_in"] and me["bloqueio"] == motivo
    for livre in ("/opendoctor-login.html", "/assets/email/logo.png", "/privacy.html"):
        assert c.get(livre).status_code == 200, livre
    assert c.get("/auth/logout", follow_redirects=False).status_code == 307


@pytest.mark.parametrize("conta", [{}, {"crm_status": "verificado", "crm_fonte": "cfm"},
                                   {"crm_status": "verificado", "crm_fonte": "manual"}])
def test_contas_antigas_e_verificadas_seguem_como_sempre(monkeypatch, conta):
    c = _logado(monkeypatch, **conta)
    assert c.get("/cid10?q=diabetes").status_code == 200
    assert c.get("/opendoctor-agenda.html", follow_redirects=False).status_code == 200
    assert c.get("/me").json()["bloqueio"] is None


def test_login_com_senha_de_conta_pendente_avisa_a_tela(monkeypatch):
    fake = _Fake(_user("ana@clinica.com.br", crm_status="pendente"))
    c = _client(monkeypatch, fake)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json() == {"ok": True, "redirect": auth.HOME, "bloqueio": "crm_pendente"}
    fake = _Fake(_user("ana@clinica.com.br"))                                     # conta antiga: igual a antes
    c = _client(monkeypatch, fake)
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json() == {"ok": True, "redirect": auth.HOME}


# ===================== aprovada à mão: confirma CPF e nascimento quando houver a chave =====================

def test_aprovada_a_mao_confirma_uma_vez_quando_ha_chave(monkeypatch):
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="manual")
    monkeypatch.setattr(db, "get_medico", lambda uid: {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP"})
    confirmou = []
    monkeypatch.setattr(db, "crm_confirmed", lambda uid: confirmou.append(uid) or True)
    st = _cfm_simulado(monkeypatch, valido=False)
    assert c.get("/cid10?q=diabetes").json() == {"error": "crm_confirmar"}
    assert c.get("/me").json()["bloqueio"] == "crm_confirmar"
    assert c.post("/auth/crm/confirmar", json={"cpf": "123", "nascimento": "12/05/1985"}).json() == {"error": "cpf"}
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.json() == {"error": "crm_dados"} and confirmou == []                    # não bateu: pede de novo
    _cfm_simulado(monkeypatch, valido={"status": "indisponivel", "codigo": "2010"})
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.status_code == 503 and r.json() == {"error": "cfm_indisponivel"} and confirmou == []
    st = _cfm_simulado(monkeypatch, valido=True)
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985", "next": "/opendoctor-prontuario.html"})
    assert r.json() == {"ok": True, "redirect": "/opendoctor-prontuario.html"} and confirmou == ["u1"]
    assert st["validacoes"] == [("123456", "SP", CPF, "12/05/1985")]
    assert TestClient(server.app).post("/auth/crm/confirmar", json={"cpf": CPF}).status_code == 401   # sem sessão


def test_confirmar_sem_nada_a_confirmar_nao_chama_o_cfm(monkeypatch):
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="cfm")
    st = _cfm_simulado(monkeypatch)
    assert c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"}).json()["ok"]
    assert st["validacoes"] == []


# ===================== página de cadastros (administradores) =====================

UID = "8f14e45f-ceea-467a-9575-1a2b3c4d5e6f"


def test_cadastros_so_para_administradores(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    c = _logado(monkeypatch)
    monkeypatch.setattr(db, "pending_doctors", lambda: pytest.fail("não-administrador leu a lista"))
    monkeypatch.setattr(db, "decide_crm", lambda uid, ap: pytest.fail("não-administrador decidiu"))
    assert c.get("/admin/cadastros").status_code == 403
    assert c.post("/admin/cadastros/aprovar", json={"id": UID}).status_code == 403
    assert c.post("/admin/cadastros/recusar", json={"id": UID}).status_code == 403
    assert c.get("/opendoctor-cadastros.html", follow_redirects=False).status_code == 200   # a página não tem dado nenhum
    anonimo = TestClient(server.app)
    assert anonimo.get("/admin/cadastros").status_code == 401
    assert anonimo.get("/opendoctor-cadastros.html", follow_redirects=False).status_code == 302
    monkeypatch.setenv("ADMIN_EMAILS", "")
    c = _logado(monkeypatch, email="dono@opendoctor.app")                    # sem ADMIN_EMAILS, ninguém é administrador
    assert c.get("/admin/cadastros").status_code == 403


def test_administrador_aprova_e_recusa(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "outro@x.com, Dono@OpenDoctor.app")
    c = _logado(monkeypatch, email="dono@opendoctor.app")
    lista = [{"id": UID, "name": "Ana Lima", "crm": "123456", "crm_uf": "SP", "pedido_em": "2026-10-30T12:00:00+00:00",
              "situacao": None, "outras_contas": 0}]
    monkeypatch.setattr(db, "pending_doctors", lambda: lista)
    pendentes, decisoes, enviados = {UID: {"id": UID, "email": "ana@clinica.com.br", "name": "Ana Lima"}}, [], []

    def decide(uid, aprovado):
        decisoes.append((uid, aprovado))
        return pendentes.pop(uid, None)
    monkeypatch.setattr(db, "decide_crm", decide)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send_crm_decision", lambda to, name="", aprovado=True: enviados.append((to, aprovado)))
    j = c.get("/admin/cadastros").json()
    assert j == {"pendentes": lista, "cfm": False}
    assert c.post("/admin/cadastros/aprovar", json={"id": "x"}).json()["error"] == "id_invalido"
    assert c.post("/admin/cadastros/aprovar", content=json.dumps({"id": UID}), headers={"content-type": "text/plain"}).json()["error"] == "id_invalido"
    r = c.post("/admin/cadastros/aprovar", json={"id": UID.upper()})
    assert r.json() == {"ok": True, "email_enviado": True}
    assert decisoes == [(UID, True)] and enviados == [("ana@clinica.com.br", True)]
    r = c.post("/admin/cadastros/recusar", json={"id": UID})                    # já decidido: não muda nem avisa de novo
    assert r.status_code == 409 and r.json()["error"] == "nao_pendente" and len(enviados) == 1
    pendentes[UID] = {"id": UID, "email": "ana@clinica.com.br", "name": "Ana Lima"}
    assert c.post("/admin/cadastros/recusar", json={"id": UID}).json()["ok"]
    assert enviados[-1] == ("ana@clinica.com.br", False)


def test_email_da_decisao_que_falha_nao_desfaz(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    c = _logado(monkeypatch, email="dono@opendoctor.app")
    monkeypatch.setattr(db, "decide_crm", lambda uid, ap: {"id": uid, "email": "ana@clinica.com.br", "name": "Ana"})
    monkeypatch.setattr(mailer, "configured", lambda: True)

    def falha(*a, **k):
        raise RuntimeError("resend 500")
    monkeypatch.setattr(mailer, "send_crm_decision", falha)
    assert c.post("/admin/cadastros/aprovar", json={"id": UID}).json() == {"ok": True, "email_enviado": False}


# ===================== CRM conferido não muda em Configurações =====================

def test_crm_conferido_nao_muda_em_configuracoes(monkeypatch):
    medico = {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP", "especialidade": None, "consultorio_endereco": None,
              "consultorio_telefone": None, "receita_papel": None}
    monkeypatch.setattr(db, "get_medico", lambda uid: dict(medico))
    monkeypatch.setattr(db, "update_medico", lambda uid, campos: medico.update(campos) or dict(medico))
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="cfm")
    assert c.get("/me/medico").json()["crm_conferido"] is True
    r = c.patch("/me/medico", json={"crm": "999999"})
    assert r.status_code == 400 and medico["crm"] == "123456"
    assert c.patch("/me/medico", json={"crm_uf": "RJ"}).status_code == 400
    assert c.patch("/me/medico", json={"crm": "123456", "especialidade": "Cardiologia"}).status_code == 200
    assert medico["especialidade"] == "Cardiologia"
    c = _logado(monkeypatch)                                                    # conta antiga: edita como sempre
    assert c.get("/me/medico").json()["crm_conferido"] is False
    assert c.patch("/me/medico", json={"crm": "777"}).status_code == 200 and medico["crm"] == "777"
