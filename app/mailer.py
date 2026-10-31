"""E-mails transacionais do login, pela API do Resend, todos no mesmo template (Figma 1047-44835):
logo · "Nome," + título 40px · texto · bloco (código em 6 caixas ou botão) · notas em cinza · rodapé cinza com logo.

  signup   código para confirmar o e-mail do cadastro
  reset    código para criar uma nova senha (esqueci a senha / conta Google criando senha)
  changed  aviso de que a senha foi alterada (sem código)
  device   aviso de entrada por um aparelho novo (sem código)
  crm_pendente  aos administradores (ADMIN_EMAILS): cadastro novo esperando a conferência do CRM (só nome e CRM/UF)
  crm_aprovado  ao médico: CRM conferido à mão, conta liberada
  crm_recusado  ao médico: não deu para confirmar o CRM, conta não liberada
  cfm_chave     aos administradores: o CFM recusou a chave (3010, inválida ou vencida)

Configuração (variáveis de ambiente no Render):
  RESEND_API_KEY   chave da API do Resend
  EMAIL_FROM       remetente com domínio verificado no Resend, ex.: "OpenDoctor <acesso@opendoctor.app>"
  APP_URL          endereço público do app (padrão https://opendoctor.app) — logo e links do e-mail

Sem RESEND_API_KEY não dá para criar conta nem redefinir senha por e-mail (a tela orienta a usar o Google);
entrar com uma senha já existente continua funcionando.
Só para testes locais: LOGIN_CODE_DEBUG=1 escreve o código no log em vez de enviar.
"""
import os
import html
import datetime

import httpx

_API = "https://api.resend.com/emails"
_FONT = "'Helvetica Neue',Helvetica,Arial,sans-serif"


def _env(name):
    """Valor da variável sem espaços nem aspas em volta (comum ao colar no painel do Render)."""
    return os.environ.get(name, "").strip().strip("\"'").strip()


def _key():
    return _env("RESEND_API_KEY")


def _app_url():
    return (_env("APP_URL") or "https://opendoctor.app").rstrip("/")


def debug_codes():
    # nunca no Render (RENDER=true lá): o código não pode ir para o log de produção
    return _env("LOGIN_CODE_DEBUG") == "1" and not _key() and not os.environ.get("RENDER")


def configured():
    return bool(_key()) or debug_codes()


def first_name(name):
    """Primeiro nome para a saudação, pulando tratamentos ("Dra. Ana Lima" → "Ana")."""
    parts = [p for p in str(name or "").split() if p]
    while len(parts) > 1 and parts[0].endswith("."):
        parts = parts[1:]
    return parts[0] if parts else ""


# ----- textos de cada e-mail -----

_CODE_NOTE = ("O código vale 10 minutos e só pode ser usado uma vez. Por segurança, não compartilhe este código "
              "com ninguém — a equipe do OpenDoctor nunca vai pedi-lo.")

