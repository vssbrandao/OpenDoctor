"""Perfil (web/opendoctor-perfil.html): só com login, no menu do "Configurações" do pé da sidebar de todas as telas,
só para ver (os dados vêm de /me e /me/medico) e com o Sair (/auth/logout). O que a página faz no navegador:
tests/e2e/perfil.mjs."""
import os
import re

from fastapi.testclient import TestClient

from app import auth, server
from tests.fake_receitas import FakeReceitas

WEB = server.WEB_DIR
PAGINA = "opendoctor-perfil.html"


def _html(nome):
    return open(os.path.join(WEB, nome), encoding="utf-8").read()


def test_perfil_so_com_login():
    c = TestClient(server.app)
    r = c.get("/" + PAGINA, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/opendoctor-login.html"), r.headers.get("location")


def test_perfil_abre_logado(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u-1", "email": "medica@exemplo.com", "sv": 0})
    r = TestClient(server.app).get("/" + PAGINA)
    assert r.status_code == 200 and "<title>OpenDoctor | Perfil</title>" in r.text


def test_perfil_no_menu_de_todas_as_telas():
    """Toda tela com o menu lateral tem o Perfil uma vez, no menu do "Configurações" do pé (como o "Settings" da Sana,
    pedido do usuário em 14/11): Configurações, Integrações, Perfil e Sair. O meio do menu não tem mais esses itens; nas
    três telas deles, o "Configurações" do pé é o marcado."""
    com_menu = sorted(f for f in os.listdir(WEB) if f.endswith(".html") and '<aside class="nav">' in _html(f))
    assert {"opendoctor-agenda.html", "opendoctor-integracao.html", "opendoctor-configuracoes.html", PAGINA} <= set(com_menu)
    for f in com_menu:
        html = _html(f)
        nav = re.search(r'<aside class="nav">(.*?)</aside>', html, re.S).group(1)
        nomes = re.findall(r'<div class="item[^"]*"[^>]*\bdata-tip="([^"]*)"', nav)
        assert nomes.count("Configurações") == 1 and nomes[-1] == "Configurações", (f, nomes)   # só o do pé
        assert "Perfil" not in nomes and "Integrações" not in nomes, (f, nomes)
        menu = re.search(r'<div class="cfg-menu" id="cfgMenu" role="menu" hidden>(.*?)\n    </div>', html, re.S).group(1)
        ops = re.findall(r'<a class="cfg-menu-op" role="menuitem" href="([^"]*)">([^<]*)</a>', menu)
        assert ops == [("opendoctor-configuracoes.html", "Configurações"), ("opendoctor-integracao.html", "Integrações"),
                       (PAGINA, "Perfil"), ("/auth/logout", "Sair")], (f, ops)
        ativo = re.search(r'<div class="(item[^"]*)" id="navCfg"', html).group(1)
        assert ("active" in ativo) == (f in ("opendoctor-configuracoes.html", "opendoctor-integracao.html", PAGINA)), f


def test_perfil_tem_o_sair_e_so_grava_a_exclusao():
    """Os dados da conta só se veem (quem grava é Configurações). A única escrita do Perfil é Excluir conta: um POST a
    /me/excluir, com o único campo editável, o e-mail digitado na confirmação (decisão do dono, 2026-11-05)."""
    html = _html(PAGINA)
    assert re.search(r'<button class="cfg-btn" type="button" id="pfLogout" data-href="/auth/logout">Sair</button>', html)
    scripts = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    assert set(re.findall(r"pede\('([^']+)'\)", scripts)) == {"/me", "/me/medico"}
    # um fetch para ler (pede), outro, o único com método, para excluir, e o GET /me do menu do pé (o e-mail da conta) —
    # qualquer outra escrita aparece aqui
    assert scripts.count("fetch(") == 3 and re.findall(r"fetch\('([^']+)'", scripts) == ["/me/excluir", "/me"]
    assert scripts.count("method") == 1 and "method: 'POST'" in scripts
    assert not re.search(r"XMLHttpRequest|sendBeacon|\.submit\(|formaction|action=", scripts + html)
    assert re.findall(r"<form\b[^>]*\bid=\"(\w+)\"", html) == ["pfExForm"] and html.count("<form") == 1
    editaveis = re.findall(r"<input(?![^>]*\breadonly\b)[^>]*\bid=\"(\w+)\"", html)
    assert editaveis == ["pfExEmail"], editaveis


def test_dados_que_o_perfil_le(monkeypatch):
    """/me (e-mail) e /me/medico (nome, CRM, UF, especialidade, conferido) com a sessão; sem ela, /me/medico dá 401."""
    fake = FakeReceitas({"u-1": {"name": "Dra. Ana Souza", "crm": "123456", "crm_uf": "SP", "especialidade": "Clínica médica"}})
    fake.install(monkeypatch.setattr)
    c = TestClient(server.app)
    assert c.get("/me/medico").status_code == 401
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u-1", "email": "medica@exemplo.com", "name": "Ana",
                                                                "sv": 0, "crm_status": "verificado"})
    me = c.get("/me").json()
    assert me["user"]["email"] == "medica@exemplo.com"
    m = c.get("/me/medico").json()
    assert m["medico"]["name"] == "Dra. Ana Souza" and m["medico"]["crm"] == "123456" and m["medico"]["crm_uf"] == "SP"
    assert m["medico"]["especialidade"] == "Clínica médica" and m["crm_conferido"] is True


def test_sair_do_perfil_desloga(monkeypatch):
    """O botão navega para /auth/logout (mesmo site): a sessão sai e vai para o login."""
    c = TestClient(server.app)
    r = c.get("/auth/logout", headers={"sec-fetch-site": "same-origin", "referer": "https://opendoctor.app/" + PAGINA},
              follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/opendoctor-login.html"
    assert auth.COOKIE_NAME in r.headers.get("set-cookie", "") and r.headers.get("clear-site-data") == '"storage"'
