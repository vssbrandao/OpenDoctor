"""Tela de login: e-mail vira login_hint do Google (sem banco, sem rede)."""
import asyncio
import json
import os
import urllib.parse

import pytest

from app import auth, integrations, server


def _q(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


def test_login_url_com_e_sem_hint(monkeypatch):
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    q = _q(auth.login_url())
    assert "login_hint" not in q and q["prompt"] == ["select_account"]
    q = _q(auth.login_url("ana@clinica.com.br"))
    assert q["login_hint"] == ["ana@clinica.com.br"] and "prompt" not in q
    assert auth.unsign(q["state"][0], auth.STATE_MAX_AGE)["k"] == "login"


class _Req:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return json.loads(self._body)


def _start(body):
    r = asyncio.run(server.google_start(_Req(body)))
    return (r.status_code, json.loads(r.body)) if hasattr(r, "status_code") else (200, r)


def test_google_start(monkeypatch):
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    st, j = _start('{"email": " ana@clinica.com.br "}')
    assert st == 200 and _q(j["url"])["login_hint"] == ["ana@clinica.com.br"]
    st, j = _start('{"email": ""}')                          # sem e-mail: login normal
    assert st == 200 and "login_hint" not in _q(j["url"])
    for bad in ('{"email": "abc"}', '{"email": "a@b"}', '{"email": "a b@c.com"}'):
        assert _start(bad)[0] == 400
    assert _start("não é json")[0] == 200                   # corpo inválido = sem e-mail


def test_google_start_sem_google(monkeypatch):
    monkeypatch.setattr(integrations, "configured", lambda p: False)
    assert _start('{"email": "ana@clinica.com.br"}')[0] == 400


# ----- login por e-mail e senha + códigos de cadastro/redefinição (banco e e-mail simulados) -----

def test_safe_next():
    assert auth.safe_next("/opendoctor-agenda.html#pacientes") == "/opendoctor-agenda.html#pacientes"
    assert auth.safe_next("/opendoctor-prontuario.html?x=1") == "/opendoctor-prontuario.html?x=1"
    for bad in ("https://evil.com", "//evil.com", "/\\evil.com", "javascript:alert(1)", "", None,
                "/auth/logout", "/a b", "/" + "x" * 400):
        assert auth.safe_next(bad) == auth.HOME
    # o navegador resolve "." e ".." (e o que vem codificado): /./auth/logout é o /auth/logout
    for bad in ("/./auth/logout", "/%2e/auth/logout", "/x/../auth/logout", "/%61uth/logout", "/auth", "/..//evil.example",
                "/a/%2e%2e/auth/logout", "/%5cevil.example"):
        assert auth.safe_next(bad) == auth.HOME, bad
    assert auth.safe_next("/opendoctor-agenda.html?a=1&b=..#x") == "/opendoctor-agenda.html?a=1&b=..#x"   # só o caminho


def test_next_da_pagina_de_login_so_fica_no_site():
    """Quem já entrou vai direto para o next da página (sem passar pelo servidor): a mesma regra de safe_next.
    O navegador apaga tab e quebra de linha, então "/\\t/evil.example" viraria "//evil.example"."""
    import os
    import re
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node")
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-login.html"), encoding="utf-8").read()
    fn = re.search(r"function safeNext\(v\) \{.*?\n      \}", html, re.S).group(0)
    bons = ["/opendoctor-agenda.html#pacientes", "/opendoctor-prontuario.html?x=1", "/opendoctor-agenda.html?a=..#x"]
    ruins = ["/\t/evil.example", "/\n/evil.example", "/\r/evil.example", "/ /evil.example", "/\x00/evil.example",
             "//evil.example", "/\\evil.example", "https://evil.example", "javascript:alert(1)", "", "/auth/logout",
             "/" + "x" * 400, "/..//evil.example", "/./auth/logout", "/%2e/auth/logout", "/x/../auth/logout",
             "/%61uth/logout", "/%5cevil.example"]
    js = (fn + "; var location = { origin: 'https://opendoctor.app' };"
          + "process.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(safeNext)));")
    out = subprocess.run([node, "-e", js, json.dumps(bons + ruins)], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == bons + [""] * len(ruins)
    for v in bons:                                       # o servidor aceita o mesmo
        assert auth.safe_next(v) == v
    for v in ruins:                                      # e recusa o mesmo
        assert auth.safe_next(v) == auth.HOME, v


def test_codigo_por_finalidade():
    assert auth.code_hash("a@b.com", "123456", "signup") != auth.code_hash("a@b.com", "123456", "reset")
    assert auth.code_hash("a@b.com", "123456", "reset") != auth.code_hash("c@d.com", "123456", "reset")
    c = auth.new_code()
    assert len(c) == 6 and c.isdigit()


def test_regras_e_hash_da_senha():
    assert auth.password_problems("abc") == ["tamanho", "letras", "especial"]
    assert auth.password_problems("Abcdef12") == ["especial"]
    assert auth.password_problems("abcdef12!") == ["letras"]          # sem maiúscula
    assert auth.password_problems("Abcdefg1!") == ["letras"]          # só 1 número
    assert auth.password_problems("Abcdef12!") == []
    assert auth.password_problems("Ab 12345 x") == ["especial"]       # espaço não conta
    assert auth.password_problems(None) == list(auth.PW_RULES)
    h = auth.hash_password("Abcdef12!")
    assert h.startswith("pbkdf2_sha256$600000$") and "Abcdef12!" not in h
    assert auth.check_password("Abcdef12!", h) and not auth.check_password("abcdef12!", h)
    assert not auth.check_password("x", None) and not auth.check_password("x", "lixo")
    assert auth.hash_password("Abcdef12!") != h                       # sal diferente a cada vez


def test_sessao_derrubada_ao_trocar_senha(monkeypatch):
    from app import db
    users = {"u1": {"id": "u1", "email": "a@b.com", "sv": 0}}
    monkeypatch.setattr(db, "get_user", lambda uid: users.get(uid))

    class R:
        def __init__(self, tok):
            self.cookies = {auth.COOKIE_NAME: tok}
    tok = auth.sign({"uid": "u1", "sv": 0})
    assert auth.current_user(R(tok))["id"] == "u1"
    assert auth.current_user(R(auth.sign({"uid": "u1"})))["id"] == "u1"     # cookies antigos (sem sv) valem
    users["u1"]["sv"] = 1                                                   # senha trocada
    assert auth.current_user(R(tok)) is None


PW = "Abcdef12!"
# Registro profissional (CPF de exemplo com dígitos válidos; sem a chave do CFM a conta nasce pendente)
REG = {"nome": "Ana Lima", "cpf": "529.982.247-25", "nascimento": "12/05/1985", "crm": "123456", "uf": "SP"}


def _novo(email="novo@clinica.com.br", **kw):
    return dict(REG, email=email, password=PW, **kw)


class _Fake:
    def __init__(self, users=None):
        self.users = users or {}          # email -> {"id","hash","sv","locked_s"}
        self.codes, self.sent, self.failed = {}, [], {}
        self.events = []                  # (user_id, event, method, device)


class _NaHora:
    """Executa o registro de acesso na hora (no servidor ele vai para uma thread)."""
    def submit(self, fn):
        fn()


def _fake_audit(monkeypatch, fake):
    from app import db, mailer
    monkeypatch.setattr(server, "_AUDIT", _NaHora())

    def record(uid, event, method, ip=None, user_agent=None, device=None):
        mine = [e for e in fake.events if e[0] == uid and e[1] == "entrou"]
        novo = event == "entrou" and bool(mine) and all(e[3] != device for e in mine)
        fake.events.append((uid, event, method, device))
        return novo
    monkeypatch.setattr(db, "record_login", record)
    monkeypatch.setattr(mailer, "send_new_device",
                        lambda to, name="", device="", method="": fake.sent.append((to, device, "device:" + method)))


def _client(monkeypatch, fake, configured=True):
    from fastapi.testclient import TestClient
    from app import db, mailer
    server._RL.clear()
    monkeypatch.setattr(mailer, "configured", lambda: configured)
    monkeypatch.setattr(mailer, "send_code", lambda to, code, purpose, name="": fake.sent.append((to, code, purpose)))
    monkeypatch.setattr(mailer, "send_password_changed",
                        lambda to, name="", criada=False: fake.sent.append((to, "", "created" if criada else "changed")))
    monkeypatch.setattr(db, "new_login_code", lambda e, h, teto=True: (fake.codes.__setitem__(e, h), ("ok", 0))[1])
    monkeypatch.setattr(db, "discard_login_code", lambda e: fake.codes.pop(e, None))
    monkeypatch.setattr(db, "device_known", lambda uid, dev: False)          # nenhum aparelho conhecido (o teste que quer, troca)

    def check(e, h, soma=True):
        if fake.codes.get(e) == h:
            fake.codes.pop(e)
            return "ok", 0
        return ("errado", 4) if e in fake.codes else ("expirado", 0)
    monkeypatch.setattr(db, "check_login_code", check)
    monkeypatch.setattr(db, "account", lambda e: None if e not in fake.users else {"password": bool(fake.users[e].get("hash"))})
    monkeypatch.setattr(db, "user_by_email", lambda e: fake.users.get(e))
    monkeypatch.setattr(db, "user_by_google_sub",
                        lambda s: next((u for u in fake.users.values() if s and u.get("google_sub") == s), None))

    def info(e):
        u = fake.users.get(e)
        return None if not u else {"id": u["id"], "hash": u.get("hash"), "sv": u.get("sv", 0), "locked_s": u.get("locked_s", 0),
                                   "crm_status": u.get("crm_status"), "crm_fonte": u.get("crm_fonte")}
    monkeypatch.setattr(db, "password_login_info", info)

    def failed(uid):
        fake.failed[uid] = fake.failed.get(uid, 0) + 1
        return (0, 900) if fake.failed[uid] >= 5 else (5 - fake.failed[uid], 0)
    monkeypatch.setattr(db, "login_failed", failed)
    monkeypatch.setattr(db, "login_succeeded", lambda uid: fake.failed.pop(uid, None))

    def create(e, n, ph, crm=None):
        crm = crm or {}
        st, fonte = crm.get("status"), crm.get("fonte")
        # como db._CRM_DECISAO: 'verificado' de um CRM/UF que outra conta (não recusada) já tem nasce pendente
        if st == "verificado" and any(u.get("crm") == crm.get("crm") and u.get("crm_uf") == crm.get("uf")
                                      and u.get("crm_status") != "recusado" for k, u in fake.users.items() if k != e):
            st, fonte = "pendente", None
        fake.users.setdefault(e, {"id": "u-" + e, "email": e, "name": n, "hash": ph, "sv": 0, "crm": crm.get("crm"),
                                  "crm_uf": crm.get("uf"), "crm_status": st, "crm_fonte": fonte})
        return fake.users[e]
    monkeypatch.setattr(db, "create_email_user", create)

    def set_pw(uid, ph, sv=None):
        u = next(u for u in fake.users.values() if u["id"] == uid)
        u.update(hash=ph, sv=u.get("sv", 0) + 1)
        return u
    monkeypatch.setattr(db, "set_password", set_pw)
    monkeypatch.setattr(db, "get_user", lambda uid: next((u for u in fake.users.values() if u["id"] == uid), None))
    _fake_audit(monkeypatch, fake)
    return TestClient(server.app)


def _user(email, pw=PW, **kw):
    return {email: dict({"id": "u-" + email, "email": email, "hash": auth.hash_password(pw) if pw else None, "sv": 0}, **kw)}


def test_check_decide_a_proxima_tela(monkeypatch):
    fake = _Fake(dict(_user("ana@clinica.com.br"), **_user("google@clinica.com.br", pw=None)))
    c = _client(monkeypatch, fake)
    assert c.post("/auth/email/check", json={"email": " Ana@Clinica.com.br"}).json() == {"exists": True, "password": True, "email_ok": True}
    assert c.post("/auth/email/check", json={"email": "google@clinica.com.br"}).json()["password"] is False
    assert c.post("/auth/email/check", json={"email": "novo@clinica.com.br"}).json()["exists"] is False
    assert c.post("/auth/email/check", json={"email": "abc"}).json()["error"] == "email_invalido"


def test_login_com_senha(monkeypatch):
    fake = _Fake(dict(_user("ana@clinica.com.br"), **_user("google@clinica.com.br", pw=None)))
    c = _client(monkeypatch, fake)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": "errada", "next": "/opendoctor-agenda.html#pacientes"})
    assert r.status_code == 401 and r.json() == {"error": "senha_incorreta", "left": 4} and auth.COOKIE_NAME not in r.cookies
    r = c.post("/auth/password/login", json={"email": "ANA@clinica.com.br", "password": PW, "next": "/opendoctor-agenda.html#pacientes"})
    assert r.json() == {"ok": True, "redirect": "/opendoctor-agenda.html#pacientes"} and auth.COOKIE_NAME in r.cookies
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": ""}).json()["error"] == "senha_vazia"
    assert c.post("/auth/password/login", json={"email": "google@clinica.com.br", "password": PW}).json()["error"] == "sem_senha"
    assert c.post("/auth/password/login", json={"email": "x@clinica.com.br", "password": PW}).json()["error"] == "sem_conta"


def test_bloqueio_apos_5_erros(monkeypatch):
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    rs = [c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": "errada"}).json() for _ in range(5)]
    assert [r.get("left") for r in rs[:4]] == [4, 3, 2, 1]
    assert rs[4] == {"error": "bloqueado", "minutes": 15}
    fake.users["ana@clinica.com.br"]["locked_s"] = 61
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.status_code == 429 and r.json() == {"error": "bloqueado", "minutes": 2}   # nem a senha certa entra


def test_cadastro_exige_codigo(monkeypatch):
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    assert c.post("/auth/signup/start", json=dict(_novo(), password="fraca")).json() == \
        {"error": "senha_fraca", "rules": ["tamanho", "letras", "especial"]}
    assert c.post("/auth/signup/start", json=dict(_novo(), nome=" ")).json()["error"] == "nome"
    assert c.post("/auth/signup/start", json=_novo("ana@clinica.com.br")).status_code == 409
    r = c.post("/auth/signup/start", json=dict(_novo(), nome="  Dra.  Nova  Lima "))
    ticket = r.json()["ticket"]
    to, code, purpose = fake.sent[-1]
    assert (to, purpose) == ("novo@clinica.com.br", "signup") and "novo@clinica.com.br" not in fake.users   # ainda não criou
    assert PW not in ticket
    assert c.post("/auth/signup/verify", json={"ticket": ticket, "code": "000000"}).json()["error"] == "codigo_incorreto"
    assert c.post("/auth/signup/verify", json={"ticket": "x.y", "code": code}).json()["error"] == "sessao_expirada"
    r = c.post("/auth/signup/verify", json={"ticket": ticket, "code": code})
    assert r.json()["redirect"] == auth.HOME and auth.COOKIE_NAME in r.cookies
    assert auth.unsign(r.cookies[auth.COOKIE_NAME])["bv"] == 1           # a conta nova: as boas-vindas vão na sessão
    u = fake.users["novo@clinica.com.br"]
    assert u["name"] == "Dra. Nova Lima" and auth.check_password(PW, u["hash"])
    # o código de cadastro não serve para redefinir senha
    c.post("/auth/signup/resend", json={"ticket": ticket})
    code2 = fake.sent[-1][1]
    assert c.post("/auth/password/reset/verify", json={"email": "novo@clinica.com.br", "code": code2}).json()["error"] == "codigo_incorreto"


def test_esqueci_a_senha(monkeypatch):
    from app import db
    fake = _Fake(dict(_user("ana@clinica.com.br"), **_user("google@clinica.com.br", pw=None)))
    c = _client(monkeypatch, fake)
    monkeypatch.setattr(db, "get_user", lambda uid: next((u for u in fake.users.values() if u["id"] == uid), None))
    assert c.post("/auth/password/forgot", json={"email": "ninguem@clinica.com.br"}).json()["ok"]   # não revela nem envia
    assert fake.sent == []
    c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"})
    to, code, purpose = fake.sent[-1]
    assert purpose == "reset"
    assert c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": "000000"}).json()["error"] == "codigo_incorreto"
    ticket = c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": code}).json()["ticket"]
    assert c.post("/auth/password/reset", json={"ticket": ticket, "password": "fraca"}).json()["error"] == "senha_fraca"
    assert c.post("/auth/password/reset", json={"ticket": "x.y", "password": "Nova!12ab"}).json()["error"] == "sessao_expirada"
    r = c.post("/auth/password/reset", json={"ticket": ticket, "password": "Nova!12ab"})
    assert r.json()["ok"] and auth.COOKIE_NAME in r.cookies
    assert fake.users["ana@clinica.com.br"]["sv"] == 1                       # outras sessões caem
    assert c.post("/auth/password/reset", json={"ticket": ticket, "password": "Outra!12ab"}).json()["error"] == "sessao_expirada"  # uso único
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json()["error"] == "senha_incorreta"
    # conta só Google pode criar uma senha pelo mesmo caminho
    c.post("/auth/password/forgot", json={"email": "google@clinica.com.br"})
    tk = c.post("/auth/password/reset/verify", json={"email": "google@clinica.com.br", "code": fake.sent[-1][1]}).json()["ticket"]
    assert c.post("/auth/password/reset", json={"ticket": tk, "password": "Minha!12ab"}).json()["ok"]


def test_sem_provedor_de_email(monkeypatch):
    c = _client(monkeypatch, _Fake(_user("ana@clinica.com.br")), configured=False)
    assert c.post("/auth/email/check", json={"email": "novo@b.com"}).json()["email_ok"] is False
    assert c.post("/auth/signup/start", json=_novo("novo@b.com")).status_code == 503
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).status_code == 503
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json()["ok"]   # senha funciona


def test_envio_falhou_descarta_codigo(monkeypatch):
    from app import mailer
    fake = _Fake()
    c = _client(monkeypatch, fake)

    def falha(to, code, purpose, name=""):
        raise RuntimeError("resend 500")
    monkeypatch.setattr(mailer, "send_code", falha)
    r = c.post("/auth/signup/start", json=_novo())
    assert r.status_code == 502 and r.json()["error"] == "envio_falhou" and fake.codes == {}


def test_limites_por_ip(monkeypatch):
    c = _client(monkeypatch, _Fake(_user("ana@clinica.com.br")))
    rs = [c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": "errada"}) for _ in range(21)]
    assert rs[20].status_code == 429 and rs[20].json()["error"] == "limite_ip"
    rs = [c.post("/auth/email/check", json={"email": "a@b.com"}) for _ in range(31)]
    assert rs[30].json()["error"] == "limite_ip"


def test_codigo_nunca_no_log_do_render(monkeypatch):
    from app import mailer
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("LOGIN_CODE_DEBUG", "1")
    monkeypatch.setenv("RENDER", "true")
    assert not mailer.debug_codes() and not mailer.configured()
    monkeypatch.delenv("RENDER")
    assert mailer.debug_codes()


def test_integracao_sem_login_vai_para_tela_de_login(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    c = TestClient(server.app)
    r = c.get("/integrations/google/connect", follow_redirects=False, headers={"accept": "text/html"})
    assert r.headers["location"] == "/opendoctor-login.html?next=%2Fintegrations%2Fgoogle%2Fconnect"   # link clicado
    assert c.get("/integrations/google/connect").status_code == 401                                    # fetch
    assert auth.safe_next("/opendoctor-integracao.html") == "/opendoctor-integracao.html"




def test_reenvio_dentro_de_30s_nao_finge_envio(monkeypatch):
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    j = c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).json()
    assert j == {"ok": True, "resend_in": 30, "sent": True}
    monkeypatch.setattr(db, "new_login_code", lambda e, h, teto=True: ("aguarde", 12))
    n = len(fake.sent)
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).json() == {"ok": True, "resend_in": 12, "sent": False}
    r = c.post("/auth/signup/start", json=_novo()).json()
    assert r["ticket"] and r["sent"] is False and r["resend_in"] == 12 and len(fake.sent) == n   # segue com o código anterior


def test_regras_aceitam_acentos():
    assert auth.password_problems("éXEMPLO12!") == []           # maiúscula/minúscula com acento valem
    assert auth.password_problems("ÉXEMPLO12!") == ["letras"]


def test_template_dos_emails():
    from app import mailer
    assert mailer.first_name("Dra. Ana Paula Lima") == "Ana" and mailer.first_name("") == ""
    assert mailer.first_name("Dr.") == "Dr."
    subj, body, text = mailer.render("reset", name="Vinicius Brandão", code="482913")
    assert subj.startswith("482913") and "Vinicius," in body and "Seu código para uma nova senha" in body
    assert body.count('class="box"') == 6 and ">4</td>" in body and ">3</td>" in body
    assert "https://opendoctor.app/assets/email/logo.png" in body and "Código: 482913" in text
    subj, body, text = mailer.render("signup", name="<script>x</script>", code="111111")
    assert "<script>x" not in body and "Confirme seu e-mail" in body
    subj, body, text = mailer.render("changed", when="14/10/2026 às 00:30 (horário de Brasília)")
    assert "Olá," in body and 'class="box"' not in body and "opendoctor-login.html" in body
    assert "14/10/2026 às 00:30" in body and "Esqueci minha senha" in text


def test_aviso_de_senha_alterada(monkeypatch):
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    monkeypatch.setattr(db, "get_user", lambda uid: next((u for u in fake.users.values() if u["id"] == uid), None))
    c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"})
    tk = c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": fake.sent[-1][1]}).json()["ticket"]
    assert c.post("/auth/password/reset", json={"ticket": tk, "password": "Nova!12ab"}).json()["ok"]
    assert fake.sent[-1] == ("ana@clinica.com.br", "", "changed")


# ----- revisão de segurança -----

class _Rq:
    def __init__(self, cookies):
        self.cookies = cookies


def test_so_cookie_de_sessao_vale_como_sessao(monkeypatch):
    from app import db
    monkeypatch.setattr(db, "get_user", lambda uid: {"id": uid, "email": "a@b.com", "sv": 0})
    ok = auth.sign({"k": "sess", "uid": "u1", "sv": 0})
    antigo = auth.sign({"uid": "u1", "sv": 0})                      # cookie de antes desta versão
    cal = auth.sign({"k": "cal", "prov": "google", "uid": "u1"})     # state do calendário (vai na URL do Google)
    reset = auth.sign({"k": "reset", "uid": "u1", "sv": 0})          # tíquete de nova senha
    assert auth.current_user(_Rq({auth.COOKIE_NAME: ok}))["id"] == "u1"
    assert auth.current_user(_Rq({auth.COOKIE_NAME: antigo}))["id"] == "u1"
    assert auth.current_user(_Rq({auth.COOKIE_NAME: cal})) is None
    assert auth.current_user(_Rq({auth.COOKIE_NAME: reset})) is None


def test_rotas_de_login_so_aceitam_json(monkeypatch):
    c = _client(monkeypatch, _Fake(_user("ana@clinica.com.br")))
    body = '{"email": "ana@clinica.com.br", "password": "%s"}' % PW
    for ctype in ("text/plain", "application/x-www-form-urlencoded", ""):
        r = c.post("/auth/password/login", content=body, headers={"content-type": ctype})
        assert r.json()["error"] == "email_invalido" and auth.COOKIE_NAME not in r.cookies
    r = c.post("/auth/password/login", content=body, headers={"content-type": "application/json; charset=utf-8"})
    assert r.json()["ok"]


def test_login_google_amarrado_ao_navegador(monkeypatch):
    from fastapi.testclient import TestClient
    from app import db
    import urllib.parse as up
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(auth, "exchange_login", lambda code: {"email": "ana@clinica.com.br", "name": "Ana", "sub": "1",
                                                             "email_verified": True})
    monkeypatch.setattr(db, "user_by_email", lambda e: {"id": "u1"})
    monkeypatch.setattr(db, "user_by_google_sub", lambda s: None)
    monkeypatch.setattr(db, "upsert_user", lambda *a, **k: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    fake = _Fake()
    _fake_audit(monkeypatch, fake)
    c = TestClient(server.app)
    r = c.get("/auth/google/login?next=/opendoctor-agenda.html%23pacientes", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    nonce = r.cookies.get(auth.OAUTH_COOKIE)
    assert nonce and auth.unsign(state)["n"] == nonce
    # outro navegador (sem o cookie) usando o mesmo retorno: não loga
    r2 = TestClient(server.app).get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)
    assert "erro=conexao" in r2.headers["location"] and auth.COOKIE_NAME not in r2.cookies
    # o mesmo navegador: loga e volta para a página de origem
    r3 = c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)
    assert r3.headers["location"] == "/opendoctor-agenda.html#pacientes" and auth.COOKIE_NAME in r3.cookies
    assert r3.cookies.get(auth.DEVICE_COOKIE) and fake.events == [("u1", "entrou", "google", auth.device_hash(r3.cookies.get(auth.DEVICE_COOKIE)))]
    # /auth/google/start (e-mail digitado) também marca o navegador
    r4 = c.post("/auth/google/start", json={"email": "ana@clinica.com.br"})
    assert r4.json()["url"].startswith("https://") and r4.cookies.get(auth.OAUTH_COOKIE)


# ----- nível 1: registro de acessos, aviso de aparelho novo, IP, cabeçalhos, chave da sessão -----

def test_registro_de_acessos_e_aviso_de_aparelho_novo(monkeypatch):
    from fastapi.testclient import TestClient
    fake = _Fake(_user("ana@clinica.com.br", name="Dra. Ana Lima"))
    c = _client(monkeypatch, fake)
    login = {"email": "ana@clinica.com.br", "password": PW}
    mac = {"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"}
    r = c.post("/auth/password/login", json=login, headers=mac)
    dev = r.cookies.get(auth.DEVICE_COOKIE)
    assert r.json()["ok"] and dev and fake.sent == []                 # primeira entrada registrada: sem aviso
    assert c.post("/auth/password/login", json=login, headers=mac).json()["ok"]
    assert fake.sent == [] and c.cookies.get(auth.DEVICE_COOKIE) == dev   # mesmo aparelho: sem aviso, mesmo cookie
    win = {"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36 Edg/141.0"}
    outro = TestClient(server.app)
    assert outro.post("/auth/password/login", json=login, headers=win).json()["ok"]
    assert fake.sent == [("ana@clinica.com.br", "Edge no Windows", "device:senha")]
    assert outro.post("/auth/password/login", json=login, headers=win).json()["ok"] and len(fake.sent) == 1
    c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": "errada"})
    assert [e[1] for e in fake.events] == ["entrou"] * 4 + ["senha_incorreta"]
    assert all(e[3] for e in fake.events[:4]) and len({e[3] for e in fake.events[:4]}) == 2   # só o hash, 2 aparelhos
    assert dev not in {e[3] for e in fake.events}


def test_cadastro_registra_sem_aviso(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    r = c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]})
    assert r.json()["ok"] and [e[1:3] for e in fake.events] == [("entrou", "cadastro")]
    assert [s[2] for s in fake.sent] == ["signup"]


