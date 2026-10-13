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


def test_nome_do_paciente_em_evento_antigo():
    from app.integrations import _event_patient_name
    from app.db import patient_key
    assert _event_patient_name({"summary": "Consulta — Ana Paula"}) == "Ana Paula"
    assert _event_patient_name({"summary": "Ana", "description": "obs\nPaciente: Ana Souza"}) == "Ana Souza"
    # "Ana" não pode casar com "Ana Paula"
    assert patient_key(_event_patient_name({"summary": "Retorno — Ana Paula"})) != patient_key("Ana")
