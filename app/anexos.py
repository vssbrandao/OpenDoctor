"""Anexos do assistente (o "+" do campo do New chat e do assistente ao lado do prontuário).

Decisão do usuário (16/11/2026): a IMAGEM (PNG, JPEG, WebP) vai inteira ao modelo (pode conter o nome: exceção aprovada à
regra 3 do CLAUDE.md); o PDF vai só como TEXTO extraído e mascarado (scribe.mask + os nomes achados no laudo, veja
"máscara" abaixo). Nada é guardado: nem banco, nem disco, nem log (o chamador só registra contagens). O nome do arquivo
nem chega ao servidor. O texto do PDF é extraído em um processo separado, com teto de tempo e memória (app/pdf_texto.py).

prepara(lista, nome_paciente) → {"imagens": [data_url...], "pdfs": [texto...], "kb_img": int, "kb_pdf": int}
ou levanta ErroAnexo(codigo), com codigo em: anexos_demais, anexo_tipo, anexo_grande, anexo_invalido, pdf_sem_texto.
"""
import base64
import binascii
import re
import unicodedata

from . import pdf_texto, scribe

MAX_ANEXOS = 4
MAX_IMG = 5 * 1024 * 1024          # bytes decodificados, por imagem
MAX_PDF = 10 * 1024 * 1024         # por PDF
MAX_TOTAL = 15 * 1024 * 1024       # soma de todos
PDF_PAGINAS = pdf_texto.PDF_PAGINAS   # só as primeiras páginas são lidas
PDF_CHARS = pdf_texto.PDF_CHARS       # e só os primeiros caracteres de cada PDF vão ao modelo
MIN_UTEIS = 20                     # menos que isso de letras/dígitos: PDF sem texto (escaneado)

IMAGENS = ("image/png", "image/jpeg", "image/webp")
PDF = "application/pdf"
LIMITE = {"image/png": MAX_IMG, "image/jpeg": MAX_IMG, "image/webp": MAX_IMG, PDF: MAX_PDF}


class ErroAnexo(Exception):
    def __init__(self, codigo):
        super().__init__(codigo)
        self.codigo = codigo


def _bate(tipo, b):
    """Os primeiros bytes conferem com o tipo declarado?"""
    if tipo == "image/png":
        return b.startswith(b"\x89PNG")
    if tipo == "image/jpeg":
        return b.startswith(b"\xff\xd8\xff")
    if tipo == "image/webp":
        return len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP"
    if tipo == PDF:
        return b.startswith(b"%PDF-")
    return False


# ===== máscara do texto do PDF =====
# Na dúvida, mascara (é dado de saúde). Mesmo sem paciente escolhido, o nome é achado por estes caminhos:
#  1) campo rotulado: "Nome:", "Nome do paciente:", "Paciente -", "Pac.:", "Paciente........: X", "Nome : X"; o valor na
#     linha de baixo quando o rótulo fica sozinho ("Paciente:\nMARIA DA SILVA"); o nome quebrado em duas linhas
#     ("MARIA DA SILVA\nSANTOS OLIVEIRA   Idade: 45") e o valor com idade ("Maria da Silva, 45 anos");
#  2) tratamento: "Sr(a). João Pereira", "Sra. Maria", "Sr. Fulano" (nunca "Dr./Dra.": é o médico);
#  3) frases de laudo/atestado: "Exame de: X", "Laudo de X", "Atesto para os devidos fins que X";
#  4) cabeçalho: nome em caixa alta sem rótulo nas 3 primeiras linhas não vazias;
#  5) depois, cada nome achado é procurado no resto do texto (scribe.mask), junto com o do paciente escolhido.
_ROTULO = re.compile(
    r"(?<![\wÀ-ÿ])(?:nome(?:\s+(?:d[oa]s?\s+)?(?:paciente|completo|social|civil|m[ãa]e|pai|respons[áa]vel|cliente|"
    r"usu[áa]ri[oa]|benefici[áa]ri[oa]|titular))?|paciente|pac\.?|cliente|respons[áa]vel|benefici[áa]ri[oa]|"
    r"usu[áa]ri[oa]|titular)(?:[ \t]*\.*[ \t]*:[ \t]*|[ \t]*[-–][ \t]+)",
    re.IGNORECASE)
