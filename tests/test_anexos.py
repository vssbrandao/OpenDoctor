"""Anexos do assistente (o "+" do campo): POST /ask com "anexos". A imagem vai inteira ao modelo (image_url na última
mensagem); o PDF vai só como texto extraído e mascarado; nada vai à busca, ao planejamento nem ao log. O PDF é montado
no próprio teste; a busca e o modelo são simulados: nenhum teste gasta crédito nem toca o banco."""
import base64
import json
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from app import anexos, auth, config, db, server

UID = 41
HIT = {"chunk_id": 1, "document_id": 1, "title": "Anemia workup", "url": "https://pmc.example/3",
       "source_type": "pmc", "evidence": "Revisão", "publication_date": None, "section_title": None,
       "text": "Ferritin below 30 suggests iron deficiency.", "score": 0.9, "cosine_sim": 0.9}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 30


def _pdf(linhas):
    """PDF de 1 página com Helvetica, feito à mão (xref com os deslocamentos certos)."""
    corpo = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
        "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for l in linhas) + " ET"
    stream = corpo.encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> "
            b"/Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offs:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


LAUDO = _pdf(["Laboratorio Exemplo", "Paciente: Maria Silva", "CPF: 123.456.789-09",
              "Hemoglobina: 9,8 g/dL", "Ferritina: 12 ng/mL", "Conclusao: Maria Silva com anemia."])


def b64(b):
    return base64.b64encode(b).decode()


def item(tipo, b):
    return {"tipo": tipo, "dados": b64(b)}


# ===== app/anexos.py =====

def test_pdf_feito_a_mao_o_pypdf_extrai():
    from pypdf import PdfReader
    import io
    assert "Hemoglobina: 9,8 g/dL" in PdfReader(io.BytesIO(LAUDO)).pages[0].extract_text()


def test_pdf_vira_texto_mascarado():
    r = anexos.prepara([item("application/pdf", LAUDO)])
    assert r["imagens"] == [] and len(r["pdfs"]) == 1
    t = r["pdfs"][0]
    assert "[PACIENTE]" in t and "Maria" not in t and "Silva" not in t       # o campo e o nome repetido no laudo
    assert "123.456.789-09" not in t and "9,8 g/dL" in t and "Ferritina: 12 ng/mL" in t


@pytest.mark.parametrize("linha", ["Nome: JOSÉ SANTOS", "nome do paciente - José Santos", "Pac.: José Santos",
                                   "Nome social: José Santos", "PACIENTE: José Santos  Idade: 58 anos",
                                   "Paciente: José Santos DN: 01/02/1960"])
def test_campos_de_nome_rotulados(linha):
    t = anexos.mascara_pdf(linha + "\nGlicemia 110 mg/dL")
    assert "José" not in t and "JOSÉ" not in t and "Santos" not in t and "SANTOS" not in t
    assert "[PACIENTE]" in t and "Glicemia 110 mg/dL" in t
    if "Idade" in linha:
        assert "Idade: 58 anos" in t
    if "DN" in linha:
        assert "DN: 01/02/1960" in t


def test_nome_do_paciente_escolhido_tambem_sai():
    t = anexos.mascara_pdf("Evolução: Joana refere cansaço.", "Joana Prado")
    assert "Joana" not in t and "cansaço" in t


def test_imagem_vai_como_data_url():
    r = anexos.prepara([item("image/png", PNG), item("image/jpeg", JPEG), item("image/webp", WEBP)])
    assert r["pdfs"] == [] and [u.split(";")[0] for u in r["imagens"]] == ["data:image/png", "data:image/jpeg",
                                                                          "data:image/webp"]
    assert r["imagens"][0] == "data:image/png;base64," + b64(PNG)