def test_nome_do_aparelho():
    assert auth.device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit Version/18.0 Mobile Safari/604.1") == "Safari no iPhone"
    assert auth.device_label("Mozilla/5.0 (Linux; Android 14) AppleWebKit Chrome/141.0 Mobile Safari/537.36") == "Chrome no Android"
    assert auth.device_label("Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:131.0) Gecko Firefox/131.0") == "Firefox no macOS"
    assert auth.device_label("<script>") == "navegador não identificado" and auth.device_label(None)
    assert auth.device_id(_Rq({auth.DEVICE_COOKIE: "x" * 32})) and auth.device_id(_Rq({auth.DEVICE_COOKIE: "<b>" * 10})) is None


def test_email_de_aparelho_novo():
    from app import mailer
    subj, body, text = mailer.render("device", name="Ana", when="14/10/2026 às 09:00 (horário de Brasília)",
                                     device="Chrome no Windows", via="e-mail e senha")
    assert subj == "Novo acesso à sua conta do OpenDoctor" and "Ana," in body and 'class="box"' not in body
    assert "Chrome no Windows, com e-mail e senha" in body and "Esqueci minha senha" in text
    assert "todos os aparelhos" not in body


class _Hd:
    def __init__(self, headers, peer="10.0.0.9"):
        self.headers = headers
        self.client = type("C", (), {"host": peer})()


