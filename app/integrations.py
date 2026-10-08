"""Integrações de calendário (OAuth 2.0): Google Calendar e Microsoft Outlook.

Fluxo Authorization Code:
  /auth/<provider>/login     → redireciona ao consentimento do provedor
  /auth/<provider>/callback  → troca o code por tokens e guarda localmente
  status()/disconnect()      → estado e desconexão
  events()                   → lê os próximos eventos do calendário

Tokens ficam em opendoctor-assistant/.integrations.json (gitignored).
Credenciais (client id/secret) vêm do .env — ver .env.example.
"""
import os
import json
import time
import secrets
import datetime
import urllib.parse

import httpx

from . import config

STORE = os.path.join(config.ROOT, ".integrations.json")
REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "http://127.0.0.1:8000").rstrip("/")

PROVIDERS = {
    "google": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email https://www.googleapis.com/auth/calendar.readonly",
        "extra_auth": {"access_type": "offline", "prompt": "consent"},
        "userinfo": "https://www.googleapis.com/oauth2/v2/userinfo",
        "id_env": "GOOGLE_CLIENT_ID", "secret_env": "GOOGLE_CLIENT_SECRET",
    },
    "microsoft": {
        "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access openid email https://graph.microsoft.com/Calendars.Read",
        "extra_auth": {},
        "userinfo": "https://graph.microsoft.com/v1.0/me",
        "id_env": "MS_CLIENT_ID", "secret_env": "MS_CLIENT_SECRET",
    },
}


def _cid(p): return os.environ.get(PROVIDERS[p]["id_env"], "").strip()
def _secret(p): return os.environ.get(PROVIDERS[p]["secret_env"], "").strip()
def configured(p): return bool(_cid(p) and _secret(p))
def redirect_uri(p): return f"{REDIRECT_BASE}/auth/{p}/callback"


def _load():
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    with open(STORE, "w", encoding="utf-8") as fh:
        json.dump(d, fh)


def auth_url(provider):
    p = PROVIDERS[provider]
    state = secrets.token_urlsafe(16)
    store = _load(); store.setdefault("_state", {})[provider] = state; _save(store)
    params = {"client_id": _cid(provider), "redirect_uri": redirect_uri(provider),
              "response_type": "code", "scope": p["scope"], "state": state}
    params.update(p["extra_auth"])
    return p["auth"] + "?" + urllib.parse.urlencode(params)


def _userinfo_email(provider, access_token):
    try:
        r = httpx.get(PROVIDERS[provider]["userinfo"],
                      headers={"Authorization": "Bearer " + access_token}, timeout=20)
        j = r.json()
        return j.get("email") or j.get("mail") or j.get("userPrincipalName")
    except Exception:
        return None


def exchange_code(provider, code, state):
    store = _load()
    if store.get("_state", {}).get(provider) != state:
        raise ValueError("state inválido")
    p = PROVIDERS[provider]
    r = httpx.post(p["token"], timeout=30, data={
        "client_id": _cid(provider), "client_secret": _secret(provider),
        "code": code, "redirect_uri": redirect_uri(provider),
        "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise RuntimeError(f"token {r.status_code}: {r.text[:300]}")
    tok = r.json()
    email = _userinfo_email(provider, tok.get("access_token"))
    store[provider] = {
        "access_token": tok.get("access_token"),
        "refresh_token": tok.get("refresh_token"),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)) - 60,
        "email": email,
    }
    store.get("_state", {}).pop(provider, None)
    _save(store)


def _access_token(provider):
    store = _load(); t = store.get(provider)
    if not t:
        return None
    if t.get("expires_at", 0) > time.time():
        return t["access_token"]
    if not t.get("refresh_token"):
        return None
    p = PROVIDERS[provider]
    r = httpx.post(p["token"], timeout=30, data={
        "client_id": _cid(provider), "client_secret": _secret(provider),
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        return None
    tok = r.json()
    t["access_token"] = tok.get("access_token")
    t["expires_at"] = time.time() + int(tok.get("expires_in", 3600)) - 60
    if tok.get("refresh_token"):
        t["refresh_token"] = tok["refresh_token"]
    store[provider] = t; _save(store)
    return t["access_token"]


def status():
    store = _load(); out = {}
    for prov in PROVIDERS:
        t = store.get(prov)
        out[prov] = {"connected": bool(t), "email": (t or {}).get("email"),
                     "configured": configured(prov)}
    return out


def disconnect(provider):
    store = _load(); store.pop(provider, None); _save(store)


def events(provider, limit=10):
    """Próximos eventos do calendário (prova de que a conexão funciona)."""
    at = _access_token(provider)
    if not at:
        return []
    now = datetime.datetime.now(datetime.timezone.utc)
    hdr = {"Authorization": "Bearer " + at}
    out = []
    try:
        if provider == "google":
            r = httpx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                          headers=hdr, timeout=25, params={
                              "timeMin": now.isoformat(), "singleEvents": "true",
                              "orderBy": "startTime", "maxResults": limit})
            for e in r.json().get("items", []):
                st = e.get("start", {})
                out.append({"title": e.get("summary", "(sem título)"),
                            "start": st.get("dateTime") or st.get("date")})
        else:  # microsoft
            end = now + datetime.timedelta(days=30)
            r = httpx.get("https://graph.microsoft.com/v1.0/me/calendarview",
                          headers=hdr, timeout=25, params={
                              "startDateTime": now.isoformat(), "endDateTime": end.isoformat(),
                              "$orderby": "start/dateTime", "$top": limit})
            for e in r.json().get("value", []):
                out.append({"title": e.get("subject", "(sem título)"),
                            "start": (e.get("start") or {}).get("dateTime")})
    except Exception:
        pass
    return out
