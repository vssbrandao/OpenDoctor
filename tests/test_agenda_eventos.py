"""Leitura da agenda (sem banco, sem rede): a semana e a busca seguem as páginas do provedor até o teto, em vez de
mostrar só os primeiros 50/250 eventos; e a página pede o teto. O que a página desenha (dia inteiro, plantão que
passa da meia-noite) é conferido no Chrome por tests/e2e/agenda.mjs."""
import os
import re
import shutil
import subprocess

from fastapi.testclient import TestClient

from app import auth, db, integrations, server

PAGINA = os.path.join(os.path.dirname(__file__), "..", "web", "opendoctor-agenda.html")


class _Resp:
    def __init__(self, body):
        self.status_code, self._body = 200, body

    def json(self):
        return self._body


def _google(monkeypatch, paginas):
    """Google devolvendo a agenda em páginas: token da página → (ids, próximo token)."""
    pedidos = []
    monkeypatch.setattr(integrations, "_access_token", lambda uid, p: "tok")

    def get(url, headers=None, timeout=None, params=None):
        pedidos.append(dict(params))
        ids, prox = paginas[params.get("pageToken")]
        body = {"items": [{"id": f"e{i}", "summary": "Consulta", "start": {"dateTime": "2026-10-30T10:00:00-03:00"},
                           "end": {"dateTime": "2026-10-30T10:30:00-03:00"}} for i in ids]}
        if prox:
            body["nextPageToken"] = prox
        return _Resp(body)
    monkeypatch.setattr(integrations.httpx, "get", get)
    return pedidos


def test_google_segue_as_paginas_ate_o_fim(monkeypatch):
    pedidos = _google(monkeypatch, {None: ([0, 1, 2], "p2"), "p2": ([3, 4, 5], "p3"), "p3": ([6], None)})
    evs = integrations.events("u1", "google", 2500, "2026-10-25T03:00:00Z", "2026-11-01T03:00:00Z")
    assert [e["id"] for e in evs] == [f"e{i}" for i in range(7)]
    assert [p.get("pageToken") for p in pedidos] == [None, "p2", "p3"]
    # cada página repete a mesma janela e o mesmo pedido (o Google exige)
    assert all(p["timeMin"] == "2026-10-25T03:00:00Z" and p["timeMax"] == "2026-11-01T03:00:00Z"
               and p["maxResults"] == 2500 and p["orderBy"] == "startTime" for p in pedidos)


def test_google_para_no_limite_e_no_teto(monkeypatch):
    pedidos = _google(monkeypatch, {None: ([0, 1, 2], "p2"), "p2": ([3, 4, 5], "p3"), "p3": ([6], None)})
    assert [e["id"] for e in integrations.events("u1", "google", 4)] == ["e0", "e1", "e2", "e3"]
    assert len(pedidos) == 2                                       # já tinha o bastante: não pede a 3ª página
    pedidos.clear()
    integrations.events("u1", "google", 10 ** 6)
    assert pedidos[0]["maxResults"] == integrations.EVENTS_MAX == 2500
    pedidos.clear()
    integrations.events("u1", "google", 0)
    assert pedidos[0]["maxResults"] == 1


def test_google_com_paginas_sem_fim_para_sozinho(monkeypatch):
    pedidos = _google(monkeypatch, {None: ([], "x"), "x": ([], "x")})   # páginas vazias com token, para sempre
    assert integrations.events("u1", "google", 2500) == []
    assert len(pedidos) == integrations._PAGES


