"""Conferência do CRM no web service oficial do CFM (Conselho Federal de Medicina), manual v3.0 (08/2026).

SOAP 1.1 em https://ws.cfm.org.br:8080/WebServiceConsultaMedicos/ServicoConsultaMedicos (só TLS 1.2), cabeçalho
SOAPAction "" (vazio, obrigatório), namespace http://servico.cfm.org.br/. Duas operações:

  Consultar(crm, uf, chave)                        → dadosMedico: crm, uf, nome, situacao ('A' = regular), ...
  Validar(crm, uf, cpf, dataNascimento, chave)     → resultadoConsulta true | false

Os erros vêm com HTTP 200 e <codigoErro> (sem SOAP Fault): 2010/2030/2040 são passageiros (tenta mais uma vez e,
se repetir, o CFM está indisponível), 3010 chave inválida ou vencida, 4000/4010/4020 pedido inválido, 8101 médico
não encontrado. Campo que falta não vem: tudo é lido pelo nome da tag, e só as tags conhecidas.

A chave (8 caracteres) é a variável de ambiente CFM_CHAVE, contratada pela empresa com o CFM (docs/cadastro-crm.md).
Sem ela, configured() é False e o cadastro fica pendente, aprovado à mão. A chave, o CPF e a data de nascimento
nunca vão para o log nem para uma URL: o log só leva a operação, o código de erro e o tempo.
"""
import os
import re
import ssl
import time
import unicodedata
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import httpx

URL = "https://ws.cfm.org.br:8080/WebServiceConsultaMedicos/ServicoConsultaMedicos"
NS = "http://servico.cfm.org.br/"
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
MAX_RESPOSTA = 64 * 1024                 # a resposta tem poucas tags; maior que isto não é do CFM
PASSAGEIROS = {"2010", "2030", "2040"}   # tenta de novo uma vez
NAO_ENCONTRADO = "8101"
REGULAR = "A"

UFS = ("AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ",
       "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO")

_TAGS_MEDICO = ("crm", "uf", "nome", "situacao", "tipoInscricao", "dataAtualizacao")
_TRANSPORT = None                        # só os testes trocam (respostas prontas, sem rede)


def _chave():
    return os.environ.get("CFM_CHAVE", "").strip().strip("\"'").strip()


def configured():
    """Há chave do CFM? Sem ela, todo cadastro novo fica pendente (aprovação à mão)."""
    return bool(_chave())


# ----- número do CRM e UF digitados -----

_UF_RE = re.compile(r"(?<![A-Z])(" + "|".join(UFS) + r")(?![A-Z])")


def separa_crm(texto, uf=""):
    """('CRM-SP 123.456', '') → ('123456', 'SP'). O CRM vai só com o número: tira a sigla CRM, a UF escrita junto
    (que passa a valer como UF), o sufixo de inscrição provisória ('1234567-P'), o prefixo '52-' com que o RJ mostra os
    números ('52-1234' → '1234') e o prefixo de outras inscrições ('300-EMFE-1234567' → '1234567')."""
    t = unicodedata.normalize("NFKC", str(texto or "")).upper()
    uf = str(uf or "").strip().upper()
    t = t.replace("CRM", " ")
    m = _UF_RE.search(t)
    if m:
        uf = m.group(1)
        t = t[:m.start()] + " " + t[m.end():]
    t = re.sub(r"-\s*P(?![A-Z])", " ", t)                       # provisória: 1234567-P
    m = re.match(r"^\D*\d+\s*-\s*[A-Z]+\s*-\s*(\d[\d.]*)", t)   # 300-EMFE-1234567
    if m:
        t = m.group(1)
    if uf == "RJ":
        t = re.sub(r"^\D*52\s*[-.]\s*(?=\d)", "", t)           # 52-1234 (como o CRM-RJ mostra) → 1234
    return re.sub(r"\D", "", t), uf


def crm_numero(digitos):
    """O número que o CFM aceita (inteiro de 1 a 7 dígitos, sem zeros à esquerda) ou None."""
    d = str(digitos or "")
    if not d.isdigit() or not 1 <= len(d.lstrip("0")) <= 7 or int(d) <= 0:
        return None
    return str(int(d))


# ----- nome digitado x nome no CFM -----

_CONECTORES = {"de", "da", "do", "dos", "das", "e", "d"}
_TITULOS = {"dr", "dra", "doutor", "doutora", "prof", "profa", "professor", "professora"}


