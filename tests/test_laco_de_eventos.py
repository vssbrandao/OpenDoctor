"""O servidor tem um processo só (render.yaml): rota async que chama direto o banco, o hash da senha (600 mil voltas),
o e-mail, a IA ou o Google trava o laço de eventos e, enquanto isso dura, nenhum outro médico é atendido (nem a
gravação da consulta). Sem banco, sem rede: cada chamada bloqueante vira uma versão lenta que só termina depois que
outro pedido (/health) foi atendido — o que só acontece se ela rodar fora do laço."""
import ast
import asyncio
import threading
import time

import httpx
import pytest

from app import auth, db, exemplo, integrations, llm, mailer, prescricao, server

USER = {"id": "u1", "email": "ana@clinica.com.br", "name": "Ana", "sv": 0}
PAT = {"id": 7, "name": "Paciente Teste", "key": "paciente teste", "example": False}
PW = "Abcdef12!"


@pytest.fixture
def fake(monkeypatch):
    """Banco, e-mail, Google e IA simulados (rápidos); cada caso deixa um deles lento."""
    server._RL.clear()
    monkeypatch.setattr(auth, "current_user", lambda request: dict(USER))
    monkeypatch.setattr(auth, "check_password", lambda pw, h: True)
    monkeypatch.setattr(auth, "hash_password", lambda pw: "pbkdf2_sha256$1$x$y")
    for nome, v in {
        "get_patient": lambda uid, pid: dict(PAT) if pid == 7 else None, "connected_providers": lambda uid: {"google": "a@b.com"},
        "find_patients": lambda uid, name: [], "notes_by_event": lambda uid, ids: {}, "log_access": lambda *a, **k: None,
        "get_note": lambda uid, nid: {"id": nid, "patient_id": 7}, "add_addendum": lambda uid, nid, c: {"id": 1},
        "list_access": lambda uid, pid: [], "add_file": lambda *a: {"id": 1}, "list_files": lambda uid, pid: [],
        "find_by_cpf": lambda *a, **k: None, "create_patient": lambda *a: dict(PAT), "update_patient": lambda *a: dict(PAT),
        "touch_patient": lambda *a: None, "record_login": lambda *a: False, "login_succeeded": lambda uid: None,
        "password_login_info": lambda e: {"id": "u1", "hash": "h", "sv": 0, "locked_s": 0}, "account": lambda e: None,
        "new_login_code": lambda e, h: ("ok", 0), "discard_login_code": lambda e: None, "check_login_code": lambda e, h: ("ok", 0),
        "user_by_email": lambda e: dict(USER), "create_email_user": lambda *a: dict(USER), "get_user": lambda uid: dict(USER),
        "set_password": lambda uid, ph, sv=None: dict(USER),
    }.items():
        monkeypatch.setattr(db, nome, v)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    for nome in ("send_code", "send_password_changed", "send_new_device"):
        monkeypatch.setattr(mailer, nome, lambda *a, **k: None)
    monkeypatch.setattr(exemplo, "seed_safe", lambda uid: None)
    monkeypatch.setattr(integrations, "create_event", lambda *a, **k: {"id": "e1"})
    monkeypatch.setattr(integrations, "update_event", lambda *a, **k: {"id": "e1"})
    monkeypatch.setattr(integrations, "patient_events", lambda *a: [])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Qual dose?\nE no idoso?\nPor quanto tempo?")
    monkeypatch.setattr(prescricao, "nomes_remedios", lambda: ["Dipirona"])
    return monkeypatch


def _tk(**d):
    return auth.sign(d)