@pytest.mark.parametrize("lista,codigo", [
    ([item("image/png", PNG)] * 5, "anexos_demais"),
    ([item("image/gif", b"GIF89a" + b"\x00" * 10)], "anexo_tipo"),
    ([{"tipo": "text/plain", "dados": b64(b"oi")}], "anexo_tipo"),
    ([item("image/png", JPEG)], "anexo_tipo"),                         # bytes não batem com o tipo
    ([item("image/webp", b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 10)], "anexo_tipo"),
    ([item("application/pdf", PNG)], "anexo_tipo"),
    ([{"tipo": "image/png", "dados": "isto não é base64!"}], "anexo_invalido"),
    ([{"tipo": "image/png", "dados": "data:image/png;base64," + b64(PNG)}], "anexo_invalido"),
    ([{"tipo": "image/png", "dados": ""}], "anexo_invalido"),
    (["x"], "anexo_invalido"),
    ("x", "anexo_invalido"),
    ([item("image/png", PNG + b"\x00" * (5 * 1024 * 1024))], "anexo_grande"),
    ([item("application/pdf", b"%PDF-" + b"\x00" * (10 * 1024 * 1024))], "anexo_grande"),
    ([item("image/png", PNG + b"\x00" * (4 * 1024 * 1024)) for _ in range(4)], "anexo_grande"),   # 4 × 4 MB > 15 MB
    ([item("application/pdf", b"%PDF-1.4\nlixo sem estrutura")], "anexo_invalido"),
    ([item("application/pdf", _pdf([" "]))], "pdf_sem_texto"),
])
def test_erros(lista, codigo):
    with pytest.raises(anexos.ErroAnexo) as e:
        anexos.prepara(lista)
    assert e.value.codigo == codigo


def test_pdf_criptografado_com_senha_e_invalido():
    from pypdf import PdfReader, PdfWriter
    import io
    w = PdfWriter()
    w.append(PdfReader(io.BytesIO(LAUDO)))
    w.encrypt("segredo", algorithm="RC4-128")
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(anexos.ErroAnexo) as e:
        anexos.prepara([item("application/pdf", buf.getvalue())])
    assert e.value.codigo == "anexo_invalido"


# ===== POST /ask =====

@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": UID, "email": "medica@exemplo.com", "sv": 0})
    vistos = {"plan": [], "search": [], "modelo": [], "medical": True}

    def plan(q, h):
        vistos["plan"].append((q, h))
        return {"medical": vistos["medical"], "standalone": q, "question_en": q, "terms_en": "anemia ferritin"}
    monkeypatch.setattr(server, "_plan", plan)

    def busca(q, k=6, fts_query=None):
        vistos["search"].append((q, fts_query))
        return {"insufficient": False, "best_sim": 0.9, "hits": [dict(HIT)], "qvec": None}
    monkeypatch.setattr(server.search, "search", busca)
    monkeypatch.setattr(server.search, "br_guidelines", lambda q, **kw: [])
    monkeypatch.setattr(server.tools, "renal_note", lambda q: None)

    def modelo(msgs, **kw):
        vistos["modelo"].append(msgs)
        yield "A ferritina de 12 ng/mL e a hemoglobina de 9,8 g/dL indicam anemia ferropriva [1]. "
    monkeypatch.setattr(server.llm, "stream_chat", modelo)
    server._RL.clear()
    c = TestClient(server.app)
    c.vistos = vistos
    return c


def _frases(r):
    return [json.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]


def test_pdf_chega_ao_modelo_mascarado_e_nao_vai_a_busca(cli, capsys):
    r = cli.post("/ask", json={"query": "O que este exame sugere?", "anexos": [item("application/pdf", LAUDO)]})
    assert r.status_code == 200
    ultima = cli.vistos["modelo"][0][-1]["content"]
    assert isinstance(ultima, str)                                      # sem imagem: content continua string
    assert "Anexos do médico nesta pergunta" in ultima and "PDF 1:" in ultima
    assert "[PACIENTE]" in ultima and "Ferritina: 12 ng/mL" in ultima
    tudo = json.dumps(cli.vistos, ensure_ascii=False)
    assert "Maria" not in tudo and "123.456.789-09" not in tudo
    assert "Ferritina" not in json.dumps(cli.vistos["search"] + cli.vistos["plan"], ensure_ascii=False)
    # o número do laudo é dado do próprio médico: não vira "sem fonte"
    fim = [e for e in _frases(r) if "ungrounded" in e][0]
    assert fim["ungrounded"] == 0
    out = capsys.readouterr().out
    assert "anexos img= 0 pdf= 1" in out
    assert "Maria" not in out and "Ferritina" not in out and "Hemoglobina" not in out and b64(LAUDO)[:20] not in out


