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


def login_url() -> str:
    p = integrations.PROVIDERS["google"]
    state = sign({"k": "login", "n": secrets.token_urlsafe(8)})
    params = {
        "client_id": integrations._cid("google"),
        "redirect_uri": integrations.redirect_uri("google"),
        "response_type": "code",
        "scope": LOGIN_SCOPE,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
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
