"""Envio de e-mail transacional (código de login) pela API do Resend.

Configuração (variáveis de ambiente no Render):
  RESEND_API_KEY   chave da API do Resend
  EMAIL_FROM       remetente com domínio verificado no Resend, ex.: "OpenDoctor <acesso@opendoctor.app>"

Sem RESEND_API_KEY o login por e-mail fica indisponível (a tela orienta a entrar com o Google).
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


def _body(code):
    c = html.escape(code)
    return f"""<!doctype html><html><body style="margin:0;background:#ffffff">
<div style="max-width:480px;margin:0 auto;padding:40px 24px;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;color:#0C0C0D">
  <p style="margin:0 0 24px;font-size:20px;line-height:1.3;font-weight:500">Seu código de acesso ao OpenDoctor</p>
  <p style="margin:0 0 24px;font-size:14px;line-height:1.5;color:#3C3C40">Digite este código na tela de login para continuar:</p>
  <p style="margin:0 0 24px;font-size:32px;line-height:1;font-weight:500;letter-spacing:8px">{c}</p>
  <p style="margin:0 0 8px;font-size:13px;line-height:1.5;color:#7D7D82">O código vale 10 minutos e só pode ser usado uma vez.</p>
  <p style="margin:0;font-size:13px;line-height:1.5;color:#7D7D82">Se não foi você que pediu, ignore este e-mail — ninguém entra na sua conta sem o código.</p>
</div></body></html>"""


def send_login_code(to, code):
    """Envia o código; levanta RuntimeError se o provedor recusar."""
    if debug_codes():
        print(f"[login-code] {to}: {code}", flush=True)      # só local (LOGIN_CODE_DEBUG=1, sem chave)
        return
    sender = os.environ.get("EMAIL_FROM", "").strip() or "OpenDoctor <acesso@opendoctor.app>"
    r = httpx.post(_API, timeout=15, headers={"Authorization": "Bearer " + _key()}, json={
        "from": sender,
        "to": [to],
        "subject": f"{code} é o seu código de acesso ao OpenDoctor",
        "html": _body(code),
        "text": f"Seu código de acesso ao OpenDoctor: {code}\n\nVale 10 minutos e só pode ser usado uma vez. "
                "Se não foi você que pediu, ignore este e-mail.",
    })
    if r.status_code >= 300:
        raise RuntimeError(f"resend {r.status_code}: {r.text[:200]}")
