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