def test_ip_do_visitante_nao_vem_do_cabecalho_forjado():
    assert server._client_ip(_Hd({"cf-connecting-ip": "177.45.46.176", "x-forwarded-for": "7.7.7.7, 177.45.46.176"})) == "177.45.46.176"
    assert server._client_ip(_Hd({"x-forwarded-for": "7.7.7.7, 177.45.46.176, 172.69.11.27"})) == "172.69.11.27"
    assert server._client_ip(_Hd({})) == "10.0.0.9"


def test_cabecalhos_de_seguranca():
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    for path in ("/health", "/opendoctor-login.html", "/me"):
        h = c.get(path).headers
        assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "max-age=31536000" in h["strict-transport-security"]
        assert h["referrer-policy"] == "strict-origin-when-cross-origin" and "camera=()" in h["permissions-policy"]
    assert "/_diag/ip" not in {getattr(r, "path", "") for r in server.app.routes}   # diagnóstico temporário removido


def test_sem_session_secret_o_render_nao_sobe():
    import os
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, RENDER="true", SESSION_SECRET="")
    r = subprocess.run([sys.executable, "-c", "import app.auth"], env=env, cwd=root, capture_output=True, text=True)
    assert r.returncode != 0 and "SESSION_SECRET" in r.stderr
    env["SESSION_SECRET"] = "x" * 40
    assert subprocess.run([sys.executable, "-c", "import app.auth"], env=env, cwd=root).returncode == 0