def palavras(nome):
    """Palavras do nome sem acento, em minúsculas, sem conectores (de, da, dos…) nem tratamento (Dr., Dra.)."""
    s = unicodedata.normalize("NFKD", str(nome or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z]+", " ", s)
    out = [p for p in s.split() if p not in _CONECTORES]
    while out and out[0] in _TITULOS:
        out = out[1:]
    return out


def nome_confere(digitado, do_cfm):
    """O primeiro nome é o mesmo e o último sobrenome digitado está entre as palavras do nome no CFM."""
    a, b = palavras(digitado), palavras(do_cfm)
    return len(a) >= 2 and bool(b) and a[0] == b[0] and a[-1] in b


# ----- SOAP -----

def _ctx():
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2          # o servidor do CFM só fala TLS 1.2
    return ctx


def _envelope(op, campos):
    corpo = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in campos)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:ser="{NS}"><soapenv:Header/><soapenv:Body>'
            f'<ser:{op}>{corpo}</ser:{op}></soapenv:Body></soapenv:Envelope>')


def _log(op, oque, t0):
    print(f"[cfm] {op} {oque} {round((time.monotonic() - t0) * 1000)} ms", flush=True)


def ler(xml_bytes):
    """Tags conhecidas da resposta, pelo nome (sem namespace): {tag: texto}, com 'especialidade' em lista.
    Levanta ValueError se não for um XML que dê para ler com segurança."""
    if len(xml_bytes) > MAX_RESPOSTA or b"<!DOCTYPE" in xml_bytes.upper() or b"<!ENTITY" in xml_bytes.upper():
        raise ValueError("resposta fora do formato")
    try:
        raiz = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError("xml inválido") from e
    out = {"especialidade": []}
    for el in raiz.iter():
        tag = str(el.tag).rsplit("}", 1)[-1]
        txt = (el.text or "").strip()
        if tag == "especialidade":
            if txt:
                out["especialidade"].append(txt[:200])
        elif tag in _TAGS_MEDICO + ("codigoErro", "resultadoConsulta") and tag not in out:
            out[tag] = txt[:200]
    return out


def _chama(op, campos):
    """POST do envelope; devolve as tags lidas ou None (rede, HTTP ou resposta ilegível)."""
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=TIMEOUT, verify=_ctx(), transport=_TRANSPORT) as c:
            r = c.post(URL, content=_envelope(op, campos).encode("utf-8"),
                       headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": '""'})
    except httpx.HTTPError as e:
        _log(op, "rede " + type(e).__name__, t0)
        return None
    if r.status_code != 200:
        _log(op, f"http {r.status_code}", t0)
        return None
    try:
        x = ler(r.content)
    except ValueError:
        _log(op, "resposta ilegível", t0)
        return None
    _log(op, "erro " + x["codigoErro"] if x.get("codigoErro") else "ok", t0)
    return x


def _com_nova_tentativa(op, campos):
    x = _chama(op, campos)
    if x is not None and x.get("codigoErro") in PASSAGEIROS:
        time.sleep(0.5)
        x = _chama(op, campos)
    return x


def consultar(crm, uf):
    """{'status': 'ok', 'medico': {...}} | {'status': 'nao_encontrado'} | {'status': 'indisponivel', 'codigo': ...}.
    'indisponivel' junta rede, erro passageiro repetido, chave inválida (3010) e pedido recusado (4000/4010/4020):
    nenhum deles diz nada sobre o médico."""
    if not configured():
        return {"status": "indisponivel", "codigo": "sem_chave"}
    x = _com_nova_tentativa("Consultar", (("crm", crm), ("uf", uf), ("chave", _chave())))
    if x is None:
        return {"status": "indisponivel", "codigo": "rede"}
    cod = x.get("codigoErro")
    if cod == NAO_ENCONTRADO:
        return {"status": "nao_encontrado"}
    if cod:
        return {"status": "indisponivel", "codigo": cod}
    if not x.get("nome") or not x.get("situacao"):
        return {"status": "indisponivel", "codigo": "resposta"}
    return {"status": "ok", "medico": {
        "crm": x.get("crm", ""), "uf": x.get("uf", ""), "nome": x["nome"][:70], "situacao": x["situacao"][:1].upper(),
        "tipo": x.get("tipoInscricao", ""), "atualizado": x.get("dataAtualizacao", ""),
        "especialidades": x["especialidade"]}}


def validar(crm, uf, cpf, nascimento):
    """O CPF e a data de nascimento (DD/MM/AAAA) são os do médico deste CRM?
    {'status': 'ok', 'valido': bool} | {'status': 'indisponivel', 'codigo': ...}. O CFM devolve false para qualquer
    divergência (e para chave errada, sem código)."""
    if not configured():
        return {"status": "indisponivel", "codigo": "sem_chave"}
    x = _com_nova_tentativa("Validar", (("crm", crm), ("uf", uf), ("cpf", cpf), ("dataNascimento", nascimento),
                                        ("chave", _chave())))
    if x is None:
        return {"status": "indisponivel", "codigo": "rede"}
    if x.get("codigoErro"):
        return {"status": "indisponivel", "codigo": x["codigoErro"]}
    res = (x.get("resultadoConsulta") or "").lower()
    if res not in ("true", "false"):
        return {"status": "indisponivel", "codigo": "resposta"}
    return {"status": "ok", "valido": res == "true"}
