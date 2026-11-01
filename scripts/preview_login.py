"""Preview LOCAL do login e do cadastro: o servidor de verdade (rotas, páginas, CSP, cookies, banco) contra o banco de
TESTES, com o Google, o CFM e o e-mail simulados. Só contas fictícias, com e-mail @preview-login.invalid, apagadas ao
subir e em /__preview/limpa. Nada vai ao banco de produção, ao Google, ao CFM, ao Resend nem à OpenAI: todo pedido de
rede para fora deste servidor dá erro.

    PREVIEW_PORT=8871 .venv/bin/uvicorn scripts.preview_login:app --port 8871                 (sem a chave do CFM, como hoje)
    PREVIEW_PORT=8872 PREVIEW_CFM=on .venv/bin/uvicorn scripts.preview_login:app --port 8872  (com o CFM simulado)
    abrir http://127.0.0.1:8871/opendoctor-login.html

- **Google:** o botão leva a /__preview/google, que faz as vezes do Google: no login, e-mail, nome, id (sub) e se o e-mail
  é verificado; na agenda, a caixa da permissão. Permitir/Continuar e Cancelar voltam ao /auth/google/callback de verdade.
- **CFM** (PREVIEW_CFM=on), pelo número do CRM: começa com 9, não encontrado; termina em 8, situação irregular; em 7, fora
  do ar (pendente); em 6, CPF/nascimento não batem; em 5, o Validar fora do ar (pendente); em 4, outro nome; os outros:
  regular, "ANA MARIA DE LIMA", dados certos. Cada CRM tem poucas conferências por dia (o limite de verdade): use CRMs
  novos.
- **E-mail:** nada sai. /__preview/mail?to=<e-mail> devolve as mensagens (assunto, texto e o código de 6 dígitos).
- **Contas prontas** (senha PREVIEW_SENHA): admin@ (a de administrador) e antiga@ (conta antiga, de senha);
  google-antiga@ (só Google, sub "g-antiga"). /__preview/conta?email= mostra a conta no banco (CRM, sessões, agenda).
- **Limite por IP:** vale o CF-Connecting-IP, como em produção; um teste que não quer esbarrar no de outro manda o seu.
"""
import os
import pathlib
import re
import urllib.parse

PORT = int(os.environ.get("PREVIEW_PORT", "8871"))
BASE = f"http://127.0.0.1:{PORT}"
CFM_ON = os.environ.get("PREVIEW_CFM", "") == "on"
DOM = "preview-login.invalid"
ADMIN = "admin@" + DOM
PREVIEW_SENHA = "Preview-login-1!"          # senha das contas fictícias deste preview (banco de testes)

# antes de importar o app (o .env não sobrescreve o que já está definido): sem banco de produção, sem chaves de verdade
os.environ.update({"DATABASE_URL": "", "OPENAI_API_KEY": "", "RESEND_API_KEY": "", "CFM_CHAVE": "preview" if CFM_ON else "",
                   "ADMIN_EMAILS": ADMIN, "OAUTH_REDIRECT_BASE": BASE, "GOOGLE_CLIENT_ID": "preview",
                   "GOOGLE_CLIENT_SECRET": "preview", "MS_CLIENT_ID": "", "MS_CLIENT_SECRET": ""})

import base64  # noqa: E402
import datetime  # noqa: E402
import html  # noqa: E402
import json  # noqa: E402

import httpx  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

from app import auth, cfm, config, db, integrations, mailer, server  # noqa: E402


# ----- rede: só este servidor -----
def _so_aqui(f):
    def chama(url, *a, **k):
        if not str(url).startswith(BASE):
            raise RuntimeError("preview: sem rede para fora (" + str(url).split("?")[0][:60] + ")")
        return f(url, *a, **k)
    return chama


httpx.post, httpx.get = _so_aqui(httpx.post), _so_aqui(httpx.get)


# ----- banco: o de TESTES, com a marca, e nunca o projeto de produção -----
def _projeto(url):
    u = urllib.parse.urlsplit(url)
    m = re.match(r"db\.([a-z0-9]+)\.supabase\.co$", u.hostname or "")
    if m:
        return m.group(1)
    m = re.match(r"postgres\.([a-z0-9]+)$", urllib.parse.unquote(u.username or ""))
    return m.group(1) if m else f"{u.hostname}:{u.port}/{u.path}"


