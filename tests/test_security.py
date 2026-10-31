"""Guardas de segurança da plataforma. Eles percorrem TODAS as rotas, páginas, migrações e arquivos —
não só os que existem hoje: rota nova, página nova ou tabela nova entra na conferência sozinha.

Se um teste daqui falhar, não "conserte o teste": leia o CLAUDE.md (regras de segurança) e decida.
"""
import os
import re
import subprocess

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

# O que abre sem login. Mudar esta lista é decisão consciente: precisa mudar aqui E em server.PUBLIC_*.
PUBLICOS = {"/", "/health", "/me", "/opendoctor-login.html", "/privacy", "/privacy.html", "/terms", "/terms.html"}
PREFIXOS_PUBLICOS = {"/auth/", "/assets/"}
# Tudo sob /auth/ é público: cada rota nova ali precisa ser revisada (não pode devolver dados).
ROTAS_AUTH = {
    ("GET", "/auth/google/login"), ("POST", "/auth/google/start"), ("POST", "/auth/email/check"),
    ("POST", "/auth/password/login"), ("POST", "/auth/signup/start"), ("POST", "/auth/signup/resend"),
    ("POST", "/auth/signup/verify"), ("POST", "/auth/password/forgot"), ("POST", "/auth/password/reset/verify"),
    ("POST", "/auth/password/reset"), ("GET", "/auth/logout"), ("GET", "/auth/{provider}/callback"),
    # Registro profissional da conta nova pelo Google (lê o perfil do cookie assinado deste navegador, não do corpo) e a
    # confirmação do CPF/nascimento da conta aprovada à mão (exige a sessão): as duas só devolvem ok/erro e o destino
    ("POST", "/auth/google/registro"), ("POST", "/auth/crm/confirmar"),
}


def _rotas():
    for r in server.app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD"}):
                yield m, r.path


def test_lista_publica_e_decisao_consciente():
    assert set(server.PUBLIC_PATHS) == PUBLICOS
    assert set(server.PUBLIC_PREFIXES) == PREFIXOS_PUBLICOS
    assert {(m, p) for m, p in _rotas() if p.startswith("/auth/")} == ROTAS_AUTH


def test_toda_rota_privada_exige_login():
    """Sem login, toda rota fora da lista pública devolve 401 — inclusive as que ainda vão ser criadas."""
    c = TestClient(server.app)
    privadas = 0
    for m, p in _rotas():
        url = re.sub(r"\{[^}]+\}", "x", p)
        if server.is_public(url):
            continue
        privadas += 1
        r = c.request(m, url, json={}, follow_redirects=False)
        assert r.status_code == 401, f"{m} {p} abriu sem login ({r.status_code})"
    assert privadas >= 20                       # a varredura de fato passou pelas rotas


def test_toda_pagina_e_arquivo_do_site_exige_login():
    """Arquivos da pasta web: só as páginas públicas e /assets/ abrem sem login."""
    c = TestClient(server.app)
    for base, _, files in os.walk(WEB):
        for f in files:
            url = "/" + os.path.relpath(os.path.join(base, f), WEB).replace(os.sep, "/")
            r = c.get(url, follow_redirects=False)
            if server.is_public(url):
                assert r.status_code == 200, url
            elif url.endswith(".html"):
                assert r.status_code == 302 and r.headers["location"].startswith("/opendoctor-login.html"), url
            else:
                assert r.status_code == 401, url


def test_caminhos_disfarcados_nao_escapam():
    c = TestClient(server.app)
    for url in ("http://testserver//opendoctor-agenda.html", "/./opendoctor-agenda.html", "/OPENDOCTOR-AGENDA.HTML",
                "/assets/../opendoctor-agenda.html", "/auth/../patients", "/auth/%2E%2E/patients"):
        r = c.get(url, follow_redirects=False)
        assert r.status_code in (302, 401, 404), url
        assert r.status_code != 200, url