def test_paginas_do_app_exigem_login(monkeypatch):
    from fastapi.testclient import TestClient
    from app import db
    c = TestClient(server.app)
    for path in ("/opendoctor-agenda.html", "/opendoctor-prontuario.html", "/opendoctor-integracao.html",
                 "http://testserver//opendoctor-agenda.html", "/./opendoctor-agenda.html", "/OpenDoctor-Agenda.html", "/nao-existe.html"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"].startswith("/opendoctor-login.html?next=%2F"), path
    assert c.get("/opendoctor-agenda.html", follow_redirects=False).headers["location"] == \
        "/opendoctor-login.html?next=%2Fopendoctor-agenda.html"
    for path in ("/opendoctor-login.html", "/privacy.html", "/terms.html", "/privacy", "/assets/email/logo.png"):
        assert c.get(path, follow_redirects=False).status_code == 200, path
    assert c.get("/README.md").status_code == 401
    # o assistente de IA também só responde com login
    assert c.post("/ask", json={"query": "dose de amoxicilina"}).status_code == 401
    assert c.post("/followups", json={"answer": "x"}).status_code == 401
    # com sessão: a página abre e não fica em cache
    monkeypatch.setattr(db, "get_user", lambda uid: {"id": uid, "email": "ana@clinica.com.br", "sv": 0})
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u1", "sv": 0}))
    r = c.get("/opendoctor-agenda.html", follow_redirects=False)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and "<html" in r.text.lower()
    assert c.get("/README.md").status_code == 404                     # notas internas: nem logado


# ----- correções do teste contra o servidor de verdade (31/10) -----

def test_regras_da_senha_iguais_na_tela_e_no_servidor():
    """A lista de requisitos da tela é o que o servidor aceita: emoji conta 1 caractere; "²" não é número; "ª" não é
    minúscula (as categorias \\p{Nd} \\p{Ll} \\p{Lu} do JS)."""
    import os
    import re
    import shutil
    import subprocess
    casos = ["Ab12!😀😀", "Abcdefg²²!", "ªBCDEFG12!", "Abcdef12!", "ABCDEF12!", "Ab1!" * 3, "Abcdefgh12", "Ç" * 30 + "ab12!"]
    assert auth.password_problems("Ab12!😀😀") == ["tamanho"]          # 7 caracteres
    assert "letras" in auth.password_problems("Abcdefg²²!") and "letras" in auth.password_problems("ªBCDEFG12!")
    node = shutil.which("node")
    if not node:
        pytest.skip("sem node")
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-login.html"), encoding="utf-8").read()
    fn = re.search(r"function problems\(pw\) \{.*?\n      \}", html, re.S).group(0)
    js = fn + "; process.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(problems)));"
    out = subprocess.run([node, "-e", js, json.dumps(casos)], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [auth.password_problems(p) for p in casos]


def test_bloqueio_deixa_entrar_o_aparelho_conhecido(monkeypatch):
    """Quem só sabe o e-mail tranca a conta com 5 senhas erradas, mas não o médico: do aparelho de onde a conta já entrou,
    a senha certa entra. De outro aparelho (ou com a senha errada), o bloqueio de sempre, sem contar mais erro."""
    from app import db
    fake = _Fake(_user("ana@clinica.com.br", locked_s=600))
    c = _client(monkeypatch, fake)
    conhecido = auth.device_hash("aparelho-da-ana-0123456789")
    monkeypatch.setattr(db, "device_known", lambda uid, dev: uid == "u-ana@clinica.com.br" and dev == conhecido)
    erros = []
    monkeypatch.setattr(db, "login_failed", lambda uid: erros.append(uid) or (0, 900))
    corpo = {"email": "ana@clinica.com.br", "password": PW}
    r = c.post("/auth/password/login", json=corpo)
    assert r.status_code == 429 and r.json()["error"] == "bloqueado"                  # aparelho que nunca entrou
    c.cookies.set(auth.DEVICE_COOKIE, "aparelho-da-ana-0123456789")
    r = c.post("/auth/password/login", json=dict(corpo, password="errada"))
    assert r.status_code == 429 and r.json()["error"] == "bloqueado" and erros == []  # senha errada: nem conta
    r = c.post("/auth/password/login", json=corpo)
    assert r.json()["ok"] and auth.COOKIE_NAME in r.cookies                            # o médico, do aparelho dele
    c.cookies.clear()                                                                  # outro navegador
    c.cookies.set(auth.DEVICE_COOKIE, "outro-aparelho-0123456789xx")
    conferiu = []
    real = auth.check_password
    monkeypatch.setattr(auth, "check_password", lambda pw, h: conferiu.append(pw) or real(pw, h))
    for senha in (PW, "errada"):                    # de outro aparelho, nem o hash: o tempo não diz se a senha confere
        assert c.post("/auth/password/login", json=dict(corpo, password=senha)).json()["error"] == "bloqueado"
    assert conferiu == []


def test_codigos_da_nova_senha_por_ip_nao_gastam_os_do_dono(monkeypatch):
    """De um IP só, 5 pedidos de código para o mesmo e-mail por hora: quem sabe só o e-mail não esgota sozinho os
    códigos da hora, e o dono, de outro lugar, ainda pede o dele."""
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    de = lambda ip: {"cf-connecting-ip": ip}                                           # noqa: E731
    for _ in range(5):
        assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=de("203.0.113.9")).json()["ok"]
    r = c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=de("203.0.113.9"))
    assert r.status_code == 429 and r.json()["error"] == "limite"
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=de("198.51.100.7")).json()["ok"]
    assert c.post("/auth/password/forgot", json={"email": "bia@clinica.com.br"}, headers=de("203.0.113.9")).json()["ok"]