def test_imagem_vai_como_image_url_na_ultima_mensagem(cli, capsys):
    r = cli.post("/ask", json={"query": "", "anexos": [item("image/png", PNG)],
                               "history": [{"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá"}]})
    assert r.status_code == 200
    msgs = cli.vistos["modelo"][0]
    c = msgs[-1]["content"]
    assert isinstance(c, list) and c[0]["type"] == "text"
    assert "Pergunta do médico: Analise o anexo." in c[0]["text"]
    assert "1 imagem(ns) anexada(s) pelo médico (abaixo)" in c[0]["text"]
    assert c[1] == {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64(PNG)}}
    assert all(isinstance(m["content"], str) for m in msgs[:-1])         # só a última leva a imagem
    assert "base64" not in json.dumps(cli.vistos["search"] + cli.vistos["plan"])
    assert "base64" not in capsys.readouterr().out


def test_varios_anexos_query_vazia(cli):
    r = cli.post("/ask", json={"anexos": [item("image/jpeg", JPEG), item("application/pdf", LAUDO)]})
    assert r.status_code == 200
    c = cli.vistos["modelo"][0][-1]["content"]
    assert "Pergunta do médico: Analise os anexos." in c[0]["text"]


def test_com_anexo_nao_recusa_por_fora_de_escopo(cli):
    cli.vistos["medical"] = False
    r = cli.post("/ask", json={"query": "Analise", "anexos": [item("image/png", PNG)]})
    assert '"out_of_scope"' not in r.text and cli.vistos["modelo"]
    cli.vistos["modelo"].clear()
    r = cli.post("/ask", json={"query": "Quem ganhou o jogo?"})
    assert '"out_of_scope": true' in r.text and cli.vistos["modelo"] == []


@pytest.mark.parametrize("anx,codigo", [
    ([item("image/png", PNG)] * 5, "anexos_demais"),
    ([item("image/png", JPEG)], "anexo_tipo"),
    ([{"tipo": "image/png", "dados": "%%%"}], "anexo_invalido"),
    ([item("application/pdf", _pdf([""]))], "pdf_sem_texto"),
])
def test_erros_no_ask_antes_do_streaming(cli, anx, codigo):
    r = cli.post("/ask", json={"query": "x", "anexos": anx})
    assert r.status_code == 400 and r.json() == {"error": codigo}
    assert cli.vistos["modelo"] == [] and cli.vistos["plan"] == []


def test_corpo_grande_demais(cli):
    grande = "A" * (server.MAX_ASK_BODY + 10)
    r = cli.post("/ask", content=json.dumps({"query": "x", "anexos": [{"tipo": "image/png", "dados": grande}]}),
                 headers={"content-type": "application/json"})
    assert r.status_code == 400 and r.json() == {"error": "anexo_grande"}


def test_sem_anexos_nada_muda(cli):
    r = cli.post("/ask", json={"query": "dose de amoxicilina"})
    assert r.status_code == 200
    msgs = cli.vistos["modelo"][0]
    assert isinstance(msgs[-1]["content"], str) and "Anexos do médico" not in msgs[-1]["content"]
    assert cli.post("/ask", json={"query": ""}).status_code == 400
    assert cli.post("/ask", json={"query": "", "anexos": []}).status_code == 400


def test_com_paciente_o_nome_dele_sai_do_pdf(cli, monkeypatch):
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_ALL", False)
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    p = {"id": 7, "key": "joana prado", "name": "Joana Prado", "birth_date": "1970-01-01", "sex": "F",
         "problems": "", "allergies": "", "medications": ""}
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict(p) if uid == UID and pid == 7 else None)
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: [])
    monkeypatch.setattr(db, "list_receitas", lambda uid, pid: [])
    monkeypatch.setattr(db, "log_access", lambda *a, **k: None)
    pdf = _pdf(["Resumo de alta", "Joana evoluiu bem, sem febre.", "Hemoglobina 11,2 g/dL"])
    r = cli.post("/ask", json={"query": "", "patient_id": 7, "anexos": [item("application/pdf", pdf)]})
    assert r.status_code == 200
    tudo = json.dumps(cli.vistos["modelo"], ensure_ascii=False)
    assert "Joana" not in tudo and "Hemoglobina 11,2 g/dL" in tudo