# onde o valor do nome acaba: espaço duplo, tabulação, separador ou o próximo rótulo comum ("Idade:", "DN:", "CPF:"...)
_FIM_VALOR = re.compile(
    r"[ \t]{2,}|\t|[ \t][|;][ \t]?|[ \t]+(?=(?:idade|sexo|data|dn|d\.n\.|nasc|nascimento|cpf|rg|cns|cart[ãa]o|"
    r"prontu[áa]rio|registro|conv[êe]nio|plano|leito|quarto|setor|m[ée]dic[oa]|solicitante|dr|dra|crm|telefone|tel|"
    r"fone|celular|e-?mail|endere[çc]o|atendimento|exame|material|coleta|peso|altura|matr[íi]cula|carteirinha|"
    r"protocolo|pedido|unidade|origem|g[êe]nero)\b[^\n:]{0,25}:)",
    re.IGNORECASE)
# "Maria da Silva", "JOÃO PEREIRA", "José de Souza e Silva": palavras com maiúscula, partículas no meio
_PAL = r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ']+"
_NOME_SEQ = _PAL + r"(?:[ \t]+(?:(?:d[aeo]s?|e|D[AEO]S?|E)[ \t]+)?" + _PAL + r"){0,7}"
_TRATA = re.compile(r"(?<![\wÀ-ÿ])(?i:sr\(a\)|sra|srta|sr|senhora|senhor)\.?(?:[ \t]*:)?[ \t]+(" + _NOME_SEQ + ")")
_FRASE = re.compile(
    r"(?<![\wÀ-ÿ])(?i:(?:exames?|laudos?|resultados?|relat[óo]rios?)[ \t]+(?:de|do|da)(?:[ \t]*:)?"
    r"|atesto(?:[ \t]+para[ \t]+os[ \t]+devidos[ \t]+fins)?,?[ \t]+que(?:[ \t]+(?:o\(a\)|a\(o\)|o|a))?)"
    r"(?:[ \t]+(?i:sr\(a\)|sra|srta|sr|senhora|senhor)\.?)?"       # "Atesto que o(a) Sr(a). X": o tratamento não é nome
    r"[ \t]+(" + _NOME_SEQ + ")")
# palavras de laudo/cabeçalho (sem acento, em maiúsculas): uma linha com elas não é nome
_TERMOS = set("""HEMOGRAMA COMPLETO LAUDO LAUDOS EXAME EXAMES RESULTADO RESULTADOS LABORATORIO LABORATORIOS CLINICA
CLINICAS HOSPITAL HOSPITALAR RELATORIO RECEITA RECEITUARIO ATESTADO BIOQUIMICA URINA SANGUE IMAGEM IMAGENS
ULTRASSONOGRAFIA ULTRASSOM TOMOGRAFIA RESSONANCIA RAIO RAIOS LTDA SA MEDICINA MEDICO MEDICA DIAGNOSTICO DIAGNOSTICOS
ANALISES ANALISE SAUDE CENTRO UNIDADE DATA PAGINA PAG RESUMO ALTA EVOLUCAO PRESCRICAO PEDIDO SOLICITACAO GUIA
CONCLUSAO IMPRESSAO TECNICA METODO MATERIAL COLETA REFERENCIA VALORES VALOR SOROLOGIA PERFIL LIPIDICO GLICEMIA
HEMOGLOBINA FERRITINA COLESTEROL TRIGLICERIDES CREATININA UREIA TSH PARCIAL ROTINA CULTURA ANTIBIOGRAMA
ECOCARDIOGRAMA ELETROCARDIOGRAMA MAMOGRAFIA DENSITOMETRIA ENDOSCOPIA COLONOSCOPIA BIOPSIA ANATOMOPATOLOGICO
CITOLOGIA PATOLOGIA RADIOLOGIA CARDIOLOGIA LABORATORIAL INSTITUTO FUNDACAO SECRETARIA MUNICIPAL ESTADUAL SUS
SERVICO SERVICOS ATENDIMENTO AMBULATORIO PRONTO SOCORRO UPA UBS POSTO GRUPO REDE NUCLEO ASSOCIACAO SOCIEDADE
BRASIL BRASILEIRA BRASILEIRO NACIONAL TOTAL FEZES PARASITOLOGICO SUMARIO TIPO ABDOME ABDOMINAL TORAX CRANIO
PELVE PELVICA OBSTETRICA TRANSVAGINAL DOPPLER CONTRASTE SEM COM NORMAL ALTERADO DOCUMENTO CONFIDENCIAL PACIENTE
NOME IDADE SEXO CPF RG LEITO SETOR CONVENIO PLANO PROTOCOLO ORDEM REQUISICAO EMISSAO ASSINATURA CRM HORA""".split())
_PARTIC = {"DA", "DE", "DO", "DOS", "DAS", "E"}
_LETRAS = re.compile(r"[A-ZÀ-ÖØ-Þ']+")
_UTIL = re.compile(r"[0-9A-Za-zÀ-ÿ]")