def test_conta_google_que_cria_a_primeira_senha_recebe_o_aviso_de_criada(monkeypatch):
    from app import db
    fake = _Fake(_user("gabi@clinica.com.br", pw=None))
    c = _client(monkeypatch, fake)
    monkeypatch.setattr(db, "get_user", lambda uid: next((u for u in fake.users.values() if u["id"] == uid), None))
    c.post("/auth/password/forgot", json={"email": "gabi@clinica.com.br"})
    tk = c.post("/auth/password/reset/verify", json={"email": "gabi@clinica.com.br", "code": fake.sent[-1][1]}).json()["ticket"]
    assert c.post("/auth/password/reset", json={"ticket": tk, "password": "Nova!12ab"}).json()["ok"]
    assert fake.sent[-1] == ("gabi@clinica.com.br", "", "created")
    from app import mailer
    assert "foi criada" in mailer.render("created", when="31/10/2026 às 22:00")[0]


def test_sair_vindo_de_outro_site_nao_desloga_nem_apaga(monkeypatch):
    """Um link (ou imagem) de outro site para /auth/logout não tira o médico do app nem apaga os rascunhos deste
    navegador (Clear-Site-Data). O Sair do próprio site (ou digitado) continua saindo, e leva junto o cadastro pelo
    Google que ficou no meio e as conexões começadas."""
    from fastapi.testclient import TestClient
    from app import server
    c = TestClient(server.app)
    for site in ("cross-site", "same-site"):
        r = c.get("/auth/logout", headers={"sec-fetch-site": site}, follow_redirects=False)
        assert r.status_code in (302, 307) and "clear-site-data" not in r.headers and not r.headers.get_list("set-cookie")
    for site in ("same-origin", "none", None):
        r = c.get("/auth/logout", headers={"sec-fetch-site": site} if site else {}, follow_redirects=False)
        apaga = " ".join(r.headers.get_list("set-cookie"))
        assert r.headers["clear-site-data"] == '"storage"'
        for nome in (auth.COOKIE_NAME, server.GREG_COOKIE, auth.OAUTH_COOKIE, auth.CAL_COOKIE):
            assert nome + "=" in apaga, nome


