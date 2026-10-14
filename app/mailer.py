"""Envio de e-mail transacional (código de confirmação do cadastro / redefinição de senha) pela API do Resend.

Configuração (variáveis de ambiente no Render):
  RESEND_API_KEY   chave da API do Resend
  EMAIL_FROM       remetente com domínio verificado no Resend, ex.: "OpenDoctor <acesso@opendoctor.app>"

Sem RESEND_API_KEY não dá para criar conta nem redefinir senha por e-mail (a tela orienta a usar o Google);
entrar com uma senha já existente continua funcionando.
Só para testes locais: LOGIN_CODE_DEBUG=1 escreve o código no log em vez de enviar.
"""
import os
import html

import httpx

_API = "https://api.resend.com/emails"


def _key():
    return os.environ.get("RESEND_API_KEY", "").strip()


def debug_codes():
    # nunca no Render (RENDER=true lá): o código não pode ir para o log de produção
    return (os.environ.get("LOGIN_CODE_DEBUG", "").strip() == "1" and not _key()
            and not os.environ.get("RENDER"))


def configured():
    return bool(_key()) or debug_codes()


_TEXTS = {
    "signup": ("Confirme seu e-mail no OpenDoctor",
               "Use este código para confirmar seu e-mail e criar sua conta:",
               "Se você não pediu para criar uma conta, ignore este e-mail — nenhuma conta é criada sem o código."),
    "reset": ("Redefinição de senha do OpenDoctor",
              "Use este código para criar uma nova senha:",
              "Se não foi você que pediu, ignore este e-mail — sua senha atual continua valendo."),
}


def _body(code, purpose):
    title, lead, foot = (html.escape(t) for t in _TEXTS[purpose])
    c = html.escape(code)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"></head><body style="margin:0;background:#ffffff">
<div style="max-width:480px;margin:0 auto;padding:40px 24px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#0C0C0D">
  <p style="margin:0 0 24px;font-size:20px;line-height:1.3;font-weight:500">{title}</p>
  <p style="margin:0 0 24px;font-size:14px;line-height:1.5;color:#3C3C40">{lead}</p>
  <p style="margin:0 0 24px;font-size:32px;line-height:1;font-weight:500;letter-spacing:8px">{c}</p>
  <p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#7D7D82">O código vale 10 minutos e só pode ser usado uma vez.</p>
  <p style="margin:0;font-size:13px;line-height:1.5;color:#7D7D82">{foot}</p>
</div></body></html>"""


def send_code(to, code, purpose):
    """Envia o código (purpose: "signup" ou "reset"); levanta RuntimeError se o provedor recusar."""
    title, lead, foot = _TEXTS[purpose]
    if debug_codes():
        print(f"[login-code:{purpose}] {to}: {code}", flush=True)   # só local (LOGIN_CODE_DEBUG=1, sem chave)
        return
    sender = os.environ.get("EMAIL_FROM", "").strip() or "OpenDoctor <acesso@opendoctor.app>"
    r = httpx.post(_API, timeout=15, headers={"Authorization": "Bearer " + _key()}, json={
        "from": sender,
        "to": [to],
        "subject": f"{code} — {title}",
        "html": _body(code, purpose),
        "text": f"{title}\n\n{lead} {code}\n\nO código vale 10 minutos e só pode ser usado uma vez. {foot}",
    })
    if r.status_code >= 300:
        # status + tipo do erro do Resend (ex.: validation_error, invalid_from_address); a mensagem
        # completa fica fora do log porque pode repetir o e-mail do médico
        try:
            kind = str(r.json().get("name") or "")[:60]
        except Exception:
            kind = ""
        raise RuntimeError(f"resend {r.status_code} {kind}".strip())
