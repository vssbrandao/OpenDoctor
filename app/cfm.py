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
from xml.parsers import expat
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
_ABREVIADOS = {"jr": "junior", "fo": "filho"}               # Jr. = Júnior; Fº (º vira "o" sem acento) = Filho
_SUFIXOS = {"filho", "junior", "neto", "sobrinho"}
_APOSTROFOS = "'’‘`´ʼ"


def _limpa(nome, apostrofo):
    """Palavras sem acento, em minúsculas, sem conectores nem tratamento. `apostrofo`: o que vira o apóstrofo —
    "" junta ("D'Ávila" → davila) e " " separa ("D'Ávila" → d avila → avila, porque d é conector)."""
    s = unicodedata.normalize("NFC", str(nome or ""))
    s = "".join(apostrofo if c in _APOSTROFOS else c for c in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z]+", " ", s)
    out = [_ABREVIADOS.get(p, p) for p in s.split() if p not in _CONECTORES]
    while out and out[0] in _TITULOS:
        out = out[1:]
    return out


def palavras(nome):
    """Palavras do nome sem acento, em minúsculas, sem conectores (de, da, dos…) nem tratamento (Dr., Dra.); o apóstrofo
    junta ("Sant'Anna" → santanna) e as abreviações viram a palavra inteira (Jr. → junior, Fº → filho)."""
    return _limpa(nome, "")


def nome_confere(digitado, do_cfm):
    """O primeiro nome é o mesmo e o último sobrenome digitado está entre os SOBRENOMES do CFM (não vale repetir o
    primeiro nome: "Ana Ana"). O apóstrofo pode vir junto ou separado (D'Ávila = Davila = Ávila); quando o último é
    um sufixo (Filho, Júnior, Neto, Sobrinho), vale também o sobrenome antes dele."""
    a, b = palavras(digitado), palavras(do_cfm)
    if len(a) < 2 or len(set(a)) < 2 or not b or a[0] != b[0]:
        return False
    a_sep, b_sep = _limpa(digitado, " "), _limpa(do_cfm, " ")
    sobrenomes = set(b[1:]) | set(b_sep[1:])
    candidatos = {a[-1], a_sep[-1] if a_sep else ""}
    if a[-1] in _SUFIXOS and len(a) >= 3:
        candidatos |= {a[-2]} | ({a_sep[-2]} if len(a_sep) >= 3 else set())
    return bool(candidatos & sobrenomes)


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


class _Recusado(Exception):
    """A resposta trouxe DTD ou entidade: o parser para na hora (nada é expandido)."""


def _recusa(*_):
    raise _Recusado()


_BOMS_NAO_UTF8 = (b"\xff\xfe", b"\xfe\xff")              # UTF-16/32: o CFM responde em UTF-8


def ler(xml_bytes):
    """Tags conhecidas da resposta, pelo nome (sem namespace): {tag: texto}, com 'especialidade' em lista.
    Só UTF-8, e o próprio parser recusa DOCTYPE e entidades (em qualquer codificação, não por busca de bytes).
    Levanta ValueError se não for um XML que dê para ler com segurança."""
    if not isinstance(xml_bytes, (bytes, bytearray)) or len(xml_bytes) > MAX_RESPOSTA:
        raise ValueError("resposta fora do formato")
    xml_bytes = bytes(xml_bytes)
    if xml_bytes.lstrip(b"\x00").startswith(_BOMS_NAO_UTF8) or b"\x00" in xml_bytes:
        raise ValueError("resposta fora do formato")
    try:
        texto = xml_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("resposta fora do formato") from e
    decl = re.match(r"\ufeff?\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)", texto)
    if decl and decl.group(1).strip().lower().replace("_", "-") not in ("utf-8", "utf8"):
        raise ValueError("resposta fora do formato")
    p = expat.ParserCreate(encoding="UTF-8", namespace_separator="}")
    p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    p.StartDoctypeDeclHandler = p.EntityDeclHandler = p.UnparsedEntityDeclHandler = _recusa
    p.NotationDeclHandler = p.ExternalEntityRefHandler = _recusa
    out, pilha = {"especialidade": []}, []

    def abre(nome, _attrs):
        pilha.append((str(nome).rsplit("}", 1)[-1], []))

    def texto_(dado):
        if pilha:
            pilha[-1][1].append(dado)

    def fecha(_nome):
        tag, partes = pilha.pop()
        txt = "".join(partes).strip()
        if tag == "especialidade":
            if txt:
                out["especialidade"].append(txt[:200])
        elif tag in _TAGS_MEDICO + ("codigoErro", "resultadoConsulta") and tag not in out:
            out[tag] = txt[:200]
    p.StartElementHandler, p.CharacterDataHandler, p.EndElementHandler = abre, texto_, fecha
    try:
        p.Parse(xml_bytes, True)
    except _Recusado as e:
        raise ValueError("resposta fora do formato") from e
    except expat.ExpatError as e:
        raise ValueError("xml inválido") from e
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
