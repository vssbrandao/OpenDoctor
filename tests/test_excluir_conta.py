"""Excluir a conta (Perfil → POST /me/excluir): só a conta da sessão, com o e-mail dela digitado, de um pedido JSON do
próprio site. A conta é encerrada no banco (db.excluir_conta: nada do prontuário é apagado — o teste de banco está em
tests/test_db_integration.py), este navegador sai como no Sair, a sessão não volta e o médico recebe o aviso.
O que a página faz: tests/e2e/perfil.mjs. Banco e e-mail simulados; nada toca banco de verdade nem o Resend."""
import pytest
from fastapi.testclient import TestClient

from app import auth, db, mailer, server

CONTA = {"id": "u1", "email": "ana@clinica.com.br", "name": "Ana Lima", "sv": 0, "crm_status": "verificado", "crm_fonte": "cfm"}


@pytest.fixture
def cli(monkeypatch):
    """Sessão de verdade (cookie assinado) da conta u1; a exclusão simulada marca a conta e o get_user deixa de achá-la."""
    server._RL.clear()
    estado = {"excluida": False, "pedidos": [], "avisos": []}

    def get_user(uid):
        return dict(CONTA) if uid == "u1" and not estado["excluida"] else None

    def excluir(uid, email):
        estado["pedidos"].append((uid, email))
        if estado["excluida"] or email != CONTA["email"]:
            return None
        estado["excluida"] = True
        return {"email": CONTA["email"], "name": CONTA["name"]}
    monkeypatch.setattr(db, "get_user", get_user)
    monkeypatch.setattr(db, "excluir_conta", excluir)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send_account_deleted", lambda to, name="": estado["avisos"].append((to, name)))
    c = TestClient(server.app)
    c.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "u1", "sv": 0}))
    c.estado = estado
    return c


def test_sem_login_nao_exclui(monkeypatch):
    chamou = []
    monkeypatch.setattr(db, "excluir_conta", lambda *a: chamou.append(a))
    r = TestClient(server.app).post("/me/excluir", json={"email": "ana@clinica.com.br"})
    assert r.status_code == 401 and chamou == []


@pytest.mark.parametrize("email", ["", "outra@clinica.com.br", "ana@clinica.com", " ", None])
def test_email_que_nao_confere_nao_exclui(cli, email):
    r = cli.post("/me/excluir", json={"email": email})
    assert r.status_code == 400 and r.json() == {"error": "email_nao_confere"}
    assert cli.estado["pedidos"] == [] and not cli.estado["excluida"]
    assert "ana@clinica.com.br" not in r.text                    # a resposta nunca devolve o e-mail da conta


def test_corpo_que_nao_e_json_nao_exclui(cli):
    """Um formulário de outro site só manda text/plain ou form: sem JSON, o e-mail não chega e nada muda."""
    for kw in ({"content": '{"email": "ana@clinica.com.br"}', "headers": {"content-type": "text/plain"}},
               {"data": {"email": "ana@clinica.com.br"}}):
        r = cli.post("/me/excluir", **kw)
        assert r.status_code == 400 and r.json()["error"] == "email_nao_confere"
    assert cli.estado["pedidos"] == []


@pytest.mark.parametrize("site", ["cross-site", "same-site", "none"])
def test_pedido_de_outro_site_nao_exclui(cli, site):
    r = cli.post("/me/excluir", json={"email": "ana@clinica.com.br"}, headers={"sec-fetch-site": site})
    assert r.status_code == 403 and r.json() == {"error": "origem"} and cli.estado["pedidos"] == []