def _banco_de_testes():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("preview_login: defina TEST_DATABASE_URL no .env (banco de testes: python -m scripts.setup_test_db)")
    env = pathlib.Path(config.ROOT, ".env")
    prod = next((ln.split("=", 1)[1].strip().strip("'\"") for ln in (env.read_text().splitlines() if env.exists() else [])
                 if ln.strip().startswith("DATABASE_URL=")), "")
    if prod and _projeto(prod) == _projeto(url):
        raise SystemExit("preview_login: TEST_DATABASE_URL é o projeto de produção — recusando")
    import psycopg
    with psycopg.connect(url, connect_timeout=15) as c:
        if not c.execute("select to_regclass('public.ambiente_de_teste') is not null").fetchone()[0]:
            raise SystemExit("preview_login: o banco não tem a marca de banco de testes — recusando")
    return url


config.DATABASE_URL = _banco_de_testes()
db._pool = None


def limpa():
    """Apaga as contas fictícias deste preview (e-mail @preview-login.invalid) e o que é delas."""
    alvo = "(select id from users where email like %s)"
    pat = "%@" + DOM
    with db.connection() as c:
        for t in ("note_addenda", "patient_files", "clinical_notes", "patients"):
            c.execute(f"delete from {t} where user_id in {alvo}", (pat,))
        n = c.execute("delete from users where email like %s", (pat,)).rowcount
        c.execute("delete from login_codes where email like %s", (pat,))
        c.commit()
    return n


def _prepara():
    limpa()
    db.create_email_user(ADMIN, "Admin Preview", auth.hash_password(PREVIEW_SENHA))
    db.create_email_user("antiga@" + DOM, "Antiga Preview", auth.hash_password(PREVIEW_SENHA))
    db.upsert_user("google-antiga@" + DOM, "Google Antiga", None, "g-antiga")


# ----- e-mail: guardado aqui, nada sai -----
CAIXA = []


def _envia(to, subject, body_html, body_text):
    CAIXA.append({"to": str(to).strip().lower(), "subject": subject, "text": body_text,
                  "code": (re.findall(r"\b\d{6}\b", body_text or "") or [None])[0]})


mailer.configured = lambda: True
mailer._send = _envia


# ----- CFM simulado (PREVIEW_CFM=on) -----
def _consultar(crm, uf):
    n = re.sub(r"\D", "", str(crm))
    if n.startswith("9"):
        return {"status": "nao_encontrado"}
    fim = n[-1:]
    if fim == "7":
        return {"status": "indisponivel", "codigo": "rede"}
    return {"status": "ok", "medico": {"crm": n, "uf": uf, "nome": "JOSE CARLOS PEREIRA" if fim == "4" else "ANA MARIA DE LIMA",
                                       "situacao": "C" if fim == "8" else cfm.REGULAR, "tipo": "P", "atualizado": "",
                                       "especialidades": []}}


def _validar(crm, uf, cpf, nascimento):
    fim = re.sub(r"\D", "", str(crm))[-1:]
    if fim == "5":
        return {"status": "indisponivel", "codigo": "rede"}
    return {"status": "ok", "valido": fim != "6"}


cfm.consultar, cfm.validar = _consultar, _validar


# ----- Google simulado -----
integrations.PROVIDERS["google"]["auth"] = BASE + "/__preview/google"


def _perfil(code):
    return json.loads(base64.urlsafe_b64decode(code.encode() + b"==").decode())


def _troca_login(code):
    p = _perfil(code)
    return {"email": p["email"], "name": p.get("name") or "", "picture": None, "sub": p.get("sub") or "",
            "email_verified": p.get("verificado") == "1"}


def _troca_agenda(provider, code, user_id):
    p = _perfil(code)
    if p.get("agenda") != "1":
        raise integrations.MissingScope("sem a permissão da agenda")
    db.set_token(user_id, provider, access_token="preview", refresh_token="preview",
                 expires_at=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1),
                 scope="openid email https://www.googleapis.com/auth/calendar.events", account_email=p.get("email"))


