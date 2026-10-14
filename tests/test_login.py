"""Tela de login: e-mail vira login_hint do Google (sem banco, sem rede)."""
import asyncio
import json
import urllib.parse

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
    assert auth.with_welcome(auth.HOME) == auth.HOME + "?bemvindo=1"
    assert auth.with_welcome(auth.HOME + "#pacientes") == auth.HOME + "?bemvindo=1#pacientes"
    assert auth.with_welcome("/opendoctor-integracao.html") == "/opendoctor-integracao.html"


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


class _Fake:
    def __init__(self, users=None):
        self.users = users or {}          # email -> {"id","hash","sv","locked_s"}
        self.codes, self.sent, self.failed = {}, [], {}


def _client(monkeypatch, fake, configured=True):
    from fastapi.testclient import TestClient
    from app import db, mailer
    server._RL.clear()
    monkeypatch.setattr(mailer, "configured", lambda: configured)
    monkeypatch.setattr(mailer, "send_code", lambda to, code, purpose: fake.sent.append((to, code, purpose)))
    monkeypatch.setattr(db, "new_login_code", lambda e, h: (fake.codes.__setitem__(e, h), ("ok", 0))[1])
    monkeypatch.setattr(db, "discard_login_code", lambda e: fake.codes.pop(e, None))

    def check(e, h):
        if fake.codes.get(e) == h:
            fake.codes.pop(e)
            return "ok", 0
        return ("errado", 4) if e in fake.codes else ("expirado", 0)
    monkeypatch.setattr(db, "check_login_code", check)
    monkeypatch.setattr(db, "account", lambda e: None if e not in fake.users else {"password": bool(fake.users[e].get("hash"))})
    monkeypatch.setattr(db, "user_by_email", lambda e: fake.users.get(e))

    def info(e):
        u = fake.users.get(e)
        return None if not u else {"id": u["id"], "hash": u.get("hash"), "sv": u.get("sv", 0), "locked_s": u.get("locked_s", 0)}
    monkeypatch.setattr(db, "password_login_info", info)

    def failed(uid):
        fake.failed[uid] = fake.failed.get(uid, 0) + 1
        return (0, 900) if fake.failed[uid] >= 5 else (5 - fake.failed[uid], 0)
    monkeypatch.setattr(db, "login_failed", failed)
    monkeypatch.setattr(db, "login_succeeded", lambda uid: fake.failed.pop(uid, None))

    def create(e, n, ph):
        fake.users.setdefault(e, {"id": "u-" + e, "email": e, "name": n, "hash": ph, "sv": 0})
        return fake.users[e]
    monkeypatch.setattr(db, "create_email_user", create)

    def set_pw(uid, ph):
        u = next(u for u in fake.users.values() if u["id"] == uid)
        u.update(hash=ph, sv=u.get("sv", 0) + 1)
        return u
    monkeypatch.setattr(db, "set_password", set_pw)
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
    assert c.post("/auth/signup/start", json={"email": "novo@clinica.com.br", "name": "Dra. Nova", "password": "fraca"}).json() == \
        {"error": "senha_fraca", "rules": ["tamanho", "letras", "especial"]}
    assert c.post("/auth/signup/start", json={"email": "novo@clinica.com.br", "name": " ", "password": PW}).json()["error"] == "nome"
    assert c.post("/auth/signup/start", json={"email": "ana@clinica.com.br", "name": "Ana", "password": PW}).status_code == 409
    r = c.post("/auth/signup/start", json={"email": "novo@clinica.com.br", "name": "  Dra.  Nova ", "password": PW})
    ticket = r.json()["ticket"]
    to, code, purpose = fake.sent[-1]
    assert (to, purpose) == ("novo@clinica.com.br", "signup") and "novo@clinica.com.br" not in fake.users   # ainda não criou
    assert PW not in ticket
    assert c.post("/auth/signup/verify", json={"ticket": ticket, "code": "000000"}).json()["error"] == "codigo_incorreto"
    assert c.post("/auth/signup/verify", json={"ticket": "x.y", "code": code}).json()["error"] == "sessao_expirada"
    r = c.post("/auth/signup/verify", json={"ticket": ticket, "code": code})
    assert r.json()["redirect"] == auth.HOME + "?bemvindo=1" and auth.COOKIE_NAME in r.cookies
    u = fake.users["novo@clinica.com.br"]
    assert u["name"] == "Dra. Nova" and auth.check_password(PW, u["hash"])
    # o código de cadastro não serve para redefinir senha
    c.post("/auth/signup/resend", json={"ticket": ticket})
    code2 = fake.sent[-1][1]
    assert c.post("/auth/password/reset", json={"email": "novo@clinica.com.br", "code": code2, "password": "Outra!12ab"}).json()["error"] == "codigo_incorreto"


