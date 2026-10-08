"""Integrações de calendário (OAuth 2.0): Google Calendar e Microsoft Outlook.

Fase B (multiusuário): os tokens ficam no Postgres (tabela oauth_tokens), um por
(usuário, provedor) — não mais num arquivo único. O login do app é feito em
auth.py; aqui tratamos só a CONEXÃO do calendário (escopo sensível) e a leitura
de eventos, sempre no contexto de um user_id.

Fluxo:
  /integrations/<provider>/connect   → consentimento do provedor (escopo calendário)
  /auth/<provider>/callback          → troca o code por tokens e guarda no DB
  status(user_id) / disconnect(...)  → estado e desconexão por usuário
  events(user_id, provider)          → próximos eventos do calendário
"""
import os
import datetime
import urllib.parse

import httpx

from . import db

REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "http://127.0.0.1:8000").rstrip("/")

PROVIDERS = {
    "google": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email https://www.googleapis.com/auth/calendar.readonly",
        "extra_auth": {"access_type": "offline", "prompt": "consent",
                       "include_granted_scopes": "true"},
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


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def connect_url(provider, state):
    """URL de consentimento p/ CONECTAR o calendário. `state` é assinado pelo caller
    (auth.sign) e carrega o user_id."""
    p = PROVIDERS[provider]
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


def exchange_and_store(provider, code, user_id):
    """Troca o code por tokens de calendário e grava no DB para o usuário."""
    p = PROVIDERS[provider]
    r = httpx.post(p["token"], timeout=30, data={
        "client_id": _cid(provider), "client_secret": _secret(provider),
        "code": code, "redirect_uri": redirect_uri(provider),
        "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise RuntimeError(f"token {r.status_code}: {r.text[:300]}")
    tok = r.json()
    access = tok.get("access_token")
    expires_at = _utcnow() + datetime.timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    db.set_token(
        user_id, provider,
        access_token=access,
        refresh_token=tok.get("refresh_token"),
        expires_at=expires_at,
        scope=tok.get("scope"),
        account_email=_userinfo_email(provider, access),
    )


def _access_token(user_id, provider):
    """Token válido do usuário (renova com refresh_token se expirou)."""
    t = db.get_token(user_id, provider)
    if not t:
        return None
    exp = t.get("expires_at")
    if exp and exp > _utcnow():
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
    access = tok.get("access_token")
    expires_at = _utcnow() + datetime.timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    db.update_access_token(user_id, provider, access, expires_at, tok.get("refresh_token"))
    return access


def status(user_id):
    """Estado das integrações do usuário (ou tudo desconectado se None)."""
    connected = db.connected_providers(user_id) if user_id else {}
    out = {}
    for prov in PROVIDERS:
        out[prov] = {"connected": prov in connected,
                     "email": connected.get(prov),
                     "configured": configured(prov)}
    return out


def disconnect(user_id, provider):
    db.delete_token(user_id, provider)


def events(user_id, provider, limit=50, time_min=None, time_max=None):
    """Eventos do calendário do usuário. Se time_min/time_max (ISO 8601) forem
    passados, filtra por essa janela (ex.: o dia exibido na agenda); senão, lista
    os próximos. Cada item: {title, start, end, allDay}."""
    at = _access_token(user_id, provider)
    if not at:
        return []
    now_iso = _utcnow().isoformat()
    hdr = {"Authorization": "Bearer " + at}
    out = []
    try:
        if provider == "google":
            params = {"singleEvents": "true", "orderBy": "startTime",
                      "maxResults": limit, "timeMin": time_min or now_iso}
            if time_max:
                params["timeMax"] = time_max
            r = httpx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events",
                          headers=hdr, timeout=25, params=params)
            for e in r.json().get("items", []):
                st = e.get("start", {}); en = e.get("end", {})
                all_day = "date" in st and "dateTime" not in st
                out.append({"title": e.get("summary", "(sem título)"),
                            "start": st.get("dateTime") or st.get("date"),
                            "end": en.get("dateTime") or en.get("date"),
                            "allDay": all_day})
        else:  # microsoft
            start = time_min or now_iso
            end = time_max or (_utcnow() + datetime.timedelta(days=30)).isoformat()
            r = httpx.get("https://graph.microsoft.com/v1.0/me/calendarview",
                          headers=hdr, timeout=25, params={
                              "startDateTime": start, "endDateTime": end,
                              "$orderby": "start/dateTime", "$top": limit})
            for e in r.json().get("value", []):
                out.append({"title": e.get("subject", "(sem título)"),
                            "start": (e.get("start") or {}).get("dateTime"),
                            "end": (e.get("end") or {}).get("dateTime"),
                            "allDay": bool(e.get("isAllDay"))})
    except Exception:
        pass
    return out
