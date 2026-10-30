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
import re
import datetime
import urllib.parse

import httpx
from urllib.parse import quote

from . import db

REDIRECT_BASE = os.environ.get("OAUTH_REDIRECT_BASE", "http://127.0.0.1:8000").rstrip("/")

PROVIDERS = {
    "google": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        # calendar.events = ler E criar/editar eventos (precisa p/ criar pela agenda)
        "scope": "openid email https://www.googleapis.com/auth/calendar.events",
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


# sem uma destas a agenda não lê nem cria eventos (no consentimento o Google deixa desmarcar a caixa da agenda)
CAL_SCOPES = {"google": {"https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar"}}


class MissingScope(RuntimeError):
    """O médico conectou sem marcar a permissão da agenda: a conexão não é gravada (senão apareceria
    "Conectado" com a agenda vazia). Vira ?erro=permissao em Integrações."""


def exchange_and_store(provider, code, user_id):
    """Troca o code por tokens de calendário e grava no DB para o usuário. Levanta MissingScope se o
    provedor não concedeu a permissão da agenda."""
    p = PROVIDERS[provider]
    r = httpx.post(p["token"], timeout=30, data={
        "client_id": _cid(provider), "client_secret": _secret(provider),
        "code": code, "redirect_uri": redirect_uri(provider),
        "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise RuntimeError(f"token {r.status_code}: {r.text[:300]}")
    tok = r.json()
    # sem "scope" na resposta = concedido o que foi pedido (RFC 6749 5.1)
    if provider in CAL_SCOPES and tok.get("scope") is not None \
            and not CAL_SCOPES[provider] & set(str(tok["scope"]).split()):
        raise MissingScope("sem a permissão da agenda")
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


class NeedsReconnect(RuntimeError):
    """A conexão com o calendário morreu (o provedor recusou a renovação: acesso revogado, senha trocada,
    token vencido): só o médico reconectando resolve. Vira `needs_reconnect` nas rotas e o aviso na tela."""


def _access_token(user_id, provider):
    """Token válido do usuário (renova com refresh_token se expirou). None = calendário não conectado.
    Levanta NeedsReconnect se a conexão morreu; a linha fica marcada (sem refresh_token) para não pedir a
    renovação ao provedor de novo a cada atualização da agenda."""
    t = db.get_token(user_id, provider)
    if not t:
        return None
    exp = t.get("expires_at")
    if exp and exp > _utcnow():
        return t["access_token"]
    if not t.get("refresh_token"):
        raise NeedsReconnect("sem token")
    p = PROVIDERS[provider]
    try:
        r = httpx.post(p["token"], timeout=30, data={
            "client_id": _cid(provider), "client_secret": _secret(provider),
            "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    except httpx.HTTPError as e:                          # rede caiu ou o Google demorou: tenta na próxima
        print(f"[oauth] renovação sem resposta: {provider} {type(e).__name__}", flush=True)
        return None
    if r.status_code != 200:
        try:
            err = str(r.json().get("error") or "")
        except Exception:  # noqa: BLE001
            err = ""
        print(f"[oauth] renovação recusada: {provider} {r.status_code} {err[:40]}", flush=True)   # nunca o token
        if r.status_code in (400, 401) and err == "invalid_grant":
            db.mark_token_dead(user_id, provider, t["refresh_token"])
            raise NeedsReconnect("conexão expirada")
        return None                                       # falha passageira do provedor: tenta na próxima
    try:
        tok = r.json()
        access = tok["access_token"]
        expires_at = _utcnow() + datetime.timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    except (ValueError, KeyError, TypeError):             # resposta 200 ilegível: tenta na próxima
        print(f"[oauth] renovação com resposta inválida: {provider}", flush=True)
        return None
    db.update_access_token(user_id, provider, access, expires_at, tok.get("refresh_token"))
    return access


def _event_body(provider, title, start, end, description=None, location=None, all_day=False, patient_id=None):
    """Corpo do evento no formato de cada provedor (usado em criar e editar).
    No Google, o paciente cadastrado vai em extendedProperties.private (invisível no app do Google)."""
    if provider == "google":
        key = "date" if all_day else "dateTime"
        other = "dateTime" if all_day else "date"
        # ao trocar entre dia inteiro e horário, zera o outro campo (o Google exige um só)
        body = {"summary": title or "(sem título)",
                "start": {key: start, other: None}, "end": {key: end, other: None},
                "description": description or "", "location": location or "",
                "extendedProperties": {"private": {"od_patient_id": str(patient_id) if patient_id else None}}}
        return body
    if all_day:
        start, end = start + "T00:00:00", end + "T00:00:00"
    return {"subject": title or "(sem título)",
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "isAllDay": bool(all_day),
            "body": {"contentType": "text", "content": description or ""},
            "location": {"displayName": location or ""}}


def _event_out(provider, e):
    if provider == "google":
        st, en = e.get("start") or {}, e.get("end") or {}
        return {"id": e.get("id"), "title": e.get("summary"), "patient_id": _patient_id(e),
                "start": st.get("dateTime") or st.get("date"), "end": en.get("dateTime") or en.get("date")}
    return {"id": e.get("id"), "title": e.get("subject"),
            "start": (e.get("start") or {}).get("dateTime"), "end": (e.get("end") or {}).get("dateTime")}


def _patient_id(e):
    """Id do paciente cadastrado guardado no evento do Google (ou None)."""
    v = ((e.get("extendedProperties") or {}).get("private") or {}).get("od_patient_id")
    return int(v) if v and str(v).isdigit() else None


class CalendarError(RuntimeError):
    """O provedor recusou criar/editar/excluir. `kind` diz o porquê, pelo motivo que o Google manda
    (error.errors[0].reason): "permissao" (token sem a permissão da agenda: reconectar resolve), "limite"
    (pedidos demais: tentar de novo), "proibido" (outro 403, ex.: evento de outra pessoa) ou "" (outro erro)."""
    SEM_PERMISSAO = {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}
    LIMITE = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "dailyLimitExceeded",
              "calendarUsageLimitsExceeded", "RATE_LIMIT_EXCEEDED"}

    def __init__(self, r):
        super().__init__(f"{r.status_code}: {r.text[:200]}")
        self.status, self.reason = r.status_code, _reason(r)
        self.kind = ("permissao" if self.reason in self.SEM_PERMISSAO
                     else "limite" if self.status == 429 or self.reason in self.LIMITE
                     else "proibido" if self.status == 403 else "")


def _reason(r):
    """Motivo do erro: Google error.errors[].reason (ou o ErrorInfo de error.details); Microsoft error.code."""
    try:
        err = r.json().get("error") or {}
        cands = [x.get("reason") for x in (err.get("errors") or []) + (err.get("details") or []) if isinstance(x, dict)]
        return next((c for c in cands + [err.get("code")] if isinstance(c, str) and c), "")[:60]
    except Exception:  # noqa: BLE001
        return ""


def _headers(user_id, provider):
    at = _access_token(user_id, provider)
    if not at:
        raise RuntimeError("sem token")
    return {"Authorization": "Bearer " + at, "Content-Type": "application/json"}


def _event_url(provider, event_id=None):
    base = ("https://www.googleapis.com/calendar/v3/calendars/primary/events" if provider == "google"
            else "https://graph.microsoft.com/v1.0/me/events")
    return base + ("/" + quote(event_id, safe="") if event_id else "")


def create_event(user_id, provider, title, start, end, description=None, location=None, all_day=False,
                 patient_id=None):
    """Cria um evento no calendário primário do usuário. start/end em ISO 8601
    (com offset, ex.: 2026-10-09T13:30:00-03:00) ou, se all_day, datas AAAA-MM-DD
    (fim exclusivo). Provedor recusou → CalendarError (ex.: kind "permissao" se o token for
    somente-leitura → precisa reconectar com escopo de escrita)."""
    body = _event_body(provider, title, start, end, description, location, all_day, patient_id)
    if provider == "google":                              # na criação não manda campos vazios
        body["start"] = {k: v for k, v in body["start"].items() if v}
        body["end"] = {k: v for k, v in body["end"].items() if v}
        for k in ("description", "location"):
            if not body[k]:
                body.pop(k)
        if not patient_id:
            body.pop("extendedProperties")
    r = httpx.post(_event_url(provider), headers=_headers(user_id, provider), json=body, timeout=25)
    if r.status_code not in (200, 201):
        raise CalendarError(r)
    return _event_out(provider, r.json())


def update_event(user_id, provider, event_id, title, start, end, description=None, location=None, all_day=False,
                 patient_id=None):
    """Atualiza um evento existente (PATCH). Mesmos formatos de create_event.
    patient_id=None remove o vínculo com o paciente."""
    body = _event_body(provider, title, start, end, description, location, all_day, patient_id)
    r = httpx.patch(_event_url(provider, event_id), headers=_headers(user_id, provider), json=body, timeout=25)
    if r.status_code not in (200, 201):
        raise CalendarError(r)
    return _event_out(provider, r.json())


def delete_event(user_id, provider, event_id):
    """Exclui um evento do calendário. 404/410 = já não existe (tratado como sucesso)."""
    r = httpx.delete(_event_url(provider, event_id), headers=_headers(user_id, provider), timeout=25)
    if r.status_code not in (200, 204, 404, 410):
        raise CalendarError(r)
    return True


def _event_patient_name(e):
    """Nome do paciente num evento antigo: "Título — Nome" no título ou "Paciente: Nome" na descrição."""
    m = re.search(r"^Paciente: (.+)$", e.get("description") or "", re.M)
    if m:
        return m.group(1).strip()
    parts = (e.get("summary") or "").split(" — ")
    return parts[-1].strip() if len(parts) > 1 else (e.get("summary") or "").strip()


def patient_events(user_id, provider, patient_id, name=None, time_min=None, time_max=None):
    """Consultas de um paciente no calendário: as ligadas ao cadastro (od_patient_id) e, para eventos
    antigos sem vínculo, as com exatamente o nome dele (name=None quando há homônimos, para não
    misturar consultas de pessoas diferentes). Ordenadas por início."""
    if provider != "google":
        return []
    at = _access_token(user_id, provider)
    if not at:
        return []
    hdr = {"Authorization": "Bearer " + at}
    base = {"singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
            "timeMin": time_min or (_utcnow() - datetime.timedelta(days=3 * 365)).isoformat(),
            "timeMax": time_max or (_utcnow() + datetime.timedelta(days=365)).isoformat()}
    out = {}
    queries = [dict(base, privateExtendedProperty=f"od_patient_id={patient_id}")]
    if name:
        queries.append(dict(base, q=name))
    for params in queries:
        try:
            r = httpx.get(_event_url("google"), headers=hdr, timeout=25, params=params)
            items = r.json().get("items", []) if r.status_code == 200 else []
        except Exception:
            items = []
        for e in items:
            pid = _patient_id(e)
            if pid and pid != patient_id:                 # mesmo nome, outro paciente (homônimo)
                continue
            if not pid and (not name or db.patient_key(_event_patient_name(e)) != db.patient_key(name)):
                continue                                  # nome tem de ser o mesmo (não "Ana" em "Ana Paula")
            st, en = e.get("start") or {}, e.get("end") or {}
            out[e.get("id")] = {"id": e.get("id"), "title": e.get("summary") or "(sem título)",
                                "start": st.get("dateTime") or st.get("date"),
                                "end": en.get("dateTime") or en.get("date"),
                                "allDay": "date" in st and "dateTime" not in st,
                                "location": e.get("location") or "", "linked": bool(pid)}
    return sorted(out.values(), key=lambda v: v["start"] or "")


def status(user_id):
    """Estado das integrações do usuário (ou tudo desconectado se None)."""
    connected = db.connected_providers(user_id) if user_id else {}
    dead = db.dead_providers(user_id) if connected else set()
    out = {}
    for prov in PROVIDERS:
        out[prov] = {"connected": prov in connected,
                     "needs_reconnect": prov in dead,          # conectado, mas a conexão morreu
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
                out.append({"id": e.get("id"), "title": e.get("summary", "(sem título)"),
                            "patient_id": _patient_id(e),
                            "description": e.get("description") or "", "location": e.get("location") or "",
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
                out.append({"id": e.get("id"), "title": e.get("subject", "(sem título)"),
                            "description": e.get("bodyPreview") or "",
                            "location": (e.get("location") or {}).get("displayName") or "",
                            "start": (e.get("start") or {}).get("dateTime"),
                            "end": (e.get("end") or {}).get("dateTime"),
                            "allDay": bool(e.get("isAllDay"))})
    except Exception:
        pass
    return out