_TEXTS = {
    "signup": {
        "subject": "{code} — Confirme seu e-mail no OpenDoctor",
        "title": "Confirme seu e-mail",
        "lead": "Para terminar de criar sua conta no OpenDoctor, digite o código abaixo na tela de cadastro.",
        "notes": ["Se você não pediu para criar uma conta, ignore este e-mail — nenhuma conta é criada sem o código.",
                  _CODE_NOTE],
    },
    "reset": {
        "subject": "{code} — Código para criar uma nova senha no OpenDoctor",
        "title": "Seu código para uma nova senha",
        "lead": "Para criar uma nova senha no OpenDoctor, digite o código abaixo na tela de login.",
        "notes": ["Se você não pediu para trocar a senha, ignore este e-mail — sua senha atual continua valendo.",
                  _CODE_NOTE],
    },
    "changed": {
        "subject": "Sua senha do OpenDoctor foi alterada",
        "title": "Sua senha foi alterada",
        "lead": "A senha da sua conta no OpenDoctor foi alterada em {when}. Por segurança, as sessões abertas "
                "em outros aparelhos foram encerradas.",
        "button": "Entrar no OpenDoctor",
        "notes": ["Se não foi você, crie uma nova senha agora em “Esqueci minha senha”, na tela de login, e "
                  "confira a segurança do seu e-mail."],
    },
    "device": {
        "subject": "Novo acesso à sua conta do OpenDoctor",
        "title": "Novo acesso à sua conta",
        "lead": "Sua conta no OpenDoctor foi acessada em {when} por um aparelho novo: {device}, com {via}.",
        "button": "Entrar no OpenDoctor",
        "notes": ["Se foi você, não precisa fazer nada.",
                  "Se não foi você, crie uma nova senha agora em “Esqueci minha senha”, na tela de login — isso "
                  "encerra as sessões abertas em outros aparelhos — e confira a segurança do seu e-mail "
                  "e da sua conta Google."],
    },
    "crm_pendente": {
        "subject": "Cadastro para conferir: CRM {crm}",
        "title": "Um cadastro espera a conferência do CRM",
        "lead": "{nome}, CRM {crm}, criou uma conta no OpenDoctor. Confira o registro no CFM e aprove ou recuse "
                "o cadastro.",
        "button": "Conferir cadastros",
        "link": "/opendoctor-cadastros.html",
        "notes": ["A conta entra, mas só usa o app depois da aprovação."],
    },
    "crm_aprovado": {
        "subject": "Sua conta no OpenDoctor foi liberada",
        "title": "Seu CRM foi conferido",
        "lead": "Conferimos seu registro no CFM e sua conta no OpenDoctor está liberada. Já pode entrar e usar a "
                "agenda e o prontuário.",
        "button": "Entrar no OpenDoctor",
        "notes": ["Se você não criou uma conta no OpenDoctor, ignore este e-mail."],
    },
    "crm_recusado": {
        "subject": "Não conseguimos confirmar seu CRM",
        "title": "Não conseguimos confirmar seu CRM",
        "lead": "Não conseguimos confirmar seu registro no CFM com os dados do cadastro, e por isso sua conta no "
                "OpenDoctor não foi liberada. O OpenDoctor é só para médicos com inscrição regular no CRM.",
        "button": "Abrir o OpenDoctor",
        "notes": ["Se você acha que houve um engano, entre em contato com a equipe do OpenDoctor.",
                  "Se você não criou uma conta no OpenDoctor, ignore este e-mail."],
    },
    "cfm_chave": {
        "subject": "O CFM recusou a chave do OpenDoctor",
        "title": "O CFM recusou a chave",
        "lead": "O web service do CFM respondeu que a chave do OpenDoctor é inválida ou venceu (código 3010). Enquanto "
                "isso, os cadastros novos ficam pendentes para aprovação à mão e as contas aprovadas à mão entram sem "
                "confirmar o CPF.",
        "button": "Conferir cadastros",
        "link": "/opendoctor-cadastros.html",
        "notes": ["Confira a variável CFM_CHAVE no Render e a validade do contrato com o CFM (docs/cadastro-crm.md).",
                  "Enquanto a chave continuar recusada, este aviso se repete no máximo a cada 12 horas."],
    },
}


# ----- template (tabelas + estilos inline: é o que os programas de e-mail entendem) -----

def _code_boxes(code):
    cells = []
    for i, d in enumerate(code):
        if i:
            cells.append('<td class="gap" width="8" style="width:8px;font-size:0;line-height:0">&nbsp;</td>')
        cells.append(
            f'<td class="box" width="84" height="84" align="center" valign="middle" '
            f'style="width:84px;height:84px;background:#F4F4F6;border-radius:24px;font-family:{_FONT};'
            f'font-weight:500;font-size:28px;line-height:84px;color:#000000;text-align:center">{html.escape(d)}</td>')
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'aria-label="Código {html.escape(" ".join(code))}"><tr>{"".join(cells)}</tr></table>')


def _button(label, href):
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td height="84" align="center" valign="middle" style="height:84px;background:#000033;border-radius:999px">'
            f'<a href="{html.escape(href)}" style="display:inline-block;padding:0 48px;line-height:84px;font-family:{_FONT};'
            f'font-weight:500;font-size:14px;color:#FFFFFF;text-decoration:none;white-space:nowrap">{html.escape(label)}</a>'
            '</td></tr></table>')


def _spacer(h):
    return f'<tr><td height="{h}" style="height:{h}px;font-size:0;line-height:0">&nbsp;</td></tr>'


def render(purpose, name="", code="", when="", device="", via="", nome="", crm=""):
    """(assunto, html, texto) do e-mail. `nome` e `crm`: o médico do cadastro (aviso aos administradores)."""
    t = _TEXTS[purpose]
    base = _app_url()
    logo = (f'<img src="{base}/assets/email/logo.png" width="24" height="24" alt="OpenDoctor" '
            'style="display:block;width:24px;height:24px;border:0">')
    first = first_name(name)
    greet = f"{first}," if first else "Olá,"
    lead = t["lead"].format(when=when, device=device, via=via, nome=nome, crm=crm)
    link = base + t.get("link", "/opendoctor-login.html")
    block = _code_boxes(code) if code else _button(t["button"], link)
    preheader = f"Seu código: {code} · vale 10 minutos" if code else lead
    notes = "<br><br>".join(html.escape(n) for n in t["notes"])
    body = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light">
<title>{html.escape(t["title"])}</title>
<style>
  @media (max-width:600px){{
    .wrap{{padding:48px 20px 0 !important}}
    .h1{{font-size:30px !important;line-height:36px !important}}
    .box{{width:44px !important;height:56px !important;line-height:56px !important;font-size:22px !important;border-radius:14px !important}}
    .gap{{width:6px !important}}
  }}