EV = {"title": "Consulta", "start": "2026-10-30T10:00:00-03:00", "end": "2026-10-30T10:30:00-03:00"}
SIGNUP = {"k": "signup", "email": "nova@clinica.com.br", "name": "Nova", "ph": "h"}
CASOS = [   # (método, rota, pedido, (módulo, função lenta), troca no banco simulado)
    ("post", "/auth/password/login", {"json": {"email": "ana@clinica.com.br", "password": PW}}, (auth, "check_password"), {}),
    ("post", "/auth/password/login", {"json": {"email": "ana@clinica.com.br", "password": PW}}, (db, "password_login_info"), {}),
    ("post", "/auth/email/check", {"json": {"email": "ana@clinica.com.br"}}, (db, "account"), {}),
    ("post", "/auth/signup/start", {"json": {"email": "nova@clinica.com.br", "name": "Nova", "password": PW}}, (auth, "hash_password"), {}),
    ("post", "/auth/signup/start", {"json": {"email": "nova@clinica.com.br", "name": "Nova", "password": PW}}, (mailer, "send_code"), {}),
    ("post", "/auth/signup/resend", {"json": {"ticket": SIGNUP}}, (mailer, "send_code"), {}),
    ("post", "/auth/signup/verify", {"json": {"ticket": SIGNUP, "code": "123456"}}, (exemplo, "seed_safe"), {"user_by_email": None}),
    ("post", "/auth/password/forgot", {"json": {"email": "ana@clinica.com.br"}}, (mailer, "send_code"), {}),
    ("post", "/auth/password/reset/verify", {"json": {"email": "ana@clinica.com.br", "code": "123456"}}, (db, "check_login_code"), {}),
    ("post", "/auth/password/reset", {"json": {"ticket": {"k": "reset", "uid": "u1", "sv": 0}, "password": PW}}, (auth, "hash_password"), {}),
    ("post", "/auth/password/reset", {"json": {"ticket": {"k": "reset", "uid": "u1", "sv": 0}, "password": PW}}, (mailer, "send_password_changed"), {}),
    ("post", "/followups", {"json": {"query": "metformina", "answer": "Dose inicial 500 mg."}}, (llm, "chat"), {}),
    ("post", "/calendar/events", {"json": EV}, (integrations, "create_event"), {}),
    ("post", "/calendar/events", {"json": EV}, (db, "connected_providers"), {}),
    ("patch", "/calendar/events/e1", {"json": EV}, (integrations, "update_event"), {}),
    ("post", "/prontuario/visits", {"json": {"patient_id": 7}}, (integrations, "patient_events"), {}),
    ("post", "/prontuario/visits", {"json": {"patient_id": 7}}, (db, "get_patient"), {}),
    ("post", "/prontuario/notes/5/addenda", {"json": {"content": "Adendo."}}, (db, "add_addendum"), {}),
    ("post", "/prontuario/audit", {"json": {"action": "export", "patient_id": 7}}, (db, "log_access"), {}),
    ("post", "/prontuario/access", {"json": {"patient_id": 7}}, (db, "list_access"), {}),
    ("post", "/prontuario/files", {"content": b"%PDF-1.4\n%%EOF", "headers": {"X-Patient-Id": "7", "X-File-Name": "laudo.pdf",
                                                                        "Content-Type": "application/pdf"}}, (db, "add_file"), {}),
    ("post", "/prontuario/files", {"content": b"%PDF-1.4\n%%EOF", "headers": {"X-Patient-Id": "7", "X-File-Name": "laudo.pdf",
                                                                        "Content-Type": "application/pdf"}}, (db, "get_patient"), {}),
    ("post", "/prontuario/files/list", {"json": {"patient_id": 7}}, (db, "list_files"), {}),
    ("get", "/prontuario/remedios", {}, (prescricao, "nomes_remedios"), {}),
    ("post", "/patients", {"json": {"name": "Joana Teste"}}, (db, "create_patient"), {}),
    ("patch", "/patients/7", {"json": {"allergies": "Dipirona"}}, (db, "update_patient"), {}),
]


@pytest.mark.parametrize("metodo,rota,pedido,lenta,troca", CASOS,
                         ids=[f"{c[0]} {c[1]} {c[3][1]}" for c in CASOS])