auth.exchange_login = _troca_login
integrations.exchange_and_store = _troca_agenda
integrations.events = lambda user_id, provider, limit=250, time_min=None, time_max=None: []
integrations.patient_events = lambda *a, **k: []


def _campo(nome, valor, tipo="text", extra=""):
    return (f'<label>{nome} <input type="{tipo}" id="{nome}" name="{nome}" value="{html.escape(valor)}" {extra}></label>'
            "<br>")


async def google_page(request):
    q = request.query_params
    st, hint = q.get("state", ""), q.get("login_hint", "")
    agenda = "calendar" in q.get("scope", "")
    oculto = f'<input type="hidden" name="state" value="{html.escape(st)}">'
    if agenda:
        corpo = (f'<h1 id="titulo">Google · permissão da agenda</h1><p id="conta">{html.escape(hint)}</p>'
                 f'<form id="ok" action="/__preview/google/ok">{oculto}'
                 f'<input type="hidden" name="email" value="{html.escape(hint)}">'
                 '<label><input type="checkbox" id="agenda" name="agenda" value="1" checked> Ver e editar a agenda</label><br>'
                 '<button id="permitir">Permitir</button></form>')
    else:
        corpo = (f'<h1 id="titulo">Google · escolha a conta</h1><form id="ok" action="/__preview/google/ok">{oculto}'
                 + _campo("email", hint) + _campo("name", "Nova Google") + _campo("sub", "")
                 + '<label><input type="checkbox" id="verificado" name="verificado" value="1" checked> e-mail verificado'
                 '</label><br><button id="continuar">Continuar</button></form>')
    corpo += (f'<form id="nao" action="/__preview/google/ok">{oculto}<input type="hidden" name="cancelar" value="1">'
              '<button id="cancelar">Cancelar</button></form>')
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>Google (preview)</title>{corpo}")


async def google_ok(request):
    q = dict(request.query_params)
    volta = BASE + "/auth/google/callback?"
    if q.get("cancelar"):
        return RedirectResponse(volta + urllib.parse.urlencode({"error": "access_denied", "state": q.get("state", "")}))
    email = q.get("email", "")
    perfil = {"email": email, "name": q.get("name", ""), "sub": q.get("sub") or ("g-" + email),
              "verificado": q.get("verificado", ""), "agenda": q.get("agenda", "")}
    code = base64.urlsafe_b64encode(json.dumps(perfil).encode()).decode().rstrip("=")
    return RedirectResponse(volta + urllib.parse.urlencode({"code": code, "state": q.get("state", "")}))


async def mail(request):
    to = request.query_params.get("to", "").strip().lower()
    return JSONResponse([m for m in CAIXA if not to or m["to"] == to])


async def conta(request):
    email = request.query_params.get("email", "").strip().lower()
    if not email.endswith("@" + DOM):
        return JSONResponse({"error": "só contas do preview"}, status_code=400)
    with db.connection() as c:
        r = c.execute("""select id, email, name, google_sub, crm, crm_uf, crm_status, crm_fonte, session_version,
                                password_hash is not null as tem_senha from users where email = %s""", (email,)).fetchone()
        if not r:
            return JSONResponse({"existe": False})
        cols = ["id", "email", "name", "google_sub", "crm", "crm_uf", "crm_status", "crm_fonte", "sv", "tem_senha"]
        out = dict(zip(cols, [str(x) if k == "id" else x for k, x in zip(cols, r)]))
        out["agenda"] = [x[0] for x in c.execute("select provider from oauth_tokens where user_id = %s", (r[0],)).fetchall()]
        out["pacientes"] = c.execute("select count(*) from patients where user_id = %s", (r[0],)).fetchone()[0]
    out["existe"] = True
    return JSONResponse(out)


async def limpa_rota(request):
    n = limpa()
    _prepara()
    CAIXA.clear()
    server._RL.clear()
    return JSONResponse({"apagadas": n})


_prepara()
_PREVIEW = Starlette(routes=[Route("/__preview/google", google_page), Route("/__preview/google/ok", google_ok),
                             Route("/__preview/mail", mail), Route("/__preview/conta", conta),
                             Route("/__preview/limpa", limpa_rota)])


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/__preview/"):
        return await _PREVIEW(scope, receive, send)
    return await server.app(scope, receive, send)