def test_esqueci_a_senha(monkeypatch):
    fake = _Fake(dict(_user("ana@clinica.com.br"), **_user("google@clinica.com.br", pw=None)))
    c = _client(monkeypatch, fake)
    assert c.post("/auth/password/forgot", json={"email": "ninguem@clinica.com.br"}).json()["ok"]   # não revela nem envia
    assert fake.sent == []
    c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"})
    to, code, purpose = fake.sent[-1]
    assert purpose == "reset"
    assert c.post("/auth/password/reset", json={"email": "ana@clinica.com.br", "code": code, "password": "fraca"}).json()["error"] == "senha_fraca"
    r = c.post("/auth/password/reset", json={"email": "ana@clinica.com.br", "code": code, "password": "Nova!12ab"})
    assert r.json()["ok"] and auth.COOKIE_NAME in r.cookies
    assert fake.users["ana@clinica.com.br"]["sv"] == 1                       # outras sessões caem
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json()["error"] == "senha_incorreta"
    # conta só Google pode criar uma senha pelo mesmo caminho
    c.post("/auth/password/forgot", json={"email": "google@clinica.com.br"})
    r = c.post("/auth/password/reset", json={"email": "google@clinica.com.br", "code": fake.sent[-1][1], "password": "Minha!12ab"})
    assert r.json()["ok"]


def test_sem_provedor_de_email(monkeypatch):
    c = _client(monkeypatch, _Fake(_user("ana@clinica.com.br")), configured=False)
    assert c.post("/auth/email/check", json={"email": "novo@b.com"}).json()["email_ok"] is False
    assert c.post("/auth/signup/start", json={"email": "novo@b.com", "name": "Nova", "password": PW}).status_code == 503
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).status_code == 503
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json()["ok"]   # senha funciona


def test_envio_falhou_descarta_codigo(monkeypatch):
    from app import mailer
    fake = _Fake()
    c = _client(monkeypatch, fake)

    def falha(to, code, purpose):
        raise RuntimeError("resend 500")
    monkeypatch.setattr(mailer, "send_code", falha)
    r = c.post("/auth/signup/start", json={"email": "novo@clinica.com.br", "name": "Nova", "password": PW})
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
    r = TestClient(server.app).get("/integrations/google/connect", follow_redirects=False)
    assert r.headers["location"] == "/opendoctor-login.html?next=%2Fopendoctor-integracao.html"
    assert auth.safe_next("/opendoctor-integracao.html") == "/opendoctor-integracao.html"




def test_reenvio_dentro_de_30s_nao_finge_envio(monkeypatch):
    from app import db
    fake = _Fake(_user("ana@clinica.com.br"))
    c = _client(monkeypatch, fake)
    j = c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).json()
    assert j == {"ok": True, "resend_in": 30, "sent": True}
    monkeypatch.setattr(db, "new_login_code", lambda e, h: ("aguarde", 12))
    n = len(fake.sent)
    assert c.post("/auth/password/forgot", json={"email": "ana@clinica.com.br"}).json() == {"ok": True, "resend_in": 12, "sent": False}
    r = c.post("/auth/signup/start", json={"email": "novo@clinica.com.br", "name": "Nova", "password": PW}).json()
    assert r["ticket"] and r["sent"] is False and r["resend_in"] == 12 and len(fake.sent) == n   # segue com o código anterior


def test_regras_aceitam_acentos():
    assert auth.password_problems("éXEMPLO12!") == []           # maiúscula/minúscula com acento valem
    assert auth.password_problems("ÉXEMPLO12!") == ["letras"]
