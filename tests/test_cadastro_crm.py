"""Só médicos criam conta: o cliente do CFM (respostas prontas, sem rede), o Registro profissional do cadastro por e-mail
e pelo Google, a espera das contas pendentes, a página de cadastros dos administradores e a confirmação das contas
aprovadas à mão. Nada aqui fala com o CFM, com o banco ou com o Resend (tests/conftest.py)."""
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import auth, cfm, db, mailer, server
from tests.test_login import PW, REG, _client, _Fake, _novo, _user

CHAVE = "AbC12345"
CPF = "52998224725"


# ===================== cliente do CFM =====================

def _medico_xml(nome="ANA MARIA DE LIMA", situacao="A", crm="123456", uf="SP"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ConsultarResponse xmlns:ns2="http://servico.cfm.org.br/"><dadosMedico>
<crm>{crm}</crm><dataAtualizacao>01/10/2026</dataAtualizacao>
<especialidade>CARDIOLOGIA - RQE Nº: 1234</especialidade><especialidade>CLÍNICA MÉDICA - RQE Nº: 99</especialidade>
<nome>{nome}</nome><situacao>{situacao}</situacao><tipoInscricao>P</tipoInscricao><uf>{uf}</uf>
</dadosMedico></ns2:ConsultarResponse></S:Body></S:Envelope>"""


def _erro_xml(cod):
    return f"""<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ConsultarResponse xmlns:ns2="http://servico.cfm.org.br/"><dadosMedico><codigoErro>{cod}</codigoErro>
</dadosMedico></ns2:ConsultarResponse></S:Body></S:Envelope>"""


def _validar_xml(valor):
    return f"""<S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/"><S:Body>
<ns2:ValidarResponse xmlns:ns2="http://servico.cfm.org.br/"><resultadoConsulta>{valor}</resultadoConsulta>
</ns2:ValidarResponse></S:Body></S:Envelope>"""


@pytest.fixture
def ws(monkeypatch):
    """Web service do CFM simulado: cada pedido recebe a próxima resposta da fila (texto XML, status HTTP ou exceção)."""
    monkeypatch.setenv("CFM_CHAVE", CHAVE)
    st = {"fila": [], "pedidos": []}

    def handler(request):
        st["pedidos"].append(request)
        r = st["fila"].pop(0) if st["fila"] else _erro_xml("2010")
        if isinstance(r, Exception):
            raise r
        if isinstance(r, int):
            return httpx.Response(r, text="erro")
        if isinstance(r, bytes):
            return httpx.Response(200, content=r, headers={"content-type": "text/xml"})
        return httpx.Response(200, text=r, headers={"content-type": "text/xml; charset=utf-8"})
    monkeypatch.setattr(cfm, "_TRANSPORT", httpx.MockTransport(handler))
    monkeypatch.setattr(cfm.time, "sleep", lambda s: None)
    return st


def test_consultar_le_as_tags_conhecidas_e_monta_o_pedido_certo(ws, capsys):
    ws["fila"] = [_medico_xml()]
    r = cfm.consultar("1234", "RJ")
    assert r["status"] == "ok"
    m = r["medico"]
    assert (m["nome"], m["situacao"], m["uf"], m["atualizado"]) == ("ANA MARIA DE LIMA", "A", "SP", "01/10/2026")
    assert m["especialidades"] == ["CARDIOLOGIA - RQE Nº: 1234", "CLÍNICA MÉDICA - RQE Nº: 99"]
    p = ws["pedidos"][0]
    assert str(p.url) == cfm.URL and p.method == "POST"
    assert p.headers["soapaction"] == '""' and p.headers["content-type"] == "text/xml; charset=utf-8"
    corpo = p.content.decode()
    assert "<ser:Consultar>" in corpo and "<crm>1234</crm>" in corpo and "<uf>RJ</uf>" in corpo
    assert f"<chave>{CHAVE}</chave>" in corpo and CHAVE not in str(p.url)      # a chave vai só no corpo
    assert CHAVE not in capsys.readouterr().out                                # e nunca no log


def test_consultar_erros(ws):
    ws["fila"] = [_erro_xml("8101")]
    assert cfm.consultar("1", "SP") == {"status": "nao_encontrado"}
    for cod in ("3010", "4000", "4010", "4020"):                    # chave ou pedido: não diz nada do médico
        ws["fila"], ws["pedidos"] = [_erro_xml(cod)], []
        assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": cod} and len(ws["pedidos"]) == 1
    for cod in ("2010", "2030", "2040"):                            # passageiro: tenta mais uma vez
        ws["fila"], ws["pedidos"] = [_erro_xml(cod), _medico_xml()], []
        assert cfm.consultar("1", "SP")["status"] == "ok" and len(ws["pedidos"]) == 2
        ws["fila"], ws["pedidos"] = [_erro_xml(cod), _erro_xml(cod)], []
        assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": cod} and len(ws["pedidos"]) == 2
    ws["fila"] = [500]
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = [httpx.ConnectError("sem rede")]
    assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": "rede"}
    ws["fila"] = ['<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>']               # XML com entidades: nem lê
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = ["isto não é xml"]
    assert cfm.consultar("1", "SP")["status"] == "indisponivel"
    ws["fila"] = ["<S:Envelope xmlns:S='x'><S:Body><dadosMedico><crm>1</crm></dadosMedico></S:Body></S:Envelope>"]
    assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": "resposta"}   # sem nome e situação


_AMPLIA = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
           '<dadosMedico><nome>&b;</nome><situacao>A</situacao></dadosMedico>')


def test_ler_recusa_dtd_e_entidades_em_qualquer_codificacao():
    """O parser recusa o DOCTYPE (e as entidades) sozinho, sem procurar bytes: em UTF-16 o "<!DOCTYPE" não aparece cru."""
    utf8 = _AMPLIA.replace("UTF-16", "UTF-8")
    for ruim in (_AMPLIA.encode("utf-16"), _AMPLIA.encode("utf-16-le"), _AMPLIA.encode("utf-16-be"),
                 utf8.encode("utf-8"), utf8.replace('<?xml version="1.0" encoding="UTF-8"?>', "").encode("utf-8"),
                 '<!DOCTYPE d SYSTEM "file:///etc/passwd"><dadosMedico><nome>x</nome></dadosMedico>'.encode(),
                 b"<dadosMedico><nome>&a;</nome></dadosMedico>",                             # entidade sem DTD
                 "<dadosMedico><nome>ANA</nome><situacao>A</situacao></dadosMedico>".encode("utf-16")):   # só UTF-8
        with pytest.raises(ValueError):
            cfm.ler(ruim)
    ok = cfm.ler(("﻿" + _medico_xml("ANA &amp; LIMA")).encode("utf-8"))           # UTF-8 com BOM e &amp; valem
    assert ok["nome"] == "ANA & LIMA" and ok["situacao"] == "A" and len(ok["especialidade"]) == 2


def test_consultar_recusa_resposta_em_utf16_com_entidades(ws):
    ws["fila"] = [_AMPLIA.encode("utf-16")]
    assert cfm.consultar("1", "SP") == {"status": "indisponivel", "codigo": "rede"}


def test_validar(ws, capsys):
    ws["fila"] = [_validar_xml("true")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985") == {"status": "ok", "valido": True}
    corpo = ws["pedidos"][0].content.decode()
    assert "<ser:Validar>" in corpo and f"<cpf>{CPF}</cpf>" in corpo and "<dataNascimento>12/05/1985</dataNascimento>" in corpo
    ws["fila"] = [_validar_xml("false")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985") == {"status": "ok", "valido": False}
    ws["fila"] = [_erro_xml("2040"), _erro_xml("2040")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985")["status"] == "indisponivel"
    ws["fila"] = [_validar_xml("talvez")]
    assert cfm.validar("123456", "SP", CPF, "12/05/1985")["status"] == "indisponivel"
    out = capsys.readouterr().out
    assert CPF not in out and "12/05/1985" not in out and CHAVE not in out and "[cfm] Validar" in out


def test_sem_chave_nao_chama_o_cfm(monkeypatch):
    chamou = []
    monkeypatch.setattr(cfm, "_TRANSPORT", httpx.MockTransport(lambda r: chamou.append(r) or httpx.Response(200)))
    assert not cfm.configured()
    assert cfm.consultar("1", "SP")["status"] == "indisponivel" and cfm.validar("1", "SP", CPF, "01/01/1980")["status"] == "indisponivel"
    assert chamou == []


def test_separa_crm_e_uf():
    casos = {("CRM-SP 123456", ""): ("123456", "SP"), ("CRM/SP 123.456", ""): ("123456", "SP"),
             ("SP 123456", ""): ("123456", "SP"), ("123456/SP", ""): ("123456", "SP"), ("123456-SP", ""): ("123456", "SP"),
             ("52-1234/RJ", ""): ("1234", "RJ"), ("52-1234", "RJ"): ("1234", "RJ"), ("1234567-P/SP", ""): ("1234567", "SP"),
             ("1234567-P", "mg"): ("1234567", "MG"), ("300-EMFE-1234567", "SP"): ("1234567", "SP"),
             ("123456", "sp"): ("123456", "SP"), ("CRMSP123456", ""): ("123456", "SP"), ("crm-ce 4321", "SP"): ("4321", "CE"),
             ("52-1234", "SP"): ("521234", "SP")}                        # o 52- só cai no RJ
    for (texto, uf), esperado in casos.items():
        assert cfm.separa_crm(texto, uf) == esperado, texto
    assert cfm.crm_numero("0012345") == "12345" and cfm.crm_numero("1234567") == "1234567"
    for ruim in ("", "0", "12345678", "12a"):
        assert cfm.crm_numero(ruim) is None, ruim


def test_nome_confere_com_o_cfm():
    assert cfm.nome_confere("Ana Lima", "ANA MARIA DE LIMA")
    assert cfm.nome_confere("Dra. Ana  Maria Lima", "ANA MARIA DE LIMA")              # tratamento e espaços
    assert cfm.nome_confere("José da Conceição", "JOSE DA CONCEICAO SANTOS")           # acentos e conectores
    assert cfm.nome_confere("ana de lima", "Ana Maria Lima")
    assert not cfm.nome_confere("Ana Souza", "ANA MARIA DE LIMA")                     # sobrenome que não está lá
    assert not cfm.nome_confere("Maria Lima", "ANA MARIA DE LIMA")                    # primeiro nome diferente
    assert not cfm.nome_confere("Ana", "ANA MARIA DE LIMA")                           # só uma palavra
    assert not cfm.nome_confere("Ana de", "ANA MARIA DE LIMA")
    # o primeiro nome repetido não serve de sobrenome (o nome vai na receita)
    assert not cfm.nome_confere("Ana Ana", "ANA MARIA DE LIMA")
    assert not cfm.nome_confere("Ana de Ana", "ANA MARIA DE LIMA")
    assert cfm.nome_confere("Ana Maria", "ANA MARIA DE LIMA")                         # o nome do meio está lá


def test_nome_com_apostrofo_e_sufixo():
    """D'Ávila = Davila = Ávila; Sant'Anna = Santanna; Jr. = Júnior; Fº = Filho; com sufixo, vale o sobrenome antes dele."""
    for digitado, do_cfm in (("Maria José D'Ávila", "MARIA JOSE DAVILA"), ("Maria Jose Davila", "MARIA JOSÉ D'ÁVILA"),
                             ("Maria Avila", "MARIA D'AVILA"), ("Ana Sant'Anna", "ANA SANTANNA"),
                             ("Ana Sant’Anna", "ANA SANT'ANNA"), ("Carlos Silva Jr", "CARLOS SILVA JUNIOR"),
                             ("Carlos Silva Júnior", "CARLOS SILVA JR"), ("Carlos Silva Jr.", "CARLOS SILVA"),
                             ("Carlos Silva Filho", "CARLOS SILVA Fº"), ("Pedro Souza Neto", "PEDRO HENRIQUE SOUZA")):
        assert cfm.nome_confere(digitado, do_cfm), (digitado, do_cfm)
    assert not cfm.nome_confere("Carlos Junior", "CARLOS SILVA")                      # o sufixo sozinho não é sobrenome
    assert not cfm.nome_confere("Ana Souza Neto", "ANA MARIA DE LIMA")
    assert cfm.palavras("Dr. João D'Ávila Jr.") == ["joao", "davila", "junior"]


def test_nome_colado_com_o_acento_separado():
    """Nome copiado de PDF ou do macOS (NFD: a letra e o acento separados) vale como o digitado, e é guardado em NFC."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", "José Conceição")
    assert nfd != "José Conceição" and server._nome_completo(nfd) == "José Conceição"
    assert cfm.nome_confere(nfd, "JOSE DA CONCEICAO")