def test_chamada_lenta_nao_trava_os_outros_medicos(fake, metodo, rota, pedido, lenta, troca):
    for nome, v in troca.items():
        fake.setattr(db, nome, lambda *a, _v=v: _v)
    alvo, nome = lenta
    rapida = getattr(alvo, nome)
    comecou, livre, travou = threading.Event(), threading.Event(), []

    def devagar(*a, **k):
        comecou.set()
        travou.append(not livre.wait(2))       # no laço de eventos, o /health não é atendido enquanto isto espera
        return rapida(*a, **k)
    fake.setattr(alvo, nome, devagar)
    pedido = dict(pedido)
    if isinstance((pedido.get("json") or {}).get("ticket"), dict):
        pedido["json"] = dict(pedido["json"], ticket=_tk(**pedido["json"]["ticket"]))

    async def juntos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            lento = asyncio.ensure_future(c.request(metodo.upper(), rota, **pedido))
            while not comecou.is_set() and not lento.done():
                await asyncio.sleep(0.01)
            outro = await c.get("/health")             # outro médico, no meio da chamada lenta
            livre.set()
            return await lento, outro
    r, outro = asyncio.run(juntos())
    assert r.status_code == 200, r.text
    assert outro.status_code == 200 and travou == [False]


BLOQUEIA = ("db", "integrations", "mailer", "exemplo", "llm")       # banco, Google/Microsoft, Resend, paciente de exemplo, OpenAI
NAO_BLOQUEIA = {"integrations.configured", "mailer.configured", "db.patient_key"}     # só leem o ambiente / o texto


def test_rota_async_so_chama_banco_e_rede_pelo_threadpool():
    """Regra geral, que pega rota nova: numa rota async (e no que ela chama direto), banco, Google, e-mail, IA e o hash
    da senha só passam por run_in_threadpool. Função de dentro (mandada ao threadpool) e gerador (a resposta em partes
    roda no threadpool) não contam."""
    arvore = ast.parse(open(server.__file__, encoding="utf-8").read())
    sync = {n.name: n for n in arvore.body if isinstance(n, ast.FunctionDef)}

    def chamadas(no):
        """Chamadas diretas de `no`: (módulo.função ou função local), fora de run_in_threadpool e de funções de dentro."""
        for f in ast.iter_child_nodes(no):
            if isinstance(f, (ast.FunctionDef, ast.Lambda)):
                continue
            if isinstance(f, ast.Call) and getattr(f.func, "id", "") == "run_in_threadpool":
                for a in f.args[1:] + [k.value for k in f.keywords]:     # os argumentos são calculados no laço
                    yield from chamadas(ast.Expr(value=a))
                continue
            if isinstance(f, ast.Call) and isinstance(f.func, ast.Attribute) and isinstance(f.func.value, ast.Name):
                yield f"{f.func.value.id}.{f.func.attr}"
            elif isinstance(f, ast.Call) and isinstance(f.func, ast.Name):
                yield f.func.id
            yield from chamadas(f)

    def bloqueia(nome, vistos=()):
        if nome in sync:
            fn = sync[nome]
            if nome in vistos or any(isinstance(x, (ast.Yield, ast.YieldFrom)) for x in ast.walk(fn)):
                return None
            return next((b for c in chamadas(fn) for b in [bloqueia(c, vistos + (nome,))] if b), None)
        mod = nome.split(".")[0]
        if nome in NAO_BLOQUEIA:
            return None
        return nome if mod in BLOQUEIA or nome in ("auth.check_password", "auth.hash_password") else None

    achou = [f"{n.name} → {c} ({b})" for n in arvore.body if isinstance(n, ast.AsyncFunctionDef)
             for c in chamadas(n) for b in [bloqueia(c)] if b]
    assert achou == []


def test_trava_de_senhas_erradas_vale_com_pedidos_juntos(fake):
    """Fora do laço os pedidos correm juntos: 9 senhas erradas de uma vez conferem só as 5 da trava, e a senha certa
    que vem depois encontra a conta travada (antes, um pedido por vez garantia isso sozinho)."""
    st, lk = {"falhas": 0, "ate": 0.0, "conferidas": 0}, threading.Lock()

    def info(email):
        with lk:
            return {"id": "u1", "hash": "h", "sv": 0, "locked_s": max(0, int(st["ate"] - time.time() + 0.999))}

    def falhou(uid):
        with lk:
            st["falhas"] += 1
            if st["falhas"] >= db.LOCK_AFTER:
                st["falhas"], st["ate"] = 0, time.time() + db.LOCK_MINUTES * 60
                return 0, db.LOCK_MINUTES * 60
            return db.LOCK_AFTER - st["falhas"], 0

    def confere(pw, h):
        with lk:
            st["conferidas"] += 1
        time.sleep(0.2)                                # o hash de 600 mil voltas
        return pw == PW
    fake.setattr(db, "password_login_info", info)
    fake.setattr(db, "login_failed", falhou)
    fake.setattr(auth, "check_password", confere)
    fake.setattr(server, "_CONTA_ESPERA_S", 10)      # aqui todos esperam a vez (a desistência tem o seu teste)

    async def ataque():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            def tenta(pw):
                return c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": pw})
            erradas = await asyncio.gather(*[tenta(f"Errada{i}!") for i in range(9)])
            return erradas, await tenta(PW)
    erradas, certa = asyncio.run(ataque())
    assert st["conferidas"] == db.LOCK_AFTER
    assert sorted(r.status_code for r in erradas) == [401] * (db.LOCK_AFTER - 1) + [429] * (10 - db.LOCK_AFTER)
    assert certa.status_code == 429 and certa.json()["error"] == "bloqueado"