def test_assets_so_tem_arquivos_estaticos():
    """/assets/ é público: nada de página, dado ou script ali."""
    for base, _, files in os.walk(os.path.join(WEB, "assets")):
        for f in files:
            assert f.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "svg", "woff2", "ico", "webp"}, f


def test_toda_tabela_tem_rls():
    """Toda tabela criada nas migrações liga o RLS (sem políticas: só o servidor acessa)."""
    pasta = os.path.join(ROOT, "supabase", "migrations")
    sql = "\n".join(open(os.path.join(pasta, f), encoding="utf-8").read() for f in sorted(os.listdir(pasta)))
    sql = re.sub(r"--[^\n]*", "", sql).lower()
    criadas = set(re.findall(r"create table(?: if not exists)?\s+(?:public\.)?(\w+)", sql))
    com_rls = set(re.findall(r"alter table\s+(?:public\.)?(\w+)\s+enable row level security", sql))
    assert criadas and criadas <= com_rls, f"tabelas sem RLS: {sorted(criadas - com_rls)}"


def _arquivos_do_repo():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [f for f in out.splitlines() if f]
    except Exception:
        return []


def test_nenhum_segredo_no_codigo():
    padroes = [r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",            # OpenAI
               r"\bre_[A-Za-z0-9]{20,}",                       # Resend
               r"GOCSPX-[A-Za-z0-9_-]{10,}",                   # Google client secret
               r"postgres(?:ql)?://[^:\s/]+:[^@\s<\[]{6,}@",   # senha do banco na URL ([SENHA] é exemplo)
               r"eyJhbGciOi[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"]   # JWT (chave do Supabase)
    arquivos = _arquivos_do_repo()
    assert ".env" not in arquivos
    for f in arquivos:
        if f.endswith((".png", ".jpg", ".woff2", ".pdf", ".ico")):
            continue
        try:
            txt = open(os.path.join(ROOT, f), encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for p in padroes:
            assert not re.search(p, txt), f"possível segredo em {f}"


def test_scripts_externos_fixos_e_permitidos_na_csp():
    """Script de fora do site: versão exata + hash de integridade + domínio liberado na CSP."""
    script_src = next(d for d in server._CSP.split("; ") if d.startswith("script-src"))
    for f in os.listdir(WEB):
        if not f.endswith(".html"):
            continue
        html = open(os.path.join(WEB, f), encoding="utf-8").read()
        for tag in re.findall(r"<script[^>]+src=[\"']https?://[^>]+>", html):
            src = re.search(r"src=[\"'](https?://[^/\"']+)", tag).group(1)
            assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, f"{f}: {tag}"
            assert src in script_src, f"{f}: {src} fora da CSP"
            assert not re.search(r"@\d+/", tag), f"{f}: versão não fixa em {tag}"


def test_csp_nao_aceita_script_injetado():
    """Só rodam os <script> escritos nas páginas (pelo hash). Nada de 'unsafe-inline', onclick= no HTML
    ou javascript: — com eles, um texto injetado (XSS) viraria código."""
    import base64
    import hashlib
    script_src = next(d for d in server._CSP.split("; ") if d.startswith("script-src"))
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src
    for f in os.listdir(WEB):
        if not f.endswith(".html"):
            continue
        html = open(os.path.join(WEB, f), encoding="utf-8").read()
        assert not re.search(r"<[^>]+\son[a-z]+\s*=", html), f"{f}: atributo on*= (use addEventListener)"
        assert "javascript:" not in html, f"{f}: link javascript:"
        for body in re.findall(r"<script>(.*?)</script>", html, re.S):
            h = "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
            assert h in script_src, f"{f}: script sem hash na CSP"


def test_retencao_respeita_a_lei():
    """Registro de acessos: o Marco Civil exige pelo menos 6 meses. E a limpeza nunca toca o prontuário."""
    from app import db
    keep = db.RETENTION["login_events"]
    n, unit = keep.split()
    meses = int(n) * {"year": 12, "years": 12, "month": 1, "months": 1}[unit]
    assert meses >= 6
    assert not set(db.RETENTION) & {"clinical_notes", "note_addenda", "patients", "access_log", "users"}