def test_microsoft_segue_o_proximo_link_so_na_microsoft(monkeypatch):
    monkeypatch.setattr(integrations, "_access_token", lambda uid, p: "tok")
    pedidos = []
    nxt = "https://graph.microsoft.com/v1.0/me/calendarview?$skip=2"
    fora = "https://outro.exemplo.com/roubar"

    def get(url, headers=None, timeout=None, params=None):
        pedidos.append((url, params))
        if url == nxt:
            return _Resp({"value": [{"id": "m2", "subject": "C"}], "@odata.nextLink": fora})
        return _Resp({"value": [{"id": "m0", "subject": "A"}, {"id": "m1", "subject": "B"}], "@odata.nextLink": nxt})
    monkeypatch.setattr(integrations.httpx, "get", get)
    assert [e["id"] for e in integrations.events("u1", "microsoft", 2500)] == ["m0", "m1", "m2"]
    assert [u for u, _ in pedidos] == ["https://graph.microsoft.com/v1.0/me/calendarview", nxt]   # o token nunca vai a outro site
    assert pedidos[1][1] is None                                   # o link já leva os parâmetros


def test_rota_pede_o_bastante_e_respeita_o_teto(monkeypatch):
    pedidos = []
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "u1", "email": "ana@clinica.com.br", "sv": 0})
    monkeypatch.setattr(db, "connected_providers", lambda uid: {"google": "ana@gmail.com"})
    monkeypatch.setattr(integrations, "events", lambda uid, prov, limit, a, b: pedidos.append(limit) or [])
    c = TestClient(server.app)
    for q in ("", "?limit=2500", "?limit=999999", "?limit=0"):
        assert c.get("/calendar/events" + q).status_code == 200
    assert pedidos == [250, 2500, 2500, 1]


def test_semana_e_busca_da_pagina_pedem_o_teto():
    html = open(PAGINA, encoding="utf-8").read()
    pedidos = re.findall(r"fetch\('/calendar/events\?([^']*)'", html)
    leituras = [p for p in pedidos if "start=" in p]
    assert len(leituras) == 3                                      # dia, semana e busca
    assert sum(p == f"limit={integrations.EVENTS_MAX}&start=" for p in leituras) == 2   # semana e busca: sem corte
    # a busca lê as próximas consultas à parte (a partir de hoje), sem o passado tomar o lugar delas
    busca = html[html.index("// ===== buscar consultas"):]
    assert "Promise.all([get(t0, b), get(m, t0), get(a, m)])" in busca


def test_evento_de_dia_inteiro_cai_nos_dias_certos():
    """allDayOn (a faixa de dia inteiro no Dia e na Semana): fim exclusivo, formato do Google e da Microsoft."""
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node não instalado")
    html = open(PAGINA, encoding="utf-8").read()
    fn = re.search(r"\n    function allDayOn\(ev, d\) \{.*?\n    \}\n", html, re.S).group(0)
    casos = """
      const d = (s) => { const q = s.split('-'); return new Date(+q[0], q[1] - 1, +q[2]); };
      const ferias = { allDay: true, start: '2026-11-02', end: '2026-11-07' };
      const um = { allDay: true, start: '2026-10-30', end: '2026-10-31' };
      const ms = { allDay: true, start: '2026-10-30T00:00:00.0000000', end: '2026-10-31T00:00:00.0000000' };
      const semFim = { allDay: true, start: '2026-10-30' };
      const hora = { allDay: false, start: '2026-10-30T10:00:00-03:00', end: '2026-10-30T11:00:00-03:00' };
      console.log(JSON.stringify([
        ['2026-11-01', '2026-11-02', '2026-11-06', '2026-11-07'].map((x) => allDayOn(ferias, d(x))),
        ['2026-10-29', '2026-10-30', '2026-10-31'].map((x) => allDayOn(um, d(x))),
        ['2026-10-30', '2026-10-31'].map((x) => allDayOn(ms, d(x))),
        ['2026-10-30', '2026-10-31'].map((x) => allDayOn(semFim, d(x))),
        allDayOn(hora, d('2026-10-30')),
      ]));
    """
    out = subprocess.run([node, "-e", fn + casos], capture_output=True, text=True, timeout=30,
                         env={"PATH": os.environ.get("PATH", ""), "TZ": "America/Sao_Paulo"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ("[[false,true,true,false],[false,true,false],[true,false],[true,false],false]")