def test_boas_vindas_vao_na_sessao_da_conta_nova(monkeypatch):
    """A sessão da conta que acabou de nascer leva a marca; o /me diz (só com a conta já usando o app) e a agenda a tira
    ao mostrar. Outra conta neste navegador (outra sessão) não a recebe."""
    from fastapi.testclient import TestClient
    from app import db, server
    contas = {"u1": {"id": "u1", "email": "ana@clinica.com.br", "name": "Ana", "sv": 0, "crm_status": "verificado"},
              "u2": {"id": "u2", "email": "bia@clinica.com.br", "name": "Bia", "sv": 0, "crm_status": "pendente"}}
    monkeypatch.setattr(db, "get_user", lambda uid: dict(contas[uid]) if uid in contas else None)
    c = TestClient(server.app)
    c.cookies.clear()                       # o cookie que a resposta deixou sai: só o deste passo
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u1", "sv": 0, "bv": 1}))
    assert c.get("/me").json()["boas_vindas"] is True and "boas_vindas" not in c.get("/me").json()["user"]
    r = c.post("/me/boas-vindas", json={})
    assert r.json() == {"ok": True} and "bv" not in auth.unsign(r.cookies[auth.COOKIE_NAME])
    assert c.get("/me").json()["boas_vindas"] is False                               # não voltam ao recarregar
    c.cookies.clear()                       # o cookie que a resposta deixou sai: só o deste passo
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u1", "sv": 0}))
    assert c.get("/me").json()["boas_vindas"] is False                               # outra sessão: sem a marca
    c.cookies.clear()                       # o cookie que a resposta deixou sai: só o deste passo
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u2", "sv": 0, "bv": 1}))
    assert c.get("/me").json()["boas_vindas"] is False                               # pendente: só quando liberar
    assert c.post("/me/boas-vindas", json={}).status_code == 403                     # e a marca fica para depois


