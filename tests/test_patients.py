"""Cadastro de pacientes: chave do nome e validação de data do prontuário (sem banco)."""
from app.db import patient_key
from app.server import _iso_or_none


def test_patient_key_ignora_acento_caixa_e_espacos():
    assert patient_key("Luíza  Nonato") == patient_key("LUIZA NONATO") == "luiza nonato"
    assert patient_key("  Zoë ") == "zoe"


def test_patient_key_mantem_outros_alfabetos():
    # antes viravam "" (não dava para cadastrar) ou perdiam letras ("ukasz")
    assert patient_key("李雷") == "李雷"
    assert patient_key("Łukasz") == "łukasz"
    assert patient_key("Straße") == "strasse"


def test_patient_key_vazio():
    assert patient_key("   ") == ""
    assert patient_key(None) == ""


def test_iso_or_none():
    assert _iso_or_none("2026-10-13T12:00:00.000Z") == "2026-10-13T12:00:00.000Z"
    assert _iso_or_none("2026-10-13T09:00:00-03:00") == "2026-10-13T09:00:00-03:00"
    assert _iso_or_none("amanhã") is None
    assert _iso_or_none(123) is None
    assert _iso_or_none("") is None


def test_cpf_ok():
    from app.server import _cpf_ok
    assert _cpf_ok("529.982.247-25")
    assert not _cpf_ok("123.456.789-00")
    assert not _cpf_ok("111.111.111-11")          # dígitos repetidos passam no cálculo, mas são inválidos
    assert not _cpf_ok("5299822472")


def test_date_or_none():
    import datetime
    from app.server import _date_or_none
    assert _date_or_none("1971-03-12") == "1971-03-12"
    assert _date_or_none("1899-12-31") is None
    assert _date_or_none((datetime.date.today() + datetime.timedelta(days=1)).isoformat()) is None
    assert _date_or_none("12/03/1971") is None


def test_note_data_so_campos_conhecidos():
    from app.server import _note_data
    d = _note_data({"mode": "soap", "s": "dor", "x": "lixo", "vitals": {"pa_s": "120", "hack": "1"},
                    "cid": [{"code": "I10", "desc": "HAS"}, "texto", {}]})
    assert d["mode"] == "soap" and d["s"] == "dor" and "x" not in d
    assert d["vitals"] == {"pa_s": "120"}
    assert d["cid"] == [{"code": "I10", "desc": "HAS"}]
    assert _note_data("nada") is None


def test_note_data_exames():
    from app.server import _note_data
    d = _note_data({"mode": "soap", "labs": {"date": "2026-01-10", "v": {"hba1c": "7,1", "ldl": "", "hack": "1"}}})
    assert d["labs"] == {"date": "2026-01-10", "v": {"hba1c": "7,1"}}
    assert _note_data({"mode": "soap", "labs": {"date": "3000-01-01", "v": {"tsh": "2"}}})["labs"]["date"] is None
    assert "labs" not in _note_data({"mode": "soap", "labs": {"v": {"ldl": ""}}})
    assert "labs" not in _note_data({"mode": "soap", "labs": "texto"})
    assert _note_data({"mode": "soap", "kind": "labs"})["kind"] == "labs"
    assert "kind" not in _note_data({"mode": "soap", "kind": "outra"})


def test_nome_do_paciente_em_evento_antigo():
    from app.integrations import _event_patient_name
    from app.db import patient_key
    assert _event_patient_name({"summary": "Consulta — Ana Paula"}) == "Ana Paula"
    assert _event_patient_name({"summary": "Ana", "description": "obs\nPaciente: Ana Souza"}) == "Ana Souza"
    # "Ana" não pode casar com "Ana Paula"
    assert patient_key(_event_patient_name({"summary": "Retorno — Ana Paula"})) != patient_key("Ana")


def test_cid10_busca():
    from app import cid10
    assert cid10.search("I10")[0] == {"code": "I10", "desc": "Hipertensão essencial (primária)"}
    assert cid10.search("e11.9")[0]["code"] == "E11.9"
    assert cid10.search("e119")[0]["code"] == "E11.9"                 # sem o ponto também
    r = cid10.search("hipertensao essencial")                          # sem acento
    assert r and r[0]["code"] == "I10"
    r = cid10.search("asma")                                           # começo de palavra: não "plasmática"
    assert r and all(any(w.startswith("asm") for w in cid10._norm(x["desc"]).split()) for x in r)
    assert not any(x["code"] in ("E42", "R70", "R77") for x in r)
    t2, t1 = cid10.search("diabetes tipo 2"), cid10.search("diabetes tipo 1")
    assert t2[0]["code"] == "E11" and not any(x["code"].startswith("E10") for x in t2)   # não mistura os tipos
    assert t1[0]["code"] == "E10" and not any(x["code"].startswith("E11") for x in t1)
    assert cid10.search("HAS")[0]["code"] == "I10"
    assert cid10.search("covid")[0]["code"] == "U07.1"
    assert cid10.search("") == [] and cid10.search("xyzxyz") == []
    assert len(cid10.search("a", limit=5)) == 5
    assert cid10.get("r51") == "Cefaléia"


def test_anexo_so_pdf_e_imagem_pelo_conteudo():
    from app.server import _sniff, _file_name
    assert _sniff(b"%PDF-1.7") == "application/pdf"
    assert _sniff(b"\xff\xd8\xff\xe0") == "image/jpeg"
    assert _sniff(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert _sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    for ruim in (b"<svg onload=alert(1)>", b"<html>", b"MZ\x90\x00", b""):
        assert _sniff(ruim) is None
    assert _file_name("laudo%2F..%2Fx.pdf") == "laudo .. x.pdf" and _file_name("") == "exame"


def test_paciente_de_exemplo_no_formato_da_tela():
    """O histórico da Maria (fictícia) passa pelo mesmo filtro do servidor sem perder nada."""
    import datetime
    from app import exemplo
    from app.server import _note_data, _sniff
    now = datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)
    cons, labs = exemplo.consultas(now), exemplo.exames(now)
    assert len(cons) == 11 and len(labs) == 6 and exemplo.NAME == "Maria Silva"
    # a marca do exemplo é a chave, que nenhum nome digitado consegue gerar
    from app.db import EXAMPLE_KEY, patient_key
    for nome in ("Maria Silva", " exemplo", "exemplo", "  Exemplo ", "maria silva (exemplo)"):
        assert patient_key(nome) != EXAMPLE_KEY
    for x in cons + labs:
        assert _note_data(x["data"]) == x["data"]
    assert all(c["signed_at"] > c["start"] for c in cons)
    pdf = exemplo.laudo_pdf(datetime.date(2026, 9, 20), exemplo.EXAMES[0.5])
    assert _sniff(pdf[:16]) == "application/pdf" and b"20/09/2026" in pdf and b"%%EOF" in pdf


def test_tempo_de_documentacao_so_numeros_limitados():
    """Linha de base da gravação: o tempo que vai ao finalizar só aceita números dentro dos limites."""
    from app.server import _timing
    assert _timing({"active_s": 312, "wall_s": 900.4, "edits": 41}) == {"active_s": 312, "wall_s": 900, "edits": 41}
    assert _timing({"active_s": -1, "wall_s": 10 ** 9, "edits": True, "texto": "dor"}) is None
    assert _timing({"active_s": "300"}) is None and _timing(None) is None and _timing([1]) is None