# ===================== cadastro por e-mail =====================

def _cfm_simulado(monkeypatch, consulta=None, valido=True, em_uso=False):
    """CFM com chave: Consultar devolve `consulta` (padrão: médico regular ANA MARIA DE LIMA) e Validar, `valido`."""
    monkeypatch.setattr(cfm, "configured", lambda: True)
    st = {"consultas": [], "validacoes": []}

    def consultar(crm, uf):
        st["consultas"].append((crm, uf))
        return consulta or {"status": "ok", "medico": {"nome": "ANA MARIA DE LIMA", "situacao": "A"}}

    def validar(crm, uf, cpf, nasc):
        st["validacoes"].append((crm, uf, cpf, nasc))
        return valido if isinstance(valido, dict) else {"status": "ok", "valido": valido}
    monkeypatch.setattr(cfm, "consultar", consultar)
    monkeypatch.setattr(cfm, "validar", validar)
    monkeypatch.setattr(db, "crm_in_use", lambda crm, uf: em_uso)
    _tentativas(monkeypatch, st)
    return st


def _tentativas(monkeypatch, st):
    """O contador do banco (cfm_tentativas) em memória: chave → quantas vezes contou."""
    st.setdefault("tentativas", {})

    def usa(chave, maximo, janela_s):
        if st["tentativas"].get(chave, 0) >= maximo:
            return False
        st["tentativas"][chave] = st["tentativas"].get(chave, 0) + 1
        return True
    monkeypatch.setattr(db, "cfm_tentativa_usa", usa, raising=False)
    monkeypatch.setattr(db, "cfm_tentativas", lambda chave, janela_s: st["tentativas"].get(chave, 0), raising=False)
    monkeypatch.setattr(db, "cfm_tentativa_registra",
                        lambda chave: st["tentativas"].__setitem__(chave, st["tentativas"].get(chave, 0) + 1), raising=False)


def _avisos(monkeypatch, fake):
    monkeypatch.setattr(mailer, "send_crm_pending", lambda admins, nome, crm, uf: fake.sent.append(("admins", tuple(admins), nome, crm, uf)))
    monkeypatch.setattr(mailer, "send_crm_decision", lambda to, name="", aprovado=True: fake.sent.append((to, name, "aprovado" if aprovado else "recusado")))


def _corpo_do_tiquete(t):
    body = t.split(".")[0]
    return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()