# ===== máscara sem paciente escolhido: os formatos que escapavam (revisão de 16/11/2026) =====

def _sem(t, nomes):
    for w in nomes.split():
        assert w not in t and w.upper() not in t, (w, t)
    assert "[PACIENTE]" in t


def test_rotulo_com_o_nome_na_linha_de_baixo():
    t = anexos.mascara_pdf("Paciente:\nMARIA DA SILVA SANTOS\nIdade: 45\nGlicemia 110 mg/dL")
    _sem(t, "MARIA SILVA SANTOS")
    assert "Idade: 45" in t and "Glicemia 110 mg/dL" in t


@pytest.mark.parametrize("linha,nome", [("Paciente : MARIA", "MARIA"), ("Paciente........: MARIA", "MARIA"),
                                        ("Nome : Joao Souza", "Joao Souza"), ("Nome ...: Joao Souza", "Joao Souza")])
def test_espaco_e_pontos_antes_dos_dois_pontos(linha, nome):
    t = anexos.mascara_pdf(linha + "\nGlicemia 110 mg/dL")
    _sem(t, nome)
    assert "Glicemia 110 mg/dL" in t


@pytest.mark.parametrize("linha,nome", [("Sr(a). João Pereira compareceu", "João Pereira"),
                                        ("Sra. Maria da Silva refere dor", "Maria Silva"),
                                        ("Sr. Fulano em acompanhamento", "Fulano")])
def test_tratamento_sem_dois_pontos(linha, nome):
    t = anexos.mascara_pdf(linha + "\nPressão 120x80")
    _sem(t, nome)
    assert "Pressão 120x80" in t


def test_dr_e_dra_nao_sao_o_paciente():
    t = anexos.mascara_pdf("Hemoglobina 12 g/dL\nSolicitante: Dra. Ana Costa CRM 1234\nDr. Paulo Mendes")
    assert "Ana" in t and "Paulo Mendes" in t and "Hemoglobina 12 g/dL" in t


def test_nome_quebrado_em_duas_linhas():
    t = anexos.mascara_pdf("Paciente: MARIA DA SILVA\nSANTOS OLIVEIRA   Idade: 45\nHEMOGRAMA COMPLETO\nHemoglobina 9,8")
    _sem(t, "MARIA SILVA SANTOS OLIVEIRA")
    assert "Idade: 45" in t and "HEMOGRAMA COMPLETO" in t and "Hemoglobina 9,8" in t


def test_linha_de_exame_nao_continua_o_nome():
    t = anexos.mascara_pdf("Paciente: MARIA DA SILVA\nHEMOGRAMA COMPLETO\nHemoglobina 9,8")
    assert "HEMOGRAMA COMPLETO" in t and "MARIA" not in t


def test_valor_com_idade_e_virgula():
    t = anexos.mascara_pdf("Paciente: Maria da Silva, 45 anos\nConclusão: Maria da Silva com anemia.")
    _sem(t, "Maria Silva")
    assert "45 anos" in t and "anemia" in t


@pytest.mark.parametrize("linha,nome", [
    ("Exame de: João Pereira", "João Pereira"),
    ("Laudo de João Pereira", "João Pereira"),
    ("Atesto que o(a) Sr(a). João Pereira esteve em consulta", "João Pereira"),
    ("Atesto para os devidos fins que MARIA DA SILVA esteve em consulta", "MARIA SILVA"),
    ("Atesto que Maria da Silva esteve em consulta", "Maria Silva"),
])
def test_frases_de_laudo_e_atestado(linha, nome):
    t = anexos.mascara_pdf("Documento\n\n" + linha + "\nCID J11")
    _sem(t, nome)
    assert "CID J11" in t and "[PACIENTE](" not in t      # o "Sr(a)." não é tomado por nome


