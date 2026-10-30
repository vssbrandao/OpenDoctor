"""Conexão com o calendário (sem banco, sem rede): conexão morta ou sem a permissão da agenda vira "reconectar" em vez
de agenda vazia, e o retorno do Google só grava a agenda na conta logada no mesmo navegador que começou a conexão."""
import datetime
import json
import os
import re
import shutil
import subprocess
import urllib.parse as up

import pytest
from fastapi.testclient import TestClient

from app import auth, db, integrations, server

PASSADO = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
FUTURO = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
CAL_EVENTS = "https://www.googleapis.com/auth/calendar.events"


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class _Tokens:
    """oauth_tokens em memória: (user_id, provedor) → linha."""
    def __init__(self, monkeypatch, refresh="r-1"):
        self.rows = {("u1", "google"): {"access_token": "velho", "refresh_token": refresh, "expires_at": PASSADO}}
        self.posts = []
        monkeypatch.setattr(db, "get_token", lambda uid, p: self.rows.get((uid, p)))
        monkeypatch.setattr(db, "mark_token_dead", self._dead)
        monkeypatch.setattr(db, "update_access_token", lambda *a, **k: None)
        monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
        monkeypatch.setattr(integrations, "_secret", lambda p: "segredo")

    def _dead(self, uid, p, refresh):
        if self.rows[(uid, p)]["refresh_token"] == refresh:
            self.rows[(uid, p)]["refresh_token"] = None

    def google_responde(self, monkeypatch, status, body):
        def post(url, **kw):
            self.posts.append(url)
            return _Resp(status, body)
        monkeypatch.setattr(integrations.httpx, "post", post)


def test_google_recusa_a_renovacao_pede_reconectar_e_para_de_insistir(monkeypatch, capsys):
    t = _Tokens(monkeypatch)
    t.google_responde(monkeypatch, 400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
    with pytest.raises(integrations.NeedsReconnect):
        integrations._access_token("u1", "google")
    assert t.rows[("u1", "google")]["refresh_token"] is None and len(t.posts) == 1
    assert "r-1" not in capsys.readouterr().out                       # o log nunca leva o token
    with pytest.raises(integrations.NeedsReconnect):                  # agenda atualizando: não pede de novo ao Google
        integrations._access_token("u1", "google")
    assert len(t.posts) == 1


def test_falha_passageira_do_google_nao_marca_a_conexao(monkeypatch):
    t = _Tokens(monkeypatch)
    t.google_responde(monkeypatch, 503, {"error": "backendError"})
    assert integrations._access_token("u1", "google") is None
    assert t.rows[("u1", "google")]["refresh_token"] == "r-1"


def test_rede_caida_ao_renovar_nao_derruba_a_agenda(monkeypatch):
    t = _Tokens(monkeypatch)

    def sem_rede(url, **kw):
        raise integrations.httpx.ConnectError("sem rede")
    monkeypatch.setattr(integrations.httpx, "post", sem_rede)
    assert integrations._access_token("u1", "google") is None          # passageiro: sem 500, sem marcar
    t.google_responde(monkeypatch, 200, {"expires_in": 3600})            # 200 sem access_token
    assert integrations._access_token("u1", "google") is None
    assert t.rows[("u1", "google")]["refresh_token"] == "r-1"


def test_rotas_dizem_reconectar_quando_a_conexao_morreu(monkeypatch):
    def morto(*a, **k):
        raise integrations.NeedsReconnect("conexão expirada")
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "connected_providers", lambda uid: {"google": "ana@gmail.com"})
    monkeypatch.setattr(db, "dead_providers", lambda uid: {"google"})
    monkeypatch.setattr(db, "get_token", lambda uid, p: {"scope": "openid email " + CAL_EVENTS})
    monkeypatch.setattr(integrations, "_access_token", morto)
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: {"id": pid, "name": "Ana", "key": "ana"})
    monkeypatch.setattr(db, "find_patients", lambda uid, name: [{"id": 7}])
    c = TestClient(server.app)
    r = c.get("/calendar/events")
    assert r.json() == {"logged_in": True, "connected": "google", "events": [], "needs_reconnect": True, "reason": "expirada"}
    r = c.post("/calendar/events", json={"title": "Consulta", "start": "2026-10-30T10:00:00-03:00", "end": "2026-10-30T10:30:00-03:00"})
    assert r.status_code == 403 and r.json()["needs_reconnect"] and r.json()["reason"] == "expirada"
    r = c.patch("/calendar/events/abc", json={"start": "2026-10-30T10:00:00-03:00", "end": "2026-10-30T10:30:00-03:00"})
    assert r.status_code == 403 and r.json()["reason"] == "expirada"
    assert c.delete("/calendar/events/abc").json()["reason"] == "expirada"
    assert c.post("/prontuario/visits", json={"patient_id": 7}).json() == {"connected": True, "visits": [], "needs_reconnect": True,
                                                                           "reason": "expirada"}
    g = c.get("/integrations/status").json()["providers"]["google"]
    assert g["needs_reconnect"] is True and g["reason"] == "expirada"