def test_cadastro_verificado_no_cfm(monkeypatch, capsys):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    st = _cfm_simulado(monkeypatch)
    r = c.post("/auth/signup/start", json=_novo(crm="CRM-SP 123.456", uf=""))
    assert r.status_code == 200, r.text
    assert st["consultas"] == [("123456", "SP")] and st["validacoes"] == [("123456", "SP", CPF, "12/05/1985")]
    corpo = _corpo_do_tiquete(r.json()["ticket"])
    assert CPF not in corpo and "529.982" not in corpo and "1985" not in corpo        # o CPF e o nascimento não vão no tíquete
    to, code, purpose = fake.sent[-1]
    r = c.post("/auth/signup/verify", json={"ticket": r.json()["ticket"], "code": code})
    assert r.json() == {"ok": True, "redirect": auth.HOME + "?bemvindo=1"}             # sem espera: vai para o app
    u = fake.users["novo@clinica.com.br"]
    assert (u["name"], u["crm"], u["crm_uf"], u["crm_status"], u["crm_fonte"]) == ("Ana Lima", "123456", "SP", "verificado", "cfm")
    assert [s for s in fake.sent if s[0] == "admins"] == []                             # verificado: ninguém precisa aprovar
    out = capsys.readouterr().out
    assert CPF not in out and "12/05/1985" not in out


def test_cadastro_sem_chave_fica_pendente_e_avisa_os_administradores(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "Dono@OpenDoctor.app, outro@opendoctor.app")
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    r = c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]})
    assert r.json()["ok"] and r.json()["bloqueio"] == "crm_pendente" and auth.COOKIE_NAME in r.cookies
    u = fake.users["novo@clinica.com.br"]
    assert (u["crm_status"], u["crm_fonte"], u["crm"], u["crm_uf"]) == ("pendente", None, "123456", "SP")
    aviso = [s for s in fake.sent if s[0] == "admins"]
    assert aviso == [("admins", ("dono@opendoctor.app", "outro@opendoctor.app"), "Ana Lima", "123456", "SP")]   # só nome e CRM


def test_aviso_ao_administrador_so_leva_nome_e_crm():
    subj, body, text = mailer.render("crm_pendente", nome="Ana Lima", crm="123456/SP")
    assert "Ana Lima" in body and "123456/SP" in body and "123456/SP" in subj and "opendoctor-cadastros.html" in body
    assert "@" not in text.replace("opendoctor.app", "") and CPF not in body
    subj, body, text = mailer.render("crm_aprovado", name="Ana Lima")
    assert "Ana," in body and "liberada" in body
    subj, body, text = mailer.render("crm_recusado", name="Ana Lima")
    assert "Não conseguimos confirmar seu CRM" in body


@pytest.mark.parametrize("consulta,valido,erro", [
    ({"status": "nao_encontrado"}, True, "crm_nao_encontrado"),
    ({"status": "ok", "medico": {"nome": "ANA MARIA DE LIMA", "situacao": "C"}}, True, "crm_irregular"),
    ({"status": "ok", "medico": {"nome": "BEATRIZ SOUZA", "situacao": "A"}}, True, "crm_nome"),
    (None, False, "crm_dados"),
])
def test_cadastro_recusado_nao_cria_nada(monkeypatch, consulta, valido, erro):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, consulta, valido)
    r = c.post("/auth/signup/start", json=_novo())
    assert r.status_code == 400 and r.json() == {"error": erro}
    assert fake.sent == [] and fake.codes == {} and fake.users == {}                 # nem código, nem conta


@pytest.mark.parametrize("consulta,valido", [
    ({"status": "indisponivel", "codigo": "2010"}, True),                  # CFM fora do ar
    ({"status": "indisponivel", "codigo": "3010"}, True),                  # chave vencida
    (None, {"status": "indisponivel", "codigo": "rede"}),                  # Validar sem resposta
])
def test_cfm_indisponivel_fica_pendente(monkeypatch, consulta, valido):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, consulta, valido)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    assert c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]}).json()["bloqueio"] == "crm_pendente"
    assert fake.users["novo@clinica.com.br"]["crm_status"] == "pendente"


def test_crm_de_outra_conta_fica_pendente(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, em_uso=True)
    t = c.post("/auth/signup/start", json=_novo()).json()["ticket"]
    c.post("/auth/signup/verify", json={"ticket": t, "code": fake.sent[-1][1]})
    assert fake.users["novo@clinica.com.br"]["crm_status"] == "pendente"


