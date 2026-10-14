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


# ----- login por e-mail com código (banco e e-mail simulados) -----

def test_safe_next():
    assert auth.safe_next("/opendoctor-agenda.html#pacientes") == "/opendoctor-agenda.html#pacientes"
    assert auth.safe_next("/opendoctor-prontuario.html?x=1") == "/opendoctor-prontuario.html?x=1"
    for bad in ("https://evil.com", "//evil.com", "/\\evil.com", "javascript:alert(1)", "", None,
                "/auth/logout", "/a b", "/" + "x" * 400):
        assert auth.safe_next(bad) == auth.HOME
    assert auth.with_welcome(auth.HOME) == auth.HOME + "?bemvindo=1"
    assert auth.with_welcome(auth.HOME + "#pacientes") == auth.HOME + "?bemvindo=1#pacientes"
    assert auth.with_welcome("/opendoctor-integracao.html") == "/opendoctor-integracao.html"


def test_code_hash():
    assert auth.code_hash("a@b.com", "123456") != auth.code_hash("c@d.com", "123456")
    c = auth.new_code()
    assert len(c) == 6 and c.isdigit()


class _Fake:
    def __init__(self, users=()):
        self.codes, self.users, self.sent = {}, {u: {"id": "u-" + u, "email": u} for u in users}, []


def _client(monkeypatch, fake, configured=True):
    from fastapi.testclient import TestClient
    from app import db, mailer
    server._RL.clear()
    monkeypatch.setattr(mailer, "configured", lambda: configured)
    monkeypatch.setattr(mailer, "send_login_code", lambda to, code: fake.sent.append((to, code)))
    monkeypatch.setattr(db, "new_login_code", lambda e, h: (fake.codes.__setitem__(e, h), ("ok", 0))[1])

    def check(e, h):
        if fake.codes.get(e) == h:
            fake.codes.pop(e)
            return "ok", 0
        return ("errado", 4) if e in fake.codes else ("expirado", 0)
    monkeypatch.setattr(db, "check_login_code", check)
    monkeypatch.setattr(db, "user_by_email", lambda e: fake.users.get(e))
    monkeypatch.setattr(db, "touch_login", lambda uid: None)
    monkeypatch.setattr(db, "create_email_user", lambda e, n: fake.users.setdefault(e, {"id": "u-" + e, "email": e, "name": n}))
    return TestClient(server.app)


def test_email_login_usuario_existente(monkeypatch):
    fake = _Fake(users=["ana@clinica.com.br"])
    c = _client(monkeypatch, fake)
    r = c.post("/auth/email/start", json={"email": "Ana@Clinica.com.br "})
    assert r.status_code == 200 and fake.sent[0][0] == "ana@clinica.com.br"
    code = fake.sent[0][1]
    r = c.post("/auth/email/verify", json={"email": "ana@clinica.com.br", "code": "000000"})
    assert r.status_code == 400 and r.json()["error"] == "codigo_incorreto"
    r = c.post("/auth/email/verify", json={"email": "ana@clinica.com.br", "code": code, "next": "/opendoctor-agenda.html#pacientes"})
    assert r.json() == {"ok": True, "redirect": "/opendoctor-agenda.html#pacientes"}
    assert auth.COOKIE_NAME in r.cookies


def test_email_cadastro_novo(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    r1 = c.post("/auth/email/start", json={"email": "novo@clinica.com.br"})
    r2 = c.post("/auth/email/start", json={"email": "ana@clinica.com.br"})
    assert r1.json() == r2.json()                       # não revela se o e-mail tem conta
    code = fake.sent[0][1]
    r = c.post("/auth/email/verify", json={"email": "novo@clinica.com.br", "code": code})
    j = r.json()
    assert j["signup"] and j["ticket"] and auth.COOKIE_NAME not in r.cookies
    assert c.post("/auth/email/signup", json={"ticket": j["ticket"], "name": "Dra. Nova", "terms": False}).json()["error"] == "termos"
    assert c.post("/auth/email/signup", json={"ticket": j["ticket"], "name": " ", "terms": True}).json()["error"] == "nome"
    assert c.post("/auth/email/signup", json={"ticket": "x.y", "name": "Dra. Nova", "terms": True}).json()["error"] == "sessao_expirada"
    r = c.post("/auth/email/signup", json={"ticket": j["ticket"], "name": "  Dra.   Nova ", "terms": True})
    assert r.json()["redirect"] == auth.HOME + "?bemvindo=1" and auth.COOKIE_NAME in r.cookies
    assert fake.users["novo@clinica.com.br"]["name"] == "Dra. Nova"


def test_email_erros(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake, configured=False)
    assert c.post("/auth/email/start", json={"email": "a@b.com"}).status_code == 503
    c = _client(monkeypatch, fake)
    assert c.post("/auth/email/start", json={"email": "abc"}).json()["error"] == "email_invalido"
    assert c.post("/auth/email/verify", json={"email": "a@b.com", "code": "12"}).json()["error"] == "codigo_invalido"
    assert c.post("/auth/email/verify", json={"email": "a@b.com", "code": "123456"}).json()["error"] == "codigo_expirado"
    codes = [c.post("/auth/email/start", json={"email": "x%d@b.com" % i}).status_code for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429      # limite por IP
