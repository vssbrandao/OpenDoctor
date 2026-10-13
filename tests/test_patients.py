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