def _sa(w):
    """Palavra sem acento, em maiúsculas (para comparar com _TERMOS)."""
    return unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode().upper()


def _tem_termo(valor):
    return any(_sa(w) in _TERMOS for w in re.findall(r"[\wÀ-ÿ]+", valor))


def _caixa_alta_nome(valor, minimo=1, maximo=6):
    """Só palavras em caixa alta (≥ 2 letras; DA/DE/DO/DOS/DAS/E no meio), sem dígito, sem ':' e sem palavra de laudo:
    "SANTOS OLIVEIRA", "MARIA DA SILVA"."""
    ws = valor.split()
    if not (minimo <= len(ws) <= maximo) or re.search(r"[\d:]", valor) or _tem_termo(valor):
        return False
    if ws[0] in _PARTIC or ws[-1] in _PARTIC:
        return False
    return all(w in _PARTIC or (len(w) >= 2 and _LETRAS.fullmatch(w)) for w in ws)


def _corta(valor):
    """O nome antes de vírgula, dígito ou "anos": "Maria da Silva, 45 anos" → "Maria da Silva"."""
    m = re.search(r",|\d|(?<![\wÀ-ÿ])anos(?![\wÀ-ÿ])", valor, re.IGNORECASE)
    return (valor[:m.start()] if m else valor).rstrip(" \t.,;-–")


def _valor_da_linha(texto, ini):
    """O valor que começa em ini, até o fim da linha ou até o próximo rótulo."""
    fim_linha = texto.find("\n", ini)
    fim_linha = len(texto) if fim_linha < 0 else fim_linha
    resto = texto[ini:fim_linha]
    c = _FIM_VALOR.search(resto)
    valor = resto[:c.start()] if c else resto
    return valor.rstrip(" \t.,")


def _proxima_linha(texto, pos):
    """(início do texto, quantas quebras de linha foram puladas) da próxima linha não vazia abaixo de pos."""
    quebras, i = 0, pos
    while True:
        nl = texto.find("\n", i)
        if nl < 0:
            return None, 0
        quebras += 1
        ini = nl + 1
        fim = texto.find("\n", ini)
        fim = len(texto) if fim < 0 else fim
        linha = texto[ini:fim]
        if linha.strip():
            return ini + len(linha) - len(linha.lstrip()), quebras
        i = ini


def _continuacao(texto, pos, out):
    """Nome quebrado: a linha logo abaixo, se for só caixa alta ("SANTOS OLIVEIRA   Idade: 45"), continua o nome."""
    ini, quebras = _proxima_linha(texto, pos)
    if ini is None or quebras != 1:
        return
    valor = _valor_da_linha(texto, ini)
    if valor and _caixa_alta_nome(valor, 1, 5):
        out.append((ini, ini + len(valor), valor))


def _nomes_rotulados(texto):
    """[(início, fim, valor)] dos nomes achados (campos rotulados, tratamento, frases de laudo, cabeçalho)."""
    out = []
    for m in _ROTULO.finditer(texto):
        ini = m.end()
        valor = _valor_da_linha(texto, ini)
        if not _UTIL.search(valor):
            # rótulo sozinho na linha: o nome vem na próxima linha não vazia ("Paciente:\nMARIA DA SILVA SANTOS")
            if texto[ini:].lstrip(" \t")[:1] not in ("\n", ""):
                continue
            ini2, _ = _proxima_linha(texto, ini)
            if ini2 is None:
                continue
            v2 = _corta(_valor_da_linha(texto, ini2))
            if v2 and ":" not in v2 and not _tem_termo(v2) and _parece_nome(v2):
                out.append((ini2, ini2 + len(v2), v2))
                _continuacao(texto, ini2, out)
            continue
        if "[PACIENTE]" in valor:
            continue
        nome = _corta(valor)
        if nome and _parece_nome(nome):
            out.append((ini, ini + len(nome), nome))      # ", 45 anos" fica: é dado clínico
            _continuacao(texto, ini, out)
        else:
            out.append((ini, ini + len(valor), valor))    # campo de nome com outra coisa: sai inteiro, na dúvida
    for rx in (_TRATA, _FRASE):
        for m in rx.finditer(texto):
            ws, pos = [], m.start(1)
            for w in re.finditer(r"\S+", m.group(1)):     # para antes da 1ª palavra de laudo ("Exame de Urina")
                if _sa(w.group(0)) in _TERMOS:
                    break
                ws.append(w)
            while ws and ws[-1].group(0).upper() in _PARTIC:
                ws.pop()
            if ws:
                fim = pos + ws[-1].end()
                out.append((pos, fim, texto[pos:fim]))
                _continuacao(texto, pos, out)
    # cabeçalho: nome em caixa alta sem rótulo nas 3 primeiras linhas não vazias
    pos, vistas = 0, 0
    for linha in texto.split("\n"):
        s = linha.strip()
        if s:
            vistas += 1
            if _caixa_alta_nome(s, 2, 6):
                ini = pos + linha.index(s)
                out.append((ini, ini + len(s), s))
            if vistas >= 3:
                break
        pos += len(linha) + 1
    return out


