"""Autenticação do app: login com Google (escopos básicos) + sessão por cookie.

O login usa só `openid email profile` (NÃO-sensível) — funciona para qualquer
usuário sem a verificação do Google. A conexão de calendário (escopo sensível)
é um passo separado, em integrations.py.

A sessão é um cookie assinado por HMAC (SESSION_SECRET); não há estado no servidor.
O mesmo assinador gera/valida o `state` do OAuth.
"""
import os
import json
import time
import hmac
import base64
import hashlib
import secrets
import datetime
import urllib.parse

import httpx

from . import integrations

COOKIE_NAME = "od_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30          # 30 dias
STATE_MAX_AGE = 60 * 15                        # 15 min para concluir o OAuth

_SECRET = (os.environ.get("SESSION_SECRET", "").strip()
           or "dev-inseguro-troque-em-producao").encode()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    """Assina um dict (inclui timestamp) e devolve 'corpo.assinatura'."""
    payload = dict(payload, t=int(time.time()))
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
    return body + "." + sig


def unsign(token: str, max_age: int = None):
    """Valida a assinatura (e opcionalmente a idade); devolve o dict ou None."""
    try:
        body, sig = token.split(".", 1)
        expect = _b64e(hmac.new(_SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64d(body))
        if max_age is not None and time.time() - payload.get("t", 0) > max_age:
            return None
        return payload
    except Exception:
        return None


# ----- sessão (cookie) -----

def set_session(response, user_id: str):
    secure = integrations.REDIRECT_BASE.startswith("https://")
    response.set_cookie(
        COOKIE_NAME, sign({"uid": user_id}),
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
        secure=secure, path="/")


def clear_session(response):
    response.delete_cookie(COOKIE_NAME, path="/")


def current_user(request):
    """Devolve o dict do usuário logado (do cookie) ou None."""
    from . import db
    tok = request.cookies.get(COOKIE_NAME)
    if not tok:
        return None
    payload = unsign(tok, SESSION_MAX_AGE)
    if not payload or "uid" not in payload:
        return None
    try:
        return db.get_user(payload["uid"])
    except Exception:
        return None


# ----- login com Google (escopos básicos) -----

LOGIN_SCOPE = "openid email profile"


HOME = "/opendoctor-agenda.html"


def safe_next(nxt) -> str:
    """Destino depois do login: só caminhos deste site ("/pagina.html?x#y"); qualquer outra
    coisa (URL externa, "//host", barra invertida) vira a agenda — evita redirecionamento aberto."""
    if not isinstance(nxt, str) or not nxt.startswith("/") or nxt.startswith("//") or len(nxt) > 300:
        return HOME
    if "\\" in nxt or any(c in nxt for c in "\r\n\t ") or nxt.startswith("/auth/"):
        return HOME
    parts = urllib.parse.urlsplit(nxt)
    if parts.scheme or parts.netloc:
        return HOME
    return nxt


def with_welcome(url: str) -> str:
    """Marca o primeiro acesso para a agenda mostrar as boas-vindas."""
    if not url.split("?")[0].split("#")[0] == HOME:
        return url
    base, _, frag = url.partition("#")
    base += ("&" if "?" in base else "?") + "bemvindo=1"
    return base + ("#" + frag if frag else "")


# ----- login por e-mail: código de 6 dígitos -----

def new_code() -> str:
    return f"{secrets.randbelow(10 ** 6):06d}"


def code_hash(email: str, code: str) -> str:
    """O código não é guardado: só este HMAC (vale para um e-mail só)."""
    return hmac.new(_SECRET, f"login-code:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def login_url(hint: str = "", nxt: str = "") -> str:
    """URL do login Google. `hint` (e-mail digitado na tela de login) já abre a conta certa;
    `nxt` é a página para onde voltar depois."""
    p = integrations.PROVIDERS["google"]
    state = sign({"k": "login", "n": secrets.token_urlsafe(8), "nx": safe_next(nxt)})
    params = {
        "client_id": integrations._cid("google"),
        "redirect_uri": integrations.redirect_uri("google"),
        "response_type": "code",
        "scope": LOGIN_SCOPE,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    if hint:
        params["login_hint"] = hint
        del params["prompt"]          # com a conta indicada, não precisa da lista de contas
    return p["auth"] + "?" + urllib.parse.urlencode(params)


def exchange_login(code: str) -> dict:
    """Troca o code pelo perfil do usuário (email/nome/foto/sub). Não guarda token
    de calendário — o login básico não tem escopo de calendário."""
    p = integrations.PROVIDERS["google"]
    r = httpx.post(p["token"], timeout=30, data={
        "client_id": integrations._cid("google"),
        "client_secret": integrations._secret("google"),
        "code": code,
        "redirect_uri": integrations.redirect_uri("google"),
        "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise RuntimeError(f"token {r.status_code}: {r.text[:200]}")
    access = r.json().get("access_token")
    info = httpx.get(p["userinfo"], headers={"Authorization": "Bearer " + access},
                     timeout=20).json()
    email = info.get("email")
    if not email:
        raise RuntimeError("Google não retornou email")
    return {"email": email, "name": info.get("name"),
            "picture": info.get("picture"), "sub": info.get("id")}