def test_rajada_numa_conta_desiste_em_vez_de_fazer_fila(fake):
    """Quem espera a vez da conta mais que _CONTA_ESPERA_S volta 429 sem conferir a senha: uma rajada numa conta não
    ocupa o threadpool, e o outro médico é atendido."""
    conferidas = []

    def confere(pw, h):
        conferidas.append(pw)
        time.sleep(0.6)
        return False
    fake.setattr(auth, "check_password", confere)
    fake.setattr(db, "login_failed", lambda uid: (4, 0))
    fake.setattr(server, "_CONTA_ESPERA_S", 0.1)

    async def juntos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            rs = [asyncio.ensure_future(c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": f"Errada{i}!"}))
                  for i in range(4)]
            await asyncio.sleep(0.05)
            outro = await c.get("/health")
            return await asyncio.gather(*rs), outro
    rs, outro = asyncio.run(juntos())
    assert len(conferidas) == 1 and outro.status_code == 200
    assert sorted((r.status_code, r.json()["error"]) for r in rs) == [(401, "senha_incorreta")] + [(429, "limite_ip")] * 3


def test_tiquete_da_nova_senha_vale_uma_vez_com_pedidos_juntos(fake):
    """Dois pedidos com o mesmo tíquete ao mesmo tempo: só um troca a senha. Com o tíquete já usado, nem o hash da
    senha nova é calculado."""
    st, lk = {"sv": 0, "trocas": 0}, threading.Lock()

    def usuario(uid):
        with lk:
            return dict(USER, sv=st["sv"])

    def troca(uid, ph, sv=None):
        time.sleep(0.1)
        with lk:
            st["sv"] += 1
            st["trocas"] += 1
            return dict(USER, sv=st["sv"])
    fake.setattr(db, "get_user", usuario)
    fake.setattr(db, "set_password", troca)
    hashes = []
    fake.setattr(auth, "hash_password", lambda pw: hashes.append(pw) or "h")
    tk = _tk(k="reset", uid="u1", sv=0)

    async def juntos():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            return await asyncio.gather(*[c.post("/auth/password/reset", json={"ticket": tk, "password": PW}) for _ in range(3)])
    rs = asyncio.run(juntos())
    assert st["trocas"] == 1 and sorted(r.status_code for r in rs) == [200, 400, 400]
    assert len(hashes) == 1                            # só quem troca calcula o hash de 600 mil voltas
    from fastapi.testclient import TestClient
    r = TestClient(server.app).post("/auth/password/reset", json={"ticket": tk, "password": PW})
    assert r.status_code == 400 and r.json()["error"] == "sessao_expirada" and len(hashes) == 1



def test_tiquete_ja_usado_por_outro_processo_volta_sessao_expirada(fake):
    """O banco recusou a troca (a versão já mudou noutro processo): a resposta é "sessão expirada", sem entrar."""
    fake.setattr(db, "set_password", lambda uid, ph, sv=None: None)
    from fastapi.testclient import TestClient
    r = TestClient(server.app).post("/auth/password/reset", json={"ticket": _tk(k="reset", uid="u1", sv=0), "password": PW})
    assert r.status_code == 400 and r.json()["error"] == "sessao_expirada" and "set-cookie" not in r.headers