def test_limites_dos_codigos_contam_so_o_que_enviou_e_poupam_o_aparelho_conhecido(monkeypatch):
    """O pedido que não envia (o código de agora há pouco ainda vale) não gasta os 5 por hora deste IP; o aparelho de onde
    a conta já entrou fica fora dos limites do e-mail (e do teto do banco); o cadastro também tem os 5 por e-mail + IP."""
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    ip = {"cf-connecting-ip": "203.0.113.20"}
    tetos = []
    monkeypatch.setattr(db, "new_login_code", lambda e, h, teto=True: tetos.append(teto) or ("aguarde", 20))
    for _ in range(8):                                                     # nenhum envia: nenhum conta
        assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=ip).json()["sent"] is False
    server._RL.pop(("login_code", server._rl_ip("203.0.113.20")), None)   # (o limite geral do IP é outro balde)
    monkeypatch.setattr(db, "new_login_code", lambda e, h, teto=True: tetos.append(teto) or ("ok", 0))
    for _ in range(5):
        assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=ip).json()["sent"] is True
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=ip).json()["error"] == "limite"
    assert all(tetos)
    monkeypatch.setattr(db, "device_known", lambda uid, dev: dev == auth.device_hash("aparelho-da-ana-0123456789"))
    c.cookies.set(auth.DEVICE_COOKIE, "aparelho-da-ana-0123456789")
    server._RL.pop(("login_code", server._rl_ip("203.0.113.20")), None)   # (o limite geral do IP é outro balde)
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}, headers=ip).json()["sent"] is True
    assert tetos[-1] is False                                              # o aparelho conhecido: fora do teto do e-mail
    # cadastro: o mesmo balde
    c = _client(monkeypatch, _Fake())
    novo = {"cf-connecting-ip": "203.0.113.30"}
    for _ in range(5):
        assert c.post("/auth/signup/start", json=_novo(), headers=novo).json()["ok"]
    assert c.post("/auth/signup/start", json=_novo(), headers=novo).json()["error"] == "limite"
    assert c.post("/auth/signup/start", json=_novo(), headers={"cf-connecting-ip": "198.51.100.30"}).json()["ok"]