def _google_erro(status, reason):
    """Corpo de erro da API do Google Agenda (error.errors[0].reason)."""
    return _Resp(status, {"error": {"code": status, "message": "x", "status": "PERMISSION_DENIED",
                                    "errors": [{"domain": "global", "reason": reason, "message": "x"}]}})


def test_so_falta_de_permissao_pede_reconectar(monkeypatch, capsys):
    """Só o token sem a permissão da agenda pede reconectar; pedidos demais e evento de outra pessoa dizem o porquê."""
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "connected_providers", lambda uid: {"google": "ana@gmail.com"})
    monkeypatch.setattr(integrations, "_headers", lambda uid, p: {})
    c = TestClient(server.app)
    hora = {"start": "2026-10-30T10:00:00-03:00", "end": "2026-10-30T10:30:00-03:00"}
    casos = [(403, "insufficientPermissions", 403, "permissao", True),
             (403, "rateLimitExceeded", 429, "limite", False),
             (429, "rateLimitExceeded", 429, "limite", False),
             (403, "userRateLimitExceeded", 429, "limite", False),
             (403, "forbiddenForNonOrganizer", 403, "proibido", False),
             (403, "requiredAccessLevel", 403, "proibido", False)]
    for g_status, g_reason, status, reason, reconectar in casos:
        resp = _google_erro(g_status, g_reason)
        for metodo in ("post", "patch", "delete"):
            monkeypatch.setattr(integrations.httpx, metodo, lambda *a, **k: resp)
        for r in (c.post("/calendar/events", json=hora), c.patch("/calendar/events/abc", json=hora),
                  c.delete("/calendar/events/abc")):
            assert (r.status_code, r.json()["reason"], r.json()["needs_reconnect"]) == (status, reason, reconectar), g_reason
            assert r.json()["error"][0].isupper()                       # frase para a tela, não o texto do Google
    # o ErrorInfo novo do Google (sem errors[]) também conta como falta de permissão
    resp = _Resp(403, {"error": {"code": 403, "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}})
    monkeypatch.setattr(integrations.httpx, "post", lambda *a, **k: resp)
    assert c.post("/calendar/events", json=hora).json()["reason"] == "permissao"
    # outro erro (ex.: 400 do Google): não pede reconectar nem tem motivo
    resp = _google_erro(400, "invalid")
    monkeypatch.setattr(integrations.httpx, "post", lambda *a, **k: resp)
    r = c.post("/calendar/events", json=hora)
    assert r.status_code == 400 and r.json()["needs_reconnect"] is False and "reason" not in r.json()
    assert "[agenda] o provedor recusou: 403 forbiddenForNonOrganizer" in capsys.readouterr().out


SEM_AGENDA = "openid https://www.googleapis.com/auth/userinfo.email"     # consentimento com a caixa da agenda desmarcada
HORA = {"start": "2026-10-30T10:00:00-03:00", "end": "2026-10-30T10:30:00-03:00"}


def _conta_google(monkeypatch, scope, leitura=None):
    """Médico logado com o Google gravado com `scope` (token ainda válido); `leitura` é o que o Google responde ao
    ler a agenda. Devolve o cliente e a lista das leituras feitas no Google."""
    lidas = []
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "connected_providers", lambda uid: {"google": "ana@gmail.com"})
    monkeypatch.setattr(db, "dead_providers", lambda uid: set())
    monkeypatch.setattr(db, "get_token", lambda uid, p: {"access_token": "at", "refresh_token": "rt", "expires_at": FUTURO,
                                                         "scope": scope} if (uid, p) == ("u1", "google") else None)
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: {"id": pid, "name": "Ana", "key": "ana"})
    monkeypatch.setattr(db, "find_patients", lambda uid, name: [{"id": 7}])
    monkeypatch.setattr(db, "notes_by_event", lambda uid, ids: {})

    def get(url, **kw):
        lidas.append(url)
        return leitura or _Resp(200, {"items": []})
    monkeypatch.setattr(integrations.httpx, "get", get)
    monkeypatch.setattr(integrations.httpx, "post", lambda *a, **k: pytest.fail("não devia ir ao Google"))
    return TestClient(server.app), lidas


def _pede_permissao(c):
    """As rotas que leem a agenda dizem "reconectar: sem permissão" em vez de uma agenda vazia."""
    assert c.get("/calendar/events").json() == {"logged_in": True, "connected": "google", "events": [],
                                                "needs_reconnect": True, "reason": "permissao"}
    assert c.get("/integrations/google/events").json() == {"events": [], "needs_reconnect": True, "reason": "permissao"}
    assert c.post("/prontuario/visits", json={"patient_id": 7}).json() == {"connected": True, "visits": [],
                                                                           "needs_reconnect": True, "reason": "permissao"}


def test_conexao_gravada_sem_a_permissao_da_agenda_pede_reconectar(monkeypatch):
    """Conexões gravadas antes de exchange_and_store conferir a permissão: nada de "Conectado" com a agenda vazia."""
    c, lidas = _conta_google(monkeypatch, SEM_AGENDA)
    g = c.get("/integrations/status").json()["providers"]["google"]
    assert (g["connected"], g["needs_reconnect"], g["reason"]) == (True, True, "permissao")
    _pede_permissao(c)
    r = c.post("/calendar/events", json=dict(HORA, title="Consulta"))
    assert r.status_code == 403 and r.json()["needs_reconnect"] is True and r.json()["reason"] == "permissao"
    assert lidas == []                                                   # o escopo gravado já diz: nem pergunta ao Google
    # com a permissão da agenda (ou sem o escopo gravado, que conta como o pedido) continua "Conectado"
    for scope in ("openid email " + CAL_EVENTS, "https://www.googleapis.com/auth/calendar openid", None):
        c, lidas = _conta_google(monkeypatch, scope)
        g = c.get("/integrations/status").json()["providers"]["google"]
        assert (g["connected"], g["needs_reconnect"], g["reason"]) == (True, False, None), scope
        assert c.get("/calendar/events").json() == {"logged_in": True, "connected": "google", "events": []}
        assert len(lidas) == 1
    # só leitura (conexão de antes de calendar.events): a agenda continua aparecendo, Integrações pede reconectar
    ev = {"id": "e1", "summary": "Consulta", "start": {"dateTime": HORA["start"]}, "end": {"dateTime": HORA["end"]}}
    c, _ = _conta_google(monkeypatch, "openid https://www.googleapis.com/auth/calendar.readonly", _Resp(200, {"items": [ev]}))
    g = c.get("/integrations/status").json()["providers"]["google"]
    assert (g["needs_reconnect"], g["reason"]) == (True, "permissao")
    d = c.get("/calendar/events").json()
    assert [e["id"] for e in d["events"]] == ["e1"] and "needs_reconnect" not in d
    # conexão também morta: o motivo é o mesmo da agenda (só leitura → expirada; sem a agenda → permissão)
    monkeypatch.setattr(db, "dead_providers", lambda uid: {"google"})
    assert c.get("/integrations/status").json()["providers"]["google"]["reason"] == "expirada"
    c, _ = _conta_google(monkeypatch, SEM_AGENDA)
    monkeypatch.setattr(db, "dead_providers", lambda uid: {"google"})
    assert c.get("/integrations/status").json()["providers"]["google"]["reason"] == "permissao"


def test_google_recusa_ler_a_agenda_por_falta_de_permissao(monkeypatch):
    """Sem o escopo gravado, quem diz é o Google: o 403 de permissão ao ler vira "reconectar", não um dia livre."""
    negado = (_google_erro(403, "insufficientPermissions"),
              _Resp(403, {"error": {"code": 403, "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}))
    for resp in negado:
        c, lidas = _conta_google(monkeypatch, None, resp)
        _pede_permissao(c)
        assert len(lidas) == 3
    # outro 403 ao ler (pedidos demais) não pede reconectar
    c, _ = _conta_google(monkeypatch, None, _google_erro(403, "rateLimitExceeded"))
    assert c.get("/calendar/events").json() == {"logged_in": True, "connected": "google", "events": []}


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    return node


def test_faixa_da_agenda_diz_sem_permissao_ou_expirou():
    """A faixa #calReconnect da agenda: o texto em negrito segue o motivo que o servidor manda."""
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-agenda.html"), encoding="utf-8").read()
    fn = re.search(r"\n      window\.__calReconnect = function \(d\) \{.*?\n      \};\n", html, re.S).group(0)
    casos = """
      const b = { textContent: 'A conexão com o Google Agenda expirou.' }, a = { href: '' };
      const box = { hidden: true, querySelector: (s) => ({ a: a, b: b })[s] };
      const document = { getElementById: () => box }, window = {};
    """ + fn + """
      const out = [];
      for (const d of [{ connected: 'google', needs_reconnect: true, reason: 'permissao' },
                       { connected: 'google', needs_reconnect: true, reason: 'expirada' },
                       { connected: 'google', events: [] }]) {
        window.__calReconnect(d); out.push([box.hidden, box.hidden ? '' : b.textContent, a.href]);
      }
      console.log(JSON.stringify(out));
    """
    out = subprocess.run([_node(), "-e", casos], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        [False, "O Google Agenda está sem permissão para o OpenDoctor.", "/integrations/google/connect"],
        [False, "A conexão com o Google Agenda expirou.", "/integrations/google/connect"],
        [True, "", "/integrations/google/connect"]]


def test_cartao_de_integracoes_diz_sem_permissao_ou_expirada():
    """O cartão do Google em Integrações: "Sem permissão" + Reconectar, ou "Expirada" + Reconectar."""
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-integracao.html"), encoding="utf-8").read()
    fn = re.search(r"\n      function render\(st\) \{.*?\n      \}\n", html, re.S).group(0)
    casos = """
      function el(text) {
        const cls = new Set();
        return { textContent: text || '', hidden: true, dataset: {}, q: {},
          classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c),
                       toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) },
          querySelector(s) { return this.q[s]; }, appendChild(c) { this.textContent += c.textContent; return c; },
          addEventListener() {} };
      }
      const card = el(), status = el(), st = el('Conectado'), btn = el('Conectar'), sub = el('Conecte seu calendário');
      card.q = { '.conn-row': el(), '.conn-status': status, '.int-btn': btn, '.card-sub': sub };
      status.q = { '.st-text': st };
      const document = { querySelector: (s) => (s.indexOf('"google"') >= 0 ? card : null),
                         createElement: () => el(), createTextNode: (t) => ({ textContent: t }) };
      var CFG = {}, LOGGED_IN = true, MSG = {};
      function load() {}
    """ + fn + """
      const out = [];
      for (const g of [{ connected: true, needs_reconnect: true, reason: 'permissao' },
                       { connected: true, needs_reconnect: true, reason: 'expirada' },
                       { connected: true, needs_reconnect: false, reason: null }]) {
        render({ providers: { google: g } });
        out.push([st.textContent, btn.textContent, status.classList.contains('expired'), sub.textContent]);
      }
      console.log(JSON.stringify(out));
    """
    out = subprocess.run([_node(), "-e", casos], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        ["Sem permissão", "Reconectar", True,
         "Falta a permissão da agenda. Reconecte e marque a permissão do Google Agenda, ou desconecte."],
        ["Expirada", "Reconectar", True, "A conexão expirou. Reconecte ou desconecte."],
        ["Conectado", "Desconectar", False, "Conecte seu calendário"]]


def _token_google(monkeypatch, scope):
    gravou = []
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(integrations, "_secret", lambda p: "segredo")
    corpo = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
    if scope is not None:
        corpo["scope"] = scope
    monkeypatch.setattr(integrations.httpx, "post", lambda *a, **k: _Resp(200, corpo))
    monkeypatch.setattr(integrations, "_userinfo_email", lambda p, at: "ana@gmail.com")
    monkeypatch.setattr(db, "set_token", lambda uid, p, **kw: gravou.append((uid, p, kw["scope"])))
    return gravou


def test_conectar_sem_marcar_a_permissao_da_agenda_nao_grava(monkeypatch):
    """No consentimento do Google dá para desmarcar a caixa da agenda: sem ela, nada de "Conectado" com a agenda vazia."""
    gravou = _token_google(monkeypatch, "openid https://www.googleapis.com/auth/userinfo.email")
    with pytest.raises(integrations.MissingScope):
        integrations.exchange_and_store("google", "code", "u1")
    assert gravou == []
    for scope in ("openid email https://www.googleapis.com/auth/calendar.events",
                  "https://www.googleapis.com/auth/calendar openid", None):     # sem "scope" = o que foi pedido
        gravou = _token_google(monkeypatch, scope)
        integrations.exchange_and_store("google", "code", "u1")
        assert gravou == [("u1", "google", scope)]


def test_retorno_sem_a_permissao_da_agenda_explica_em_integracoes(monkeypatch):
    def sem_permissao(prov, code, uid):
        raise integrations.MissingScope("sem a permissão da agenda")
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(integrations, "exchange_and_store", sem_permissao)
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "sv": 0})
    c = TestClient(server.app)
    r = c.get("/integrations/google/connect", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    r = c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)
    assert r.headers["location"] == "/opendoctor-integracao.html?erro=permissao"
    html = open(os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-integracao.html"), encoding="utf-8").read()
    assert "erro === 'permissao' ? 'Marque a permissão do Google Agenda" in html


def test_conexao_da_agenda_so_vale_para_quem_comecou_neste_navegador(monkeypatch):
    gravou = []
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(integrations, "exchange_and_store", lambda prov, code, uid: gravou.append((prov, uid)))
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": request.cookies.get("quem"), "sv": 0}
                        if request.cookies.get("quem") else None)
    medico = TestClient(server.app)
    medico.cookies.set("quem", "u1")
    r = medico.get("/integrations/google/connect", follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    nonce = r.cookies.get(auth.CAL_COOKIE)
    assert nonce and auth.unsign(state)["n"] == nonce and auth.unsign(state)["uid"] == "u1"
    volta = "/auth/google/callback?code=x&state=" + up.quote(state)

    # a vítima, logada na conta dela, abre o link de conexão gerado pelo médico u1: nada é gravado
    vitima = TestClient(server.app)
    vitima.cookies.set("quem", "u2")
    r = vitima.get(volta, follow_redirects=False)
    assert "erro=sessao" in r.headers["location"] and gravou == []
    # mesmo navegador, mas agora logado noutra conta
    outra = TestClient(server.app)
    outra.cookies.set("quem", "u2")
    outra.cookies.set(auth.CAL_COOKIE, nonce, path="/auth/")
    assert "erro=sessao" in outra.get(volta, follow_redirects=False).headers["location"] and gravou == []
    # o mesmo state no retorno de outro provedor (navegador com o cookie certo; a recusa apaga o cookie)
    copia = TestClient(server.app)
    copia.cookies.set("quem", "u1")
    copia.cookies.set(auth.CAL_COOKIE, nonce, path="/auth/")
    assert "erro=sessao" in copia.get(volta.replace("/google/", "/microsoft/"), follow_redirects=False).headers["location"]
    assert gravou == []
    # quem começou, no mesmo navegador: grava na conta dele
    r = medico.get(volta, follow_redirects=False)
    assert r.headers["location"].endswith("?conectado=google") and gravou == [("google", "u1")]


def test_google_fora_do_ar_mostra_tente_de_novo():
    r = server._cal_error(RuntimeError("sem token"))                   # renovação sem resposta (passageira)
    j = json.loads(r.body)
    assert r.status_code == 503 and j["reason"] == "indisponivel" and j["needs_reconnect"] is False and "Tente de novo" in j["error"]


def test_consulta_da_maria_de_exemplo_excluida_nao_cai_numa_maria_real(monkeypatch):
    usou = []
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: None)       # o id do evento não existe mais
    monkeypatch.setattr(db, "ensure_patient", lambda uid, name: usou.append(name) or ({"id": 1, "name": name}, False))
    u = {"id": "u1"}
    with pytest.raises(db.AmbiguousPatient):
        server._note_patient(u, {"patient_id": 99, "patient": "Maria  Silva"})
    assert usou == []                                                   # nem achou nem criou uma Maria Silva real
    assert server._note_patient(u, {"patient_id": 99, "patient": "Ana Souza"})["name"] == "Ana Souza"   # outro excluído: pelo nome
    assert server._note_patient(u, {"patient": "Maria Silva"})["name"] == "Maria Silva"                  # evento antigo, sem id