def test_exame_de_urina_nao_e_nome():
    t = anexos.mascara_pdf("Exame de Urina tipo I\nLeucócitos 5 p/c")
    assert "Urina" in t


@pytest.mark.parametrize("cabeca,nome", [
    (["MARIA DA SILVA SANTOS", "HEMOGRAMA COMPLETO"], "MARIA SILVA SANTOS"),
    (["LABORATÓRIO EXEMPLO LTDA", "JOÃO PEREIRA", "Data: 10/11/2026"], "JOÃO PEREIRA"),
    (["CLÍNICA SAÚDE", "RESULTADO DE EXAME", "JOSÉ E SOUZA"], "JOSÉ SOUZA"),
])
def test_nome_em_caixa_alta_no_cabecalho(cabeca, nome):
    t = anexos.mascara_pdf("\n".join(cabeca) + "\nHemoglobina 9,8 g/dL\nJOÃO PEREIRA retorna em 30 dias")
    _sem(t, nome)
    assert "Hemoglobina 9,8 g/dL" in t
    for c in cabeca:
        if not set(c.split()) & set(nome.split()):
            assert c in t                                  # o nome do laboratório e o título do exame ficam


def test_cabecalho_so_nas_tres_primeiras_linhas():
    t = anexos.mascara_pdf("Laudo\nHemoglobina 9,8\nFerritina 12\nVALORES DE REFERENCIA\nTGO TGP NORMAIS")
    assert "TGO TGP NORMAIS" in t


def test_formatos_novos_tambem_saem_do_pdf_inteiro():
    pdf = _pdf(["MARIA DA SILVA SANTOS", "Paciente:", "MARIA DA SILVA SANTOS", "Idade: 45",
                "Hemoglobina: 9,8 g/dL", "Sra. Maria da Silva Santos deve repetir em 30 dias."])
    t = anexos.prepara([item("application/pdf", pdf)])["pdfs"][0]
    assert "Maria" not in t and "MARIA" not in t and "Santos" not in t and "9,8 g/dL" in t


# ===== leitura do PDF em processo separado =====

def test_pdf_e_lido_em_outro_processo(monkeypatch):
    from app import pdf_texto
    chamadas = []
    monkeypatch.setattr(pdf_texto, "extrai", lambda b: chamadas.append(len(b)) or None)
    with pytest.raises(anexos.ErroAnexo) as e:
        anexos.prepara([item("application/pdf", LAUDO)])
    assert e.value.codigo == "anexo_invalido" and chamadas == [len(LAUDO)]


def test_filho_que_trava_e_morto_no_tempo():
    import multiprocessing
    import time
    from app import pdf_texto
    from tests import fake_anexos
    t0 = time.monotonic()
    assert pdf_texto.extrai(LAUDO, alvo=fake_anexos.trava, timeout=1.5) is None
    assert time.monotonic() - t0 < 10
    assert not [p for p in multiprocessing.active_children() if p.is_alive()]


@pytest.mark.parametrize("nome", ["morre", "lixo"])
def test_filho_que_morre_ou_responde_lixo(nome):
    from app import pdf_texto
    from tests import fake_anexos
    assert pdf_texto.extrai(LAUDO, alvo=getattr(fake_anexos, nome), timeout=10) is None


def test_trava_no_prepara_vira_anexo_invalido(monkeypatch):
    from app import pdf_texto
    from tests import fake_anexos
    real = pdf_texto.extrai
    monkeypatch.setattr(pdf_texto, "extrai", lambda b: real(b, alvo=fake_anexos.trava, timeout=1))
    with pytest.raises(anexos.ErroAnexo) as e:
        anexos.prepara([item("application/pdf", LAUDO)])
    assert e.value.codigo == "anexo_invalido"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RLIMIT_AS só vale no Linux (Render e CI)")
def test_filho_tem_teto_de_memoria():
    from app import pdf_texto
    from tests import fake_anexos
    assert pdf_texto.extrai(LAUDO, alvo=fake_anexos.estoura, timeout=10) is None