def mascara_pdf(texto, nome_paciente=""):
    """Texto do PDF sem identificação: os nomes achados (acima) → [PACIENTE]; o nome do paciente escolhido e os nomes
    achados (o resto do laudo pode repeti-los) passam por scribe.mask, que também tira CPF, CNS, telefone e e-mail."""
    achados = _nomes_rotulados(texto)
    trechos = []
    for ini, fim, _ in sorted(achados):
        if trechos and ini <= trechos[-1][1]:
            trechos[-1][1] = max(trechos[-1][1], fim)
        else:
            trechos.append([ini, fim])
    for ini, fim in reversed(trechos):
        texto = texto[:ini] + "[PACIENTE]" + texto[fim:]
    texto = scribe.mask(texto, nome_paciente or "")
    for _, _, valor in achados:
        if _parece_nome(valor):        # "Paciente: em jejum de 8h" não apaga "jejum" do resto do laudo
            texto = scribe.mask(texto, valor)
    return texto


def _parece_nome(valor):
    """Palavras com maiúscula (ou tudo maiúsculo), sem dígitos, até 8 palavras: "Maria da Silva", "JOSÉ SANTOS"."""
    ws = valor.split()
    return 0 < len(ws) <= 8 and not re.search(r"\d", valor) and \
        all(w[:1].isupper() or w.lower() in ("de", "da", "do", "das", "dos", "e") for w in ws)


def _texto_pdf(b):
    """Texto do PDF, lido em um processo separado (teto de tempo e de memória: app/pdf_texto.py)."""
    texto = pdf_texto.extrai(b)
    if texto is None:
        raise ErroAnexo("anexo_invalido")
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if len(_UTIL.findall(texto)) < MIN_UTEIS:
        raise ErroAnexo("pdf_sem_texto")
    return texto[:PDF_CHARS]


def prepara(lista, nome_paciente=""):
    """Confere e prepara os anexos. O base64 de cada item sai do pedido assim que é decodificado (a memória do corpo
    não fica presa até o fim da resposta)."""
    if lista is None:
        lista = []
    if not isinstance(lista, list):
        raise ErroAnexo("anexo_invalido")
    if len(lista) > MAX_ANEXOS:
        raise ErroAnexo("anexos_demais")
    decod = []
    total = 0
    for a in lista:
        if not isinstance(a, dict):
            raise ErroAnexo("anexo_invalido")
        tipo, dados = a.get("tipo"), a.pop("dados", None)
        if tipo not in LIMITE:
            raise ErroAnexo("anexo_tipo")
        if not isinstance(dados, str) or not dados:
            raise ErroAnexo("anexo_invalido")
        if len(dados) > (LIMITE[tipo] * 4) // 3 + 4:       # antes de decodificar: não gasta memória à toa
            raise ErroAnexo("anexo_grande")
        try:
            b = base64.b64decode(dados, validate=True)
        except (binascii.Error, ValueError):
            raise ErroAnexo("anexo_invalido")
        del dados
        if not b:
            raise ErroAnexo("anexo_invalido")
        if len(b) > LIMITE[tipo]:
            raise ErroAnexo("anexo_grande")
        total += len(b)
        if total > MAX_TOTAL:
            raise ErroAnexo("anexo_grande")
        if not _bate(tipo, b):
            raise ErroAnexo("anexo_tipo")
        decod.append((tipo, b))
    imagens, pdfs, b_img, b_pdf = [], [], 0, 0
    for i, (tipo, b) in enumerate(decod):
        decod[i] = None                                     # cada arquivo sai da memória depois de usado
        if tipo == PDF:
            pdfs.append(mascara_pdf(_texto_pdf(b), nome_paciente))
            b_pdf += len(b)
        else:
            imagens.append(f"data:{tipo};base64," + base64.b64encode(b).decode("ascii"))
            b_img += len(b)
        del b
    return {"imagens": imagens, "pdfs": pdfs, "kb_img": round(b_img / 1024), "kb_pdf": round(b_pdf / 1024)}