def test_campos_do_registro(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    erros = {"nome": ["Ana", "Dra. Ana", "Ana 2 Lima", ""], "cpf": ["529.982.247-24", "111.111.111-11", "123"],
             "nascimento": ["31/02/1990", "12/05/2015", "12/05/1900", "1990-13-01", "ontem"],
             "crm": ["", "12345678", "CRM-SP"], "uf": ["", "XX", "S"]}
    for campo, ruins in erros.items():
        for v in ruins:
            r = c.post("/auth/signup/start", json=dict(_novo(), **{campo: v}))
            assert r.json() == {"error": campo}, (campo, v, r.json())
    assert fake.sent == []
    for bom in ({"nascimento": "1985-05-12"}, {"crm": "123456/rj", "uf": ""}, {"nome": "Maria D'Ávila"}, {"cpf": CPF}):
        server._RL.clear()
        assert c.post("/auth/signup/start", json=dict(_novo(), **bom)).json()["ok"], bom


def test_tiquete_de_antes_do_registro_nao_cria_conta(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    velho = auth.sign({"k": "signup", "email": "novo@clinica.com.br", "name": "Nova", "ph": auth.hash_password(PW)})
    assert c.post("/auth/signup/verify", json={"ticket": velho, "code": "123456"}).json()["error"] == "sessao_expirada"
    assert fake.users == {}


def test_limite_de_conferencias_no_cfm(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    st = _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    monkeypatch.setitem(server.RATE_LIMITS, "login_code", (100, 600))
    rs = [c.post("/auth/signup/start", json=_novo(crm=str(1000 + i))) for i in range(server.RATE_LIMITS["cfm"][0] + 1)]
    assert rs[-1].status_code == 429 and rs[-1].json()["error"] == "limite_ip"
    assert len(st["consultas"]) == server.RATE_LIMITS["cfm"][0]


def test_limite_por_ip_conta_o_ipv6_pelo_prefixo_64(monkeypatch):
    assert server._rl_ip("2001:db8:1:1::1") == server._rl_ip("2001:db8:1:1:ffff::9") == "2001:db8:1:1::/64"
    assert server._rl_ip("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert server._rl_ip("203.0.113.7") == "203.0.113.7" == server._rl_ip("::ffff:203.0.113.7")
    assert server._rl_ip("?") == "?"
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    monkeypatch.setitem(server.RATE_LIMITS, "login_code", (100, 600))
    n = server.RATE_LIMITS["cfm"][0]
    rs = [c.post("/auth/signup/start", json=_novo(crm=str(2000 + i)), headers={"CF-Connecting-IP": f"2001:db8:1:1::{i + 1:x}"})
          for i in range(n + 1)]
    assert [r.status_code for r in rs[:n]] == [400] * n and rs[n].status_code == 429    # trocar dentro do /64 não ajuda
    r = c.post("/auth/signup/start", json=_novo(crm="3000"), headers={"CF-Connecting-IP": "2001:db8:1:2::1"})
    assert r.status_code == 400                                                         # outro /64: outro limite


def test_limite_por_crm_vale_para_qualquer_ip(monkeypatch):
    """O Validar não vira oráculo do CPF/nascimento de um médico: o mesmo CRM/UF tem poucas conferências por dia, de
    qualquer IP; passou disso, o cadastro fica pendente sem chamar o CFM (a resposta é a mesma com a data certa ou não)."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    st = _cfm_simulado(monkeypatch, valido=False)
    monkeypatch.setitem(server.RATE_LIMITS, "login_code", (100, 600))
    n = server.CRM_TENTATIVAS[0]
    for i in range(n):
        r = c.post("/auth/signup/start", json=_novo(nascimento=f"{i + 1:02d}/03/1979"), headers={"CF-Connecting-IP": f"198.51.100.{i}"})
        assert r.status_code == 400 and r.json() == {"error": "crm_dados"}
    r = c.post("/auth/signup/start", json=_novo(nascimento="07/03/1979"), headers={"CF-Connecting-IP": "192.0.2.77"})
    assert r.status_code == 200 and json.loads(_corpo_do_tiquete(r.json()["ticket"]))["crm"]["status"] == "pendente"
    assert len(st["consultas"]) == len(st["validacoes"]) == n                   # a 6ª nem foi ao CFM
    assert st["tentativas"] == {"crm:SP:123456": n}
    r = c.post("/auth/signup/start", json=_novo(email="outra@clinica.com.br", crm="654321"), headers={"CF-Connecting-IP": "192.0.2.78"})
    assert r.json() == {"error": "crm_dados"} and len(st["validacoes"]) == n + 1     # outro CRM: conferido normalmente


def test_crm_repetido_na_hora_de_criar_a_conta_fica_pendente_e_avisa(monkeypatch):
    """Dois cadastros com o mesmo CRM começados juntos: os dois tíquetes dizem 'verificado' (nenhuma conta existia no
    início), mas só o primeiro a confirmar o código fica verificado; o segundo nasce pendente (quem decide é o banco, na
    hora de criar: db._CRM_DECISAO) e os administradores recebem o aviso."""
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    _cfm_simulado(monkeypatch)
    ta = c.post("/auth/signup/start", json=_novo(email="a@clinica.com.br")).json()["ticket"]
    ca = fake.sent[-1][1]
    tb = c.post("/auth/signup/start", json=_novo(email="b@clinica.com.br")).json()["ticket"]
    cb = fake.sent[-1][1]
    assert [json.loads(_corpo_do_tiquete(t))["crm"]["status"] for t in (ta, tb)] == ["verificado", "verificado"]
    assert "bloqueio" not in c.post("/auth/signup/verify", json={"ticket": ta, "code": ca}).json()
    r = c.post("/auth/signup/verify", json={"ticket": tb, "code": cb})
    assert r.json()["bloqueio"] == "crm_pendente"
    b = fake.users["b@clinica.com.br"]
    assert (b["crm_status"], b["crm_fonte"]) == ("pendente", None) and fake.users["a@clinica.com.br"]["crm_status"] == "verificado"
    assert [s for s in fake.sent if s[0] == "admins"] == [("admins", ("dono@opendoctor.app",), "Ana Lima", "123456", "SP")]


def test_nome_colado_com_o_acento_separado_no_cadastro(monkeypatch):
    import unicodedata
    fake = _Fake()
    c = _client(monkeypatch, fake)
    r = c.post("/auth/signup/start", json=_novo(nome=unicodedata.normalize("NFD", "José Conceição")))
    assert r.json()["ok"] and json.loads(_corpo_do_tiquete(r.json()["ticket"]))["name"] == "José Conceição"


# ===================== conta nova pelo Google =====================

def _google(monkeypatch, fake, existe=False, verificado=True):
    """Volta do Google simulada. `verificado`: o Google confirmou o e-mail da conta (email_verified)."""
    from app import integrations
    monkeypatch.setattr(integrations, "configured", lambda p: True)
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(auth, "exchange_login", lambda code: {"email": "Nova@Clinica.com.br", "name": "Nova Google",
                                                             "picture": "https://foto", "sub": "g-1",
                                                             "email_verified": verificado})
    if existe:
        fake.users.update(_user("nova@clinica.com.br", pw=None))
    criadas = []

    def upsert(email, name=None, picture=None, google_sub=None, crm=None):
        crm = crm or {}
        criadas.append((email, name, crm))
        u = fake.users.setdefault(email, {"id": "u-" + email, "email": email, "name": name, "sv": 0,
                                          "crm_status": crm.get("status"), "crm_fonte": crm.get("fonte")})
        return u
    monkeypatch.setattr(db, "upsert_user", upsert)
    return criadas


def _volta_do_google(c, q=""):
    import urllib.parse as up
    r = c.get("/auth/google/login" + q, follow_redirects=False)
    state = up.parse_qs(up.urlparse(r.headers["location"]).query)["state"][0]
    return c.get("/auth/google/callback?code=x&state=" + up.quote(state), follow_redirects=False)


def test_google_conta_nova_guarda_o_next_e_o_registro_na_url(monkeypatch):
    """Recarregar o Registro (ou voltar e entrar de novo) não perde a etapa nem a página de origem."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _google(monkeypatch, fake)
    r = _volta_do_google(c, "?next=/opendoctor-configuracoes.html")
    assert r.headers["location"] == "/opendoctor-login.html?registro=google&next=%2Fopendoctor-configuracoes.html"
    r = _volta_do_google(c, "?next=https://mal.example/x")                      # destino de fora: fica sem next
    assert r.headers["location"] == "/opendoctor-login.html?registro=google"
    assert c.post("/auth/google/registro", json=REG).json()["redirect"] == auth.HOME + "?bemvindo=1"


def test_google_conta_nova_passa_pelo_registro(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _avisos(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    r = _volta_do_google(c)
    assert r.headers["location"] == "/opendoctor-login.html?registro=google"            # nada do perfil na URL
    assert auth.COOKIE_NAME not in r.cookies and criadas == [] and fake.users == {}     # a conta ainda não existe
    assert r.cookies.get(server.GREG_COOKIE)
    assert TestClient(server.app).post("/auth/google/registro", json=REG).json()["error"] == "sessao_expirada"   # outro navegador
    assert c.post("/auth/google/registro", json=dict(REG, cpf="123")).json()["error"] == "cpf"
    r = c.post("/auth/google/registro", json=REG)
    assert r.json()["ok"] and r.json()["bloqueio"] == "crm_pendente" and auth.COOKIE_NAME in r.cookies
    assert criadas == [("nova@clinica.com.br", "Ana Lima",
                        {"crm": "123456", "uf": "SP", "status": "pendente", "fonte": None, "situacao": None})]
    assert [e[1:3] for e in fake.events] == [("entrou", "cadastro")]


def test_google_registro_recusado_e_verificado(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    _volta_do_google(c)
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "crm_nao_encontrado"} and criadas == []
    _cfm_simulado(monkeypatch)
    r = c.post("/auth/google/registro", json=REG)
    assert r.json() == {"ok": True, "redirect": auth.HOME + "?bemvindo=1"}
    assert criadas[0][2]["status"] == "verificado" and fake.users["nova@clinica.com.br"]["crm_fonte"] == "cfm"


def test_google_registro_nao_entra_em_conta_que_passou_a_existir(monkeypatch):
    """O tíquete do Google só cria conta: se o e-mail ganhou uma conta no meio do caminho, ele não serve de login."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    _volta_do_google(c)
    fake.users.update(_user("nova@clinica.com.br"))
    r = c.post("/auth/google/registro", json=REG)
    assert r.json() == {"error": "sessao_expirada"} and auth.COOKIE_NAME not in r.cookies and criadas == []
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "sessao_expirada"}     # o cookie foi apagado


def test_google_conta_que_ja_existe_entra_como_sempre(monkeypatch):
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake, existe=True)
    r = _volta_do_google(c)
    assert r.headers["location"] == auth.HOME and auth.COOKIE_NAME in r.cookies
    assert not r.cookies.get(server.GREG_COOKIE) and criadas == [("nova@clinica.com.br", "Nova Google", {})]


@pytest.mark.parametrize("existe", [True, False], ids=["conta que existe", "conta nova"])
def test_google_com_email_nao_verificado_nao_entra_nem_cria_conta(monkeypatch, capsys, existe):
    """Conta Google com um e-mail que o Google não confirmou (email_verified false): sem isso, bastaria abrir uma conta
    Google com o e-mail de um médico para entrar na conta dele (ou abrir uma no nome dele). Volta para a tela de login
    com o motivo; nada de sessão, de cookie do Registro nem de conta."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake, existe=existe, verificado=False)
    r = _volta_do_google(c, "?next=/opendoctor-configuracoes.html")
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/opendoctor-login.html?erro=google_nao_verificado&next=%2Fopendoctor-configuracoes.html"
    assert auth.COOKIE_NAME not in r.cookies and not r.cookies.get(server.GREG_COOKIE)
    assert criadas == [] and fake.events == []                               # nem atualizou a conta, nem registrou entrada
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "sessao_expirada"}
    assert c.get("/me").json()["logged_in"] is False
    assert "nova@clinica.com.br" not in capsys.readouterr().out.lower()      # o e-mail não vai para o log
    # o mesmo médico com o e-mail confirmado pelo Google: sem passo a mais (entra, ou vai direto ao Registro)
    _google(monkeypatch, fake, existe=existe, verificado=True)
    r = _volta_do_google(c)
    assert r.headers["location"] == (auth.HOME if existe else "/opendoctor-login.html?registro=google")


def test_registro_google_so_com_o_cookie_que_tem_a_marca_do_email_confirmado(monkeypatch):
    """O cookie do Registro de antes da conferência do email_verified (sem a marca `ev`) não cria conta."""
    fake = _Fake()
    c = _client(monkeypatch, fake)
    criadas = _google(monkeypatch, fake)
    velho = {"k": "greg", "email": "nova@clinica.com.br", "sub": "g-1", "nx": auth.HOME}
    c.cookies.set(server.GREG_COOKIE, auth.sign(velho))
    assert c.post("/auth/google/registro", json=REG).json() == {"error": "sessao_expirada"} and criadas == []
    c.cookies.clear()
    c.cookies.set(server.GREG_COOKIE, auth.sign(dict(velho, ev=1)))
    assert c.post("/auth/google/registro", json=REG).json()["ok"] and len(criadas) == 1


def test_email_verificado_pelo_google():
    """userinfo v2 (verified_email) e OpenID (email_verified, no id_token): precisa de um "sim" e nenhum "não"."""
    def jwt(claims):
        return "e30." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".assinatura"
    em = "ana@clinica.com.br"
    assert auth.email_verificado({"email": em, "verified_email": True})
    assert not auth.email_verificado({"email": em, "verified_email": False})
    assert not auth.email_verificado({"email": em})                                       # sem a informação: não
    assert auth.email_verificado({"email": em}, jwt({"email": em, "email_verified": True}))
    assert auth.email_verificado({"email": em}, jwt({"email": "Ana@Clinica.com.br", "email_verified": "true"}))
    assert not auth.email_verificado({"email": em, "verified_email": True}, jwt({"email": em, "email_verified": False}))
    assert not auth.email_verificado({"email": em, "email_verified": "false"})
    assert not auth.email_verificado({"email": em}, jwt({"email": "outra@x.com", "email_verified": True}))   # de outro e-mail
    assert not auth.email_verificado({"email": em}, "nao-e-jwt")
    assert not auth.email_verificado({"email": em, "verified_email": 1})                  # só True ou "true"


def test_exchange_login_le_a_confirmacao_do_email(monkeypatch):
    """O perfil sai do userinfo v2 (verified_email) e do id_token da troca do code, sem rede."""
    from app import integrations
    monkeypatch.setattr(integrations, "_cid", lambda p: "cid")
    monkeypatch.setattr(integrations, "_secret", lambda p: "segredo")
    resp = {"userinfo": {"id": "g-1", "email": "ana@clinica.com.br", "verified_email": True, "name": "Ana"}, "id_token": None}

    class R:
        def __init__(self, j):
            self.status_code, self._j, self.text = 200, j, ""

        def json(self):
            return self._j
    monkeypatch.setattr(auth.httpx, "post", lambda url, **k: R({"access_token": "at", "id_token": resp["id_token"]}))
    monkeypatch.setattr(auth.httpx, "get", lambda url, **k: R(resp["userinfo"]))
    assert auth.exchange_login("code") == {"email": "ana@clinica.com.br", "name": "Ana", "picture": None, "sub": "g-1",
                                           "email_verified": True}
    resp["userinfo"]["verified_email"] = False
    assert auth.exchange_login("code")["email_verified"] is False
    del resp["userinfo"]["verified_email"]
    resp["id_token"] = "e30." + base64.urlsafe_b64encode(json.dumps(
        {"email": "ana@clinica.com.br", "email_verified": True}).encode()).decode().rstrip("=") + ".x"
    assert auth.exchange_login("code")["email_verified"] is True


# ===================== a espera das contas pendentes =====================

def _logado(monkeypatch, cc=False, **conta):
    """Sessão aberta da conta u1. `cc`: a sessão nasceu pedindo a confirmação do CRM (login com a chave do CFM)."""
    u = dict({"id": "u1", "email": "ana@clinica.com.br", "name": "Ana Lima", "sv": 0, "crm_status": None, "crm_fonte": None}, **conta)
    monkeypatch.setattr(db, "get_user", lambda uid: dict(u) if uid == "u1" else None)
    c = TestClient(server.app)
    c.cookies.set(auth.COOKIE_NAME, auth.sign(dict({"k": "sess", "uid": "u1", "sv": 0}, **({"cc": 1} if cc else {}))))
    return c


def _sessao(resp):
    return auth.unsign(resp.cookies.get(auth.COOKIE_NAME) or "", auth.SESSION_MAX_AGE)


@pytest.mark.parametrize("status,motivo", [("pendente", "crm_pendente"), ("recusado", "crm_recusado"), ("??", "crm_pendente")])
def test_conta_pendente_entra_mas_nao_usa_o_app(monkeypatch, status, motivo):
    c = _logado(monkeypatch, crm_status=status)
    r = c.get("/opendoctor-agenda.html", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/opendoctor-login.html?next=%2Fopendoctor-agenda.html"
    r = c.get("/cid10?q=diabetes")
    assert r.status_code == 403 and r.json() == {"error": motivo}
    assert c.get("/patients", headers={"accept": "text/html"}, follow_redirects=False).status_code == 302   # link clicado
    assert c.post("/prontuario/list", json={"patient_id": 1}).status_code == 403
    assert c.get("/vendor/x.js").status_code == 403
    me = c.get("/me").json()
    assert me["logged_in"] and me["bloqueio"] == motivo
    for livre in ("/opendoctor-login.html", "/assets/email/logo.png", "/privacy.html"):
        assert c.get(livre).status_code == 200, livre
    assert c.get("/auth/logout", follow_redirects=False).status_code == 307


@pytest.mark.parametrize("conta", [{}, {"crm_status": "verificado", "crm_fonte": "cfm"},
                                   {"crm_status": "verificado", "crm_fonte": "manual"}])
def test_contas_antigas_e_verificadas_seguem_como_sempre(monkeypatch, conta):
    c = _logado(monkeypatch, **conta)
    assert c.get("/cid10?q=diabetes").status_code == 200
    assert c.get("/opendoctor-agenda.html", follow_redirects=False).status_code == 200
    assert c.get("/me").json()["bloqueio"] is None


def test_login_com_senha_de_conta_pendente_avisa_a_tela(monkeypatch):
    fake = _Fake(_user("ana@clinica.com.br", crm_status="pendente"))
    c = _client(monkeypatch, fake)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json() == {"ok": True, "redirect": auth.HOME, "bloqueio": "crm_pendente"}
    fake = _Fake(_user("ana@clinica.com.br"))                                     # conta antiga: igual a antes
    c = _client(monkeypatch, fake)
    assert c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW}).json() == {"ok": True, "redirect": auth.HOME}


# ===================== aprovada à mão: confirma CPF e nascimento quando houver a chave =====================

def test_aprovada_a_mao_confirma_uma_vez_quando_ha_chave(monkeypatch):
    c = _logado(monkeypatch, cc=True, crm_status="verificado", crm_fonte="manual")
    monkeypatch.setattr(db, "get_medico", lambda uid: {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP"})
    confirmou = []
    monkeypatch.setattr(db, "crm_confirmed", lambda uid: confirmou.append(uid) or True)
    st = _cfm_simulado(monkeypatch, valido=False)
    assert c.get("/cid10?q=diabetes").json() == {"error": "crm_confirmar"}
    assert c.get("/me").json()["bloqueio"] == "crm_confirmar"
    assert "crm_cc" not in c.get("/me").json()["user"]
    assert c.post("/auth/crm/confirmar", json={"cpf": "123", "nascimento": "12/05/1985"}).json() == {"error": "cpf"}
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.json() == {"error": "crm_dados"} and confirmou == []                    # não bateu: pede de novo
    assert c.get("/cid10?q=diabetes").status_code == 403
    st = _cfm_simulado(monkeypatch, valido=True)
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985", "next": "/opendoctor-prontuario.html"})
    assert r.json() == {"ok": True, "redirect": "/opendoctor-prontuario.html"} and confirmou == ["u1"]
    assert "cc" not in _sessao(r) and _sessao(r)["uid"] == "u1"                      # a mesma conta, sem a marca
    assert st["validacoes"] == [("123456", "SP", CPF, "12/05/1985")]
    assert c.get("/cid10?q=diabetes").status_code == 200
    assert TestClient(server.app).post("/auth/crm/confirmar", json={"cpf": CPF}).status_code == 401   # sem sessão


def test_aprovada_a_mao_nao_perde_a_sessao_aberta_quando_a_chave_chega(monkeypatch):
    """A chave do CFM chega no Render com o médico no meio do atendimento: a sessão aberta segue; a confirmação é
    pedida no próximo login."""
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="manual")
    _cfm_simulado(monkeypatch)
    assert c.get("/cid10?q=diabetes").status_code == 200
    assert c.get("/opendoctor-agenda.html", follow_redirects=False).status_code == 200
    assert c.get("/me").json()["bloqueio"] is None


def test_aprovada_a_mao_confirma_ao_entrar(monkeypatch):
    fake = _Fake(_user("ana@clinica.com.br", crm_status="verificado", crm_fonte="manual"))
    c = _client(monkeypatch, fake)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json() == {"ok": True, "redirect": auth.HOME} and "cc" not in _sessao(r)          # sem a chave: nada
    _cfm_simulado(monkeypatch)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json() == {"ok": True, "redirect": auth.HOME, "bloqueio": "crm_confirmar"} and _sessao(r)["cc"] == 1
    fake = _Fake(_user("bia@clinica.com.br", crm_status="verificado", crm_fonte="cfm"))       # conferida no CFM: nada
    c = _client(monkeypatch, fake)
    r = c.post("/auth/password/login", json={"email": "bia@clinica.com.br", "password": PW})
    assert "bloqueio" not in r.json() and "cc" not in _sessao(r)


@pytest.mark.parametrize("codigo", ["3010", "2010", "rede"])
def test_confirmacao_com_o_cfm_sem_responder_deixa_a_sessao_seguir(monkeypatch, codigo):
    """Chave vencida (3010), CFM fora do ar ou sem rede: a conta já foi aprovada à mão, então esta sessão segue sem
    a marca; o pedido volta no próximo login. Só o Validar 'false' mantém o bloqueio. 3010 avisa os administradores."""
    from tests.test_login import _NaHora
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    monkeypatch.setattr(server, "_AUDIT", _NaHora())
    monkeypatch.setattr(server, "_CFM_ALERTA", {"t": 0.0}, raising=False)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    alertas = []
    monkeypatch.setattr(mailer, "send_cfm_alerta", lambda admins: alertas.append(tuple(admins)), raising=False)
    c = _logado(monkeypatch, cc=True, crm_status="verificado", crm_fonte="manual")
    monkeypatch.setattr(db, "get_medico", lambda uid: {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP"})
    confirmou = []
    monkeypatch.setattr(db, "crm_confirmed", lambda uid: confirmou.append(uid) or True)
    _cfm_simulado(monkeypatch, valido={"status": "indisponivel", "codigo": codigo})
    assert c.get("/patients").status_code == 403
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985", "next": "/opendoctor-agenda.html"})
    assert r.status_code == 200 and r.json() == {"ok": True, "redirect": "/opendoctor-agenda.html", "adiado": True}
    assert confirmou == [] and "cc" not in _sessao(r)                   # não confirmou: o próximo login pede de novo
    assert c.get("/cid10?q=diabetes").status_code == 200
    assert alertas == ([("dono@opendoctor.app",)] if codigo == "3010" else [])
    c = _logado(monkeypatch, cc=True, crm_status="verificado", crm_fonte="manual")   # outro 3010 logo depois: 1 aviso só
    c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert len(alertas) == (1 if codigo == "3010" else 0)


def test_confirmacao_nao_usa_o_limite_por_ip_e_limita_por_conta(monkeypatch):
    """Os colegas da mesma clínica (mesmo IP) gastam o limite de cadastros, não o da confirmação; o limite da
    confirmação é por conta e só conta os CPFs/datas que não bateram."""
    fake = _Fake()
    cad = _client(monkeypatch, fake)
    _cfm_simulado(monkeypatch, {"status": "nao_encontrado"})
    monkeypatch.setitem(server.RATE_LIMITS, "login_code", (100, 600))
    for i in range(server.RATE_LIMITS["cfm"][0]):
        cad.post("/auth/signup/start", json=_novo(email=f"colega{i}@clinica.com.br", crm=str(1000 + i)))
    assert cad.post("/auth/signup/start", json=_novo(crm="999")).status_code == 429          # o IP da clínica esgotou
    c = _logado(monkeypatch, cc=True, crm_status="verificado", crm_fonte="manual")
    monkeypatch.setattr(db, "get_medico", lambda uid: {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP"})
    monkeypatch.setattr(db, "crm_confirmed", lambda uid: True)
    st = _cfm_simulado(monkeypatch, valido=False)
    for _ in range(server.CONF_FALHAS[0]):
        assert c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"}).json() == {"error": "crm_dados"}
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.status_code == 429 and r.json() == {"error": "limite_conta"}
    assert len(st["validacoes"]) == server.CONF_FALHAS[0]                     # passou do limite: nem chama o CFM
    assert c.get("/cid10?q=diabetes").status_code == 403                      # e continua pedindo a confirmação
    st = _cfm_simulado(monkeypatch, valido=True)                              # outro dia (contador zerado)
    r = c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.json()["ok"] and "adiado" not in r.json()


def test_confirmar_sem_nada_a_confirmar_nao_chama_o_cfm(monkeypatch):
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="cfm")
    st = _cfm_simulado(monkeypatch)
    assert c.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"}).json()["ok"]
    assert st["validacoes"] == []


# ===================== página de cadastros (administradores) =====================

UID = "8f14e45f-ceea-467a-9575-1a2b3c4d5e6f"


def test_cadastros_so_para_administradores(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    c = _logado(monkeypatch)
    monkeypatch.setattr(db, "pending_doctors", lambda: pytest.fail("não-administrador leu a lista"))
    monkeypatch.setattr(db, "manual_doctors", lambda janela_s: pytest.fail("não-administrador leu a lista"))
    monkeypatch.setattr(db, "decide_crm", lambda uid, ap: pytest.fail("não-administrador decidiu"))
    monkeypatch.setattr(db, "crm_dispensa", lambda uid: pytest.fail("não-administrador liberou"))
    assert c.get("/admin/cadastros").status_code == 403
    assert c.post("/admin/cadastros/aprovar", json={"id": UID}).status_code == 403
    assert c.post("/admin/cadastros/recusar", json={"id": UID}).status_code == 403
    assert c.post("/admin/cadastros/liberar", json={"id": UID}).status_code == 403
    assert TestClient(server.app).post("/admin/cadastros/liberar", json={"id": UID}).status_code == 401
    assert c.get("/opendoctor-cadastros.html", follow_redirects=False).status_code == 200   # a página não tem dado nenhum
    anonimo = TestClient(server.app)
    assert anonimo.get("/admin/cadastros").status_code == 401
    assert anonimo.get("/opendoctor-cadastros.html", follow_redirects=False).status_code == 302
    monkeypatch.setenv("ADMIN_EMAILS", "")
    c = _logado(monkeypatch, email="dono@opendoctor.app")                    # sem ADMIN_EMAILS, ninguém é administrador
    assert c.get("/admin/cadastros").status_code == 403


def test_administrador_aprova_e_recusa(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "outro@x.com, Dono@OpenDoctor.app")
    c = _logado(monkeypatch, email="dono@opendoctor.app")
    lista = [{"id": UID, "name": "Ana Lima", "email": "ana@clinica.com.br", "crm": "123456", "crm_uf": "SP",
              "pedido_em": "2026-10-30T12:00:00+00:00", "situacao": None, "outras_contas": 0}]
    monkeypatch.setattr(db, "pending_doctors", lambda: lista)
    janelas = []
    monkeypatch.setattr(db, "manual_doctors", lambda janela_s: (janelas.append(janela_s), ([], True))[1])
    pendentes, decisoes, enviados = {UID: {"id": UID, "email": "ana@clinica.com.br", "name": "Ana Lima"}}, [], []

    def decide(uid, aprovado):
        decisoes.append((uid, aprovado))
        return pendentes.pop(uid, None)
    monkeypatch.setattr(db, "decide_crm", decide)
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send_crm_decision", lambda to, name="", aprovado=True: enviados.append((to, aprovado)))
    j = c.get("/admin/cadastros").json()
    assert j == {"pendentes": lista, "manuais": [], "dispensa": True, "cfm": False, "limite_falhas": server.CONF_FALHAS[0]}
    assert janelas == [server.CONF_FALHAS[1]]                    # as falhas da confirmação na mesma janela do limite
    assert c.post("/admin/cadastros/aprovar", json={"id": "x"}).json()["error"] == "id_invalido"
    assert c.post("/admin/cadastros/aprovar", content=json.dumps({"id": UID}), headers={"content-type": "text/plain"}).json()["error"] == "id_invalido"
    r = c.post("/admin/cadastros/aprovar", json={"id": UID.upper()})
    assert r.json() == {"ok": True, "email_enviado": True}
    assert decisoes == [(UID, True)] and enviados == [("ana@clinica.com.br", True)]
    r = c.post("/admin/cadastros/recusar", json={"id": UID})                    # já decidido: não muda nem avisa de novo
    assert r.status_code == 409 and r.json()["error"] == "nao_pendente" and len(enviados) == 1
    pendentes[UID] = {"id": UID, "email": "ana@clinica.com.br", "name": "Ana Lima"}
    assert c.post("/admin/cadastros/recusar", json={"id": UID}).json()["ok"]
    assert enviados[-1] == ("ana@clinica.com.br", False)


def test_email_da_decisao_que_falha_nao_desfaz(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    c = _logado(monkeypatch, email="dono@opendoctor.app")
    monkeypatch.setattr(db, "decide_crm", lambda uid, ap: {"id": uid, "email": "ana@clinica.com.br", "name": "Ana"})
    monkeypatch.setattr(mailer, "configured", lambda: True)

    def falha(*a, **k):
        raise RuntimeError("resend 500")
    monkeypatch.setattr(mailer, "send_crm_decision", falha)
    assert c.post("/admin/cadastros/aprovar", json={"id": UID}).json() == {"ok": True, "email_enviado": False}


def _contas_liberaveis(monkeypatch, contas):
    """db.crm_dispensa / manual_doctors em memória, como no banco: só conta aprovada à mão; de novo, não muda nada."""
    feitas = []

    def dispensa(uid):
        u = contas.get(uid)
        feitas.append(uid)
        if not u or u.get("crm_status") != "verificado" or u.get("crm_fonte") != "manual":
            return None
        u.setdefault("crm_dispensado", True)
        return {"id": uid, "email": u["email"], "name": u["name"]}
    monkeypatch.setattr(db, "crm_dispensa", dispensa)
    monkeypatch.setattr(db, "manual_doctors", lambda janela_s: ([
        {"id": k, "name": u["name"], "email": u["email"], "crm": "123456", "crm_uf": "SP",
         "aprovado_em": "2026-10-30T12:00:00+00:00", "falhas": 5}
        for k, u in contas.items() if u.get("crm_fonte") == "manual" and not u.get("crm_dispensado")], True))
    return feitas


def test_administrador_libera_aprovada_a_mao_presa_na_confirmacao(monkeypatch):
    """O Validar insiste em "false" (aprovada com o CRM errado, cadastro do CFM divergente) e o médico ficou preso no
    "Confirme seu registro": o administrador libera sem confirmar. A sessão que estava barrada passa a usar o app, o
    próximo login não pede mais a confirmação, e liberar de novo não muda nada."""
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    medica = {"id": UID, "email": "ana@clinica.com.br", "name": "Ana Lima", "sv": 0, "crm_status": "verificado",
              "crm_fonte": "manual"}
    contas = {UID: medica, "9a14e45f-ceea-467a-9575-1a2b3c4d5e70": {"email": "bia@x.com", "name": "Bia", "crm_status": "verificado",
                                                                    "crm_fonte": "cfm"}}
    feitas = _contas_liberaveis(monkeypatch, contas)
    monkeypatch.setattr(db, "pending_doctors", lambda: [])
    _cfm_simulado(monkeypatch, valido=False)
    # a sessão da médica, que nasceu pedindo a confirmação, e a do administrador
    monkeypatch.setattr(db, "get_user", lambda uid: dict(medica) if uid == UID else (
        {"id": "adm", "email": "dono@opendoctor.app", "name": "Dono", "sv": 0, "crm_status": None} if uid == "adm" else None))
    doc, adm = TestClient(server.app), TestClient(server.app)
    doc.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": UID, "sv": 0, "cc": 1}))
    adm.cookies.set(auth.COOKIE_NAME, auth.sign({"k": "sess", "uid": "adm", "sv": 0}))
    assert doc.get("/cid10?q=diabetes").json() == {"error": "crm_confirmar"}
    j = adm.get("/admin/cadastros").json()
    assert [(m["id"], m["email"], m["falhas"]) for m in j["manuais"]] == [(UID, "ana@clinica.com.br", 5)] and j["dispensa"]
    assert doc.post("/admin/cadastros/liberar", json={"id": UID}).status_code == 403          # o médico não se libera
    assert adm.post("/admin/cadastros/liberar", json={"id": "x"}).json()["error"] == "id_invalido"
    assert adm.post("/admin/cadastros/liberar", content=json.dumps({"id": UID}),
                    headers={"content-type": "text/plain"}).json()["error"] == "id_invalido"      # só JSON
    assert feitas == []
    r = adm.post("/admin/cadastros/liberar", json={"id": UID.upper()})
    assert r.status_code == 200 and r.json() == {"ok": True} and medica["crm_dispensado"] is True
    assert adm.post("/admin/cadastros/liberar", json={"id": UID}).json() == {"ok": True}     # de novo: nada muda
    assert adm.get("/admin/cadastros").json()["manuais"] == []
    # a sessão barrada passa a usar o app, sem a confirmação e sem chamar o CFM
    assert doc.get("/cid10?q=diabetes").status_code == 200
    assert doc.get("/me").json()["bloqueio"] is None and "crm_dispensado" not in doc.get("/me").json()["user"]
    r = doc.post("/auth/crm/confirmar", json={"cpf": CPF, "nascimento": "12/05/1985"})
    assert r.json() == {"ok": True, "redirect": auth.HOME}
    # só conta aprovada à mão: conferida no CFM, pendente, recusada ou inexistente → 409, sem mudar nada
    r = adm.post("/admin/cadastros/liberar", json={"id": "9a14e45f-ceea-467a-9575-1a2b3c4d5e70"})
    assert r.status_code == 409 and r.json()["error"] == "nao_manual" and "crm_dispensado" not in contas["9a14e45f-ceea-467a-9575-1a2b3c4d5e70"]
    assert adm.post("/admin/cadastros/liberar", json={"id": "1a14e45f-ceea-467a-9575-1a2b3c4d5e70"}).status_code == 409


def test_liberada_sem_confirmar_entra_sem_o_pedido(monkeypatch):
    """Com a chave do CFM, a aprovada à mão liberada pelo administrador entra pela senha ou pelo Google sem a marca de
    confirmar (o pedido nunca mais aparece); a que não foi liberada continua sendo pedida."""
    fake = _Fake(_user("ana@clinica.com.br", crm_status="verificado", crm_fonte="manual", crm_dispensado=True))
    c = _client(monkeypatch, fake)
    info = db.password_login_info

    def com_dispensa(e):
        i = info(e)
        return i and dict(i, crm_dispensado=fake.users[e].get("crm_dispensado", False))
    monkeypatch.setattr(db, "password_login_info", com_dispensa)
    _cfm_simulado(monkeypatch)
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json() == {"ok": True, "redirect": auth.HOME} and "cc" not in _sessao(r)
    fake.users["ana@clinica.com.br"]["crm_dispensado"] = False
    r = c.post("/auth/password/login", json={"email": "ana@clinica.com.br", "password": PW})
    assert r.json()["bloqueio"] == "crm_confirmar" and _sessao(r)["cc"] == 1
    # pelo Google (conta que já existe): a mesma regra
    fake = _Fake()
    c = _client(monkeypatch, fake)
    _google(monkeypatch, fake, existe=True)
    fake.users["nova@clinica.com.br"].update(crm_status="verificado", crm_fonte="manual", crm_dispensado=True)
    assert "cc" not in _sessao(_volta_do_google(c))
    fake.users["nova@clinica.com.br"]["crm_dispensado"] = False
    assert _sessao(_volta_do_google(c))["cc"] == 1


def test_liberar_sem_a_migracao_0019_avisa_e_nao_muda_nada(monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "dono@opendoctor.app")
    c = _logado(monkeypatch, email="dono@opendoctor.app")

    def sem_coluna(uid):
        raise db.MigracaoPendente("0019_crm_dispensado.sql")
    monkeypatch.setattr(db, "crm_dispensa", sem_coluna)
    r = c.post("/admin/cadastros/liberar", json={"id": UID})
    assert r.status_code == 503 and r.json() == {"error": "migracao_pendente"}


class _Conn:
    """Conexão falsa: responde à sondagem da coluna crm_dispensado_em (0019) e guarda o SQL de cada consulta."""
    def __init__(self, tem):
        self.tem, self.sql = tem, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        return self

    def commit(self):
        pass

    def execute(self, sql, params=None):
        self.sql.append(sql)
        extra = (True,) if "crm_dispensado_em" in sql else ()
        if "pg_attribute" in sql:
            self._row = (self.tem,)
        elif "password_hash" in sql:                                     # db.password_login_info
            self._row = ("u1", "hash", 0, 0, "verificado", "manual") + extra
        else:                                                            # as colunas do usuário (_USER_COLS)
            self._row = ("u1", "a@b.com", "Ana", None, 0, "verificado", "manual") + extra
        return self

    def fetchone(self):
        return self._row


def test_sem_a_migracao_0019_o_login_segue_como_antes(monkeypatch):
    """Publicado antes da migração 0019: as consultas do usuário não pedem a coluna nova (ninguém fica sem entrar) e
    ninguém está liberado; depois de aplicada, o servidor vê a coluna sozinho (confere de novo a cada minuto)."""
    conn = _Conn(False)
    monkeypatch.setattr(db, "connection", lambda: conn)
    monkeypatch.setattr(db, "_DISPENSA", {"ok": None, "t": 0.0})
    u = db.get_user("u1")
    assert u["crm_dispensado"] is False and not any("crm_dispensado_em" in s for s in conn.sql if "pg_attribute" not in s)
    assert db.password_login_info("a@b.com")["crm_dispensado"] is False
    with pytest.raises(db.MigracaoPendente):
        db.crm_dispensa(UID)
    sondagens = sum("pg_attribute" in s for s in conn.sql)
    db.get_user("u1")
    assert sum("pg_attribute" in s for s in conn.sql) == sondagens         # dentro do minuto: não pergunta de novo
    conn.tem = True                                                          # o dono aplicou a 0019
    db._DISPENSA["t"] -= db.DISPENSA_RECHECA_S + 1
    assert db.get_user("u1")["crm_dispensado"] is True and "crm_dispensado_em" in conn.sql[-1]
    n = len(conn.sql)
    db.get_user("u1")
    assert len(conn.sql) == n + 1                                            # "sim" fica guardado: sem sondagem


# ===================== CRM conferido não muda em Configurações =====================

def test_crm_conferido_nao_muda_em_configuracoes(monkeypatch):
    medico = {"name": "Ana Lima", "crm": "123456", "crm_uf": "SP", "especialidade": None, "consultorio_endereco": None,
              "consultorio_telefone": None, "receita_papel": None}
    monkeypatch.setattr(db, "get_medico", lambda uid: dict(medico))
    monkeypatch.setattr(db, "update_medico", lambda uid, campos: medico.update(campos) or dict(medico))
    c = _logado(monkeypatch, crm_status="verificado", crm_fonte="cfm")
    assert c.get("/me/medico").json()["crm_conferido"] is True
    r = c.patch("/me/medico", json={"crm": "999999"})
    assert r.status_code == 400 and medico["crm"] == "123456"
    assert c.patch("/me/medico", json={"crm_uf": "RJ"}).status_code == 400
    assert c.patch("/me/medico", json={"crm": "123456", "especialidade": "Cardiologia"}).status_code == 200
    assert medico["especialidade"] == "Cardiologia"
    c = _logado(monkeypatch)                                                    # conta antiga: edita como sempre
    assert c.get("/me/medico").json()["crm_conferido"] is False
    assert c.patch("/me/medico", json={"crm": "777"}).status_code == 200 and medico["crm"] == "777"