def test_erradas_demais_no_email_dizem_que_um_codigo_novo_nao_ajuda(monkeypatch):
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    monkeypatch.setattr(db, "check_login_code", lambda e, h, soma=True: ("bloqueado_email", 0))
    r = c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": "123456"})
    assert r.status_code == 429 and r.json()["error"] == "tentativas_email"
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-login.html"), encoding="utf-8").read()
    assert "e === 'tentativas_email' ? 'Muitas tentativas erradas para este e-mail." in html


def test_aparelho_conhecido_no_bloqueio_tem_poucas_senhas_e_nao_destranca_os_outros(monkeypatch):
    """Durante o bloqueio, o aparelho conhecido tem 5 senhas a cada 15 min (as erradas dele não contam na conta); a
    entrada dele não tira o bloqueio dos outros aparelhos."""
    from app import db, server
    fake = _Fake(_user("ana@clinica.com.br", locked_s=600))
    c = _client(monkeypatch, fake)
    conhecido = auth.device_hash("aparelho-da-ana-0123456789")
    monkeypatch.setattr(db, "device_known", lambda uid, dev: dev == conhecido)
    zerou = []
    monkeypatch.setattr(db, "login_succeeded", lambda uid: zerou.append(uid))
    c.cookies.set(auth.DEVICE_COOKIE, "aparelho-da-ana-0123456789")
    corpo = {"email": "ana@clinica.com.br", "password": PW}
    assert c.post("/auth/password/login", json=corpo).json()["ok"] and zerou == []     # entra, o bloqueio fica
    for _ in range(4):
        assert c.post("/auth/password/login", json=dict(corpo, password="errada")).json()["error"] == "bloqueado"
    assert c.post("/auth/password/login", json=corpo).json()["error"] == "bloqueado"   # 5 por 15 min, até a certa
    server._RL.clear()


def test_nova_senha_do_aparelho_conhecido_nao_esbarra_nos_chutes_de_outros(monkeypatch):
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    somas = []
    monkeypatch.setattr(db, "check_login_code", lambda e, h, soma=True: somas.append(soma) or ("errado", 3))
    c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": "123456"})
    monkeypatch.setattr(db, "device_known", lambda uid, dev: dev == auth.device_hash("aparelho-da-ana-0123456789"))
    c.cookies.set(auth.DEVICE_COOKIE, "aparelho-da-ana-0123456789")
    c.post("/auth/password/reset/verify", json={"email": "ana@clinica.com.br", "code": "123456"})
    assert somas == [True, False]


def test_criar_a_primeira_senha_tem_o_e_mail_do_codigo_proprio(monkeypatch):
    """A conta só Google que pede "Prefiro criar uma senha" recebe o código de criar (não "nova senha", nem "sua senha
    atual continua valendo")."""
    from app import mailer
    fake = _Fake(_user("gabi@clinica.com.br", pw=None))
    c = _client(monkeypatch, fake)
    c.post("/auth/password/forgot", json={"email": "gabi@clinica.com.br"})
    assert fake.sent[-1][2] == "reset_criar"
    assunto, _, texto = mailer.render("reset_criar", code="123456")
    assert "criar uma senha" in assunto and "continua valendo" not in texto
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"})
    assert fake.sent[-1][2] == "reset"