def test_exclui_com_o_email_da_conta_e_este_navegador_sai(cli):
    r = cli.post("/me/excluir", json={"email": "  Ana@Clinica.com.BR "}, headers={"sec-fetch-site": "same-origin"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert cli.estado["pedidos"] == [("u1", "ana@clinica.com.br")]         # a conta da sessão, nunca um id do corpo
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith(auth.COOKIE_NAME + "=") and ("Max-Age=0" in c or "expires=" in c.lower()) for c in cookies)
    for nome in (server.GREG_COOKIE, auth.OAUTH_COOKIE, auth.CAL_COOKIE):
        assert any(c.startswith(nome + "=") and "Path=/auth/" in c for c in cookies), nome
    assert r.headers.get("clear-site-data") == '"storage"'
    assert cli.estado["avisos"] == [("ana@clinica.com.br", "Ana Lima")]


def test_depois_de_excluir_a_sessao_nao_volta(cli):
    """O mesmo cookie (ou o de outro aparelho) já não entra: o get_user não acha a conta excluída."""
    sessao = cli.cookies.get(auth.COOKIE_NAME)
    assert cli.post("/me/excluir", json={"email": "ana@clinica.com.br"}).status_code == 200
    outro = TestClient(server.app)
    outro.cookies.set(auth.COOKIE_NAME, sessao)
    assert outro.get("/me").json()["logged_in"] is False
    assert outro.get("/me/medico").status_code == 401
    r = outro.get("/opendoctor-agenda.html", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/opendoctor-login.html")
    assert outro.post("/me/excluir", json={"email": "ana@clinica.com.br"}).status_code == 401


def test_aviso_que_falha_nao_desfaz_a_exclusao(cli, monkeypatch, capsys):
    def falha(to, name=""):
        raise RuntimeError("resend fora: ana@clinica.com.br")
    monkeypatch.setattr(mailer, "send_account_deleted", falha)
    r = cli.post("/me/excluir", json={"email": "ana@clinica.com.br"})
    assert r.status_code == 200 and cli.estado["excluida"]
    assert "ana@clinica.com.br" not in capsys.readouterr().out            # nada pessoal no log


def test_sem_o_resend_exclui_sem_aviso(cli, monkeypatch):
    monkeypatch.setattr(mailer, "configured", lambda: False)
    assert cli.post("/me/excluir", json={"email": "ana@clinica.com.br"}).status_code == 200
    assert cli.estado["excluida"] and cli.estado["avisos"] == []


def test_sem_a_migracao_nada_muda(cli, monkeypatch):
    def pendente(uid, email):
        raise db.MigracaoPendente("0020_conta_excluida.sql")
    monkeypatch.setattr(db, "excluir_conta", pendente)
    r = cli.post("/me/excluir", json={"email": "ana@clinica.com.br"})
    assert r.status_code == 503 and r.json() == {"error": "indisponivel"}
    assert auth.COOKIE_NAME not in "".join(r.headers.get_list("set-cookie"))   # a sessão continua


def test_erro_do_banco_nao_sai_do_navegador(cli, monkeypatch, capsys):
    def quebra(uid, email):
        raise RuntimeError("falha com ana@clinica.com.br")
    monkeypatch.setattr(db, "excluir_conta", quebra)
    r = cli.post("/me/excluir", json={"email": "ana@clinica.com.br"})
    assert r.status_code == 500 and "clear-site-data" not in r.headers
    assert "ana@clinica.com.br" not in capsys.readouterr().out


def test_limite_de_tentativas_por_conta(cli):
    for _ in range(server.RATE_LIMITS["excluir_conta"][0]):
        assert cli.post("/me/excluir", json={"email": "errado@clinica.com.br"}).status_code == 400
    r = cli.post("/me/excluir", json={"email": "ana@clinica.com.br"})
    assert r.status_code == 429 and not cli.estado["excluida"]


def test_texto_do_aviso():
    subj, html, text = mailer.render("excluida", name="Ana Lima", when="05/11/2026 às 10:00 (horário de Brasília)")
    assert subj == "Sua conta do OpenDoctor foi excluída"
    for trecho in ("05/11/2026 às 10:00", "todos os aparelhos", "agenda do Google foi desconectada",
                   "prazo legal (Lei 13.787/2018)", "conta nova com este e-mail", "privacidade@opendoctor.app"):
        assert trecho in text, trecho
    assert "{" not in text and "Ana" in text


def test_agenda_que_volta_do_google_depois_da_exclusao_nao_fica(monkeypatch):
    """O médico estava na tela do Google conectando a agenda e excluiu a conta noutra aba: a troca grava o token, mas a
    releitura já não acha a conta (excluída) e a agenda é desconectada na hora — não espera a limpeza diária."""
    import urllib.parse as up
    from app import integrations
    gravou, tirou = [], []
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(integrations, "exchange_and_store", lambda prov, code, uid: gravou.append((prov, uid)))
    monkeypatch.setattr(integrations, "disconnect", lambda uid, prov: tirou.append((uid, prov)))
    monkeypatch.setattr(auth, "current_user", lambda request: dict(CONTA))     # a sessão ainda valia na volta
    monkeypatch.setattr(db, "get_user", lambda uid: None)                       # excluída durante a troca
    c = TestClient(server.app)
    r = c.get("/integrations/google/connect", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    r = c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)
    assert gravou == [("google", "u1")] and tirou == [("u1", "google")]
    assert r.headers["location"].endswith("?erro=sessao")


def test_login_pelo_google_de_conta_excluida_no_meio_nao_cria_outra(monkeypatch):
    """Achou a conta pelo e-mail, mas ela foi excluída antes de entrar: não nasce uma conta nova sem o Registro
    profissional (o upsert só atualiza a que existe e devolve None) — volta ao login com o erro de conexão."""
    import urllib.parse as up
    from app import integrations
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(auth, "exchange_login", lambda code: {"email": "ana@clinica.com.br", "email_verified": True,
                                                             "sub": "g1", "name": "Ana", "picture": None})
    monkeypatch.setattr(db, "user_by_email", lambda e: dict(CONTA))
    monkeypatch.setattr(db, "user_by_google_sub", lambda sub: None)
    chamadas = []

    def upsert(*a, **k):
        chamadas.append(k)
        return None                             # excluída entre o user_by_email e a entrada
    monkeypatch.setattr(db, "upsert_user", upsert)
    c = TestClient(server.app)
    r = c.get("/auth/google/login", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    r = c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)
    assert chamadas and all(k.get("so_existente") is True for k in chamadas)
    assert "erro=conexao" in r.headers["location"] and auth.COOKIE_NAME not in r.cookies