</style></head>
<body style="margin:0;padding:0;background:#FFFFFF">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#FFFFFF">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#FFFFFF">
  <tr><td class="wrap" align="center" style="padding:80px 24px 0">
    <table role="presentation" width="690" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:690px">
      <tr><td align="left">{logo}</td></tr>
      {_spacer(88)}
      <tr><td align="left" class="h1" style="max-width:586px;font-family:{_FONT};font-weight:500;font-size:40px;line-height:46px;letter-spacing:-1px;color:#000000">{html.escape(greet)}<br>{html.escape(t["title"])}</td></tr>
      {_spacer(20)}
      <tr><td align="left" style="max-width:640px;font-family:{_FONT};font-weight:500;font-size:15px;line-height:18px;letter-spacing:-0.2px;color:#000000">{html.escape(lead)}</td></tr>
      {_spacer(40)}
      <tr><td align="left">{block}</td></tr>
      {_spacer(100)}
      <tr><td align="left" style="max-width:640px;font-family:{_FONT};font-weight:500;font-size:15px;line-height:24px;color:#666666">{notes}</td></tr>
    </table>
  </td></tr>
  {_spacer(80)}
  <tr><td align="center" style="background:#F7F7F8;padding:80px 20px">{logo}</td></tr>
</table>
</body></html>"""
    text_parts = [greet, t["title"], "", lead, ""]
    if code:
        text_parts += [f"Código: {code}", ""]
    else:
        text_parts += [f"{t['button']}: {link}", ""]
    text_parts += t["notes"]
    return t["subject"].format(code=code, crm=crm), body, "\n".join(text_parts)


def _send(to, subject, body_html, body_text):
    sender = _env("EMAIL_FROM") or "OpenDoctor <acesso@opendoctor.app>"
    r = httpx.post(_API, timeout=15, headers={"Authorization": "Bearer " + _key()}, json={
        "from": sender, "to": [to], "subject": subject, "html": body_html, "text": body_text})
    if r.status_code >= 300:
        # status + tipo do erro do Resend (ex.: validation_error); a mensagem completa fica fora do log
        # porque pode repetir o e-mail do médico
        try:
            kind = str(r.json().get("name") or "")[:60]
        except Exception:
            kind = ""
        raise RuntimeError(f"resend {r.status_code} {kind}".strip())


def send_code(to, code, purpose, name=""):
    """Código de 6 dígitos (purpose: "signup" ou "reset"); levanta RuntimeError se o provedor recusar."""
    if debug_codes():
        print(f"[login-code:{purpose}] {to}: {code}", flush=True)   # só local (LOGIN_CODE_DEBUG=1, sem chave)
        return
    _send(to, *render(purpose, name=name, code=code))


def _now_brasilia():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3)))
    return now.strftime("%d/%m/%Y às %H:%M") + " (horário de Brasília)"


def send_password_changed(to, name=""):
    """Aviso de senha alterada (sem código)."""
    if debug_codes():
        print(f"[login-mail:changed] {to}", flush=True)
        return
    _send(to, *render("changed", name=name, when=_now_brasilia()))


def send_new_device(to, name="", device="", method=""):
    """Aviso de entrada por um aparelho novo (sem código)."""
    via = "a conta Google" if method == "google" else "e-mail e senha"
    if debug_codes():
        print(f"[login-mail:device] {to}: {device} ({via})", flush=True)
        return
    _send(to, *render("device", name=name, when=_now_brasilia(), device=device, via=via))


def send_crm_pending(admins, nome, crm, uf):
    """Avisa os administradores (auth.admin_emails) de um cadastro pendente. Vai só o nome e o CRM/UF do médico
    (nada de e-mail, CPF ou nascimento)."""
    numero = f"{crm}/{uf}"
    for to in admins:
        if debug_codes():
            print(f"[login-mail:crm_pendente] {to}", flush=True)
            continue
        _send(to, *render("crm_pendente", nome=nome, crm=numero))


def send_crm_decision(to, name="", aprovado=True):
    """Ao médico: cadastro aprovado (conta liberada) ou recusado."""
    purpose = "crm_aprovado" if aprovado else "crm_recusado"
    if debug_codes():
        print(f"[login-mail:{purpose}] {to}", flush=True)
        return
    _send(to, *render(purpose, name=name))


def send_cfm_alerta(admins):
    """Avisa os administradores de que o CFM recusou a chave (3010). Nada do médico vai junto."""
    for to in admins:
        if debug_codes():
            print(f"[login-mail:cfm_chave] {to}", flush=True)
            continue
        _send(to, *render("cfm_chave"))