def test_so_as_30_primeiras_paginas():
    from pypdf import PdfReader, PdfWriter
    import io
    w = PdfWriter()
    for i in range(1, 36):
        w.append(PdfReader(io.BytesIO(_pdf([f"Pagina numero {i} glicemia"]))))
    buf = io.BytesIO()
    w.write(buf)
    t = anexos.prepara([item("application/pdf", buf.getvalue())])["pdfs"][0]
    assert "Pagina numero 30 glicemia" in t and "Pagina numero 31" not in t


# ===== /ask: vagas para anexos e pergunta só com anexo =====

def test_terceiro_pedido_com_anexo_recebe_ocupado(cli, monkeypatch):
    vagas = threading.BoundedSemaphore(2)
    monkeypatch.setattr(server, "_ANEXO_VAGAS", vagas)
    monkeypatch.setattr(server, "ANEXO_ESPERA", 0.3)
    assert vagas.acquire(blocking=False) and vagas.acquire(blocking=False)      # 2 sendo preparados
    r = cli.post("/ask", json={"query": "x", "anexos": [item("image/png", PNG)]})
    assert r.status_code == 429 and r.json() == {"error": "ocupado"} and cli.vistos["modelo"] == []
    assert cli.post("/ask", json={"query": "dose de amoxicilina"}).status_code == 200   # sem anexo não espera vaga
    vagas.release()
    r = cli.post("/ask", json={"query": "x", "anexos": [item("image/png", PNG)]})
    assert r.status_code == 200
    assert vagas.acquire(blocking=False)                   # a vaga voltou depois do pedido
    vagas.release()
    vagas.release()


def test_vaga_volta_mesmo_com_erro(cli, monkeypatch):
    vagas = threading.BoundedSemaphore(2)
    monkeypatch.setattr(server, "_ANEXO_VAGAS", vagas)
    for _ in range(3):
        assert cli.post("/ask", json={"query": "x", "anexos": [item("image/png", JPEG)]}).status_code == 400

    def explode(lista, nome=""):
        raise RuntimeError("falhou")
    monkeypatch.setattr(anexos, "prepara", explode)
    c = TestClient(server.app, raise_server_exceptions=False)
    assert c.post("/ask", json={"query": "x", "anexos": [item("image/png", PNG)]}).status_code == 500
    assert vagas.acquire(blocking=False) and vagas.acquire(blocking=False)      # as 2 vagas livres


def test_base64_sai_do_pedido_ao_decodificar():
    lista = [item("image/png", PNG), item("application/pdf", LAUDO)]
    anexos.prepara(lista)
    assert all("dados" not in a for a in lista)


def test_so_anexo_nao_busca_nem_vai_ao_pubmed(cli, monkeypatch):
    fetch, grava, br = [], [], []
    monkeypatch.setattr(server.ingest, "fetch_and_embed", lambda *a, **k: fetch.append(a) or ([], []))
    monkeypatch.setattr(server, "_safe_persist", lambda *a: grava.append(a))
    monkeypatch.setattr(server, "_bg_enrich", lambda *a: grava.append(a))
    monkeypatch.setattr(server.search, "br_guidelines", lambda q, **kw: br.append(q) or [])
    r = cli.post("/ask", json={"query": "", "anexos": [item("application/pdf", LAUDO)]})
    assert r.status_code == 200
    assert cli.vistos["plan"] == [] and cli.vistos["search"] == [] and fetch == [] and grava == [] and br == []
    ultima = cli.vistos["modelo"][0][-1]["content"]
    assert "(nenhum trecho recuperado)" in ultima and "Ferritina: 12 ng/mL" in ultima
    assert "Pergunta do médico: Analise o anexo." in ultima
    fontes = [e for e in _frases(r) if "sources" in e][0]
    assert fontes["sources"] == []


def test_com_pergunta_escrita_busca_como_antes(cli):
    r = cli.post("/ask", json={"query": "O que sugere?", "anexos": [item("application/pdf", LAUDO)]})
    assert r.status_code == 200
    assert cli.vistos["plan"] and cli.vistos["search"]
    assert "Ferritin below 30" in cli.vistos["modelo"][0][-1]["content"]
