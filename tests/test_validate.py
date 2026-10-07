"""Testes das checagens determinísticas (spec §6.1)."""
from app import validate as v


def test_citations():
    assert v.citations("conduta X [1] e Y [3].") == {1, 3}
    assert v.citations("sem citação") == set()


def test_dose_tokens():
    doses = dict(v.dose_tokens("iniciar 10 mg/dia; reduziu 6,09% dos eventos"))
    assert "10" in doses and "6,09" in doses


def test_drug_mentions():
    found = set(x.lower() for x in v.drug_mentions("usar dapagliflozina e atenolol; evitar enalapril"))
    assert {"dapagliflozina", "atenolol", "enalapril"} <= found
    # não deve marcar palavra comum
    assert v.drug_mentions("o paciente estava estável") == []


def test_invalid_citation():
    ok, reason = v.validate_sentence("conduta seria X [9].", {1, 2}, {1: "txt", 2: "txt"})
    assert not ok and "inválida" in reason


def test_clinical_without_citation():
    ok, reason = v.validate_sentence("usar dapagliflozina 10 mg/dia.", {1}, {1: "dapagliflozina 10 mg/dia"})
    assert not ok and "sem citação" in reason


def test_number_not_grounded():
    # cita [1], mas o número não está no trecho citado
    ok, reason = v.validate_sentence(
        "reduziu 42% dos eventos [1].", {1}, {1: "reduziu os eventos de forma significativa"}
    )
    assert not ok and "não consta" in reason


def test_number_grounded_decimal_separator():
    # resposta usa vírgula, trecho usa ponto — deve casar
    ok, reason = v.validate_sentence(
        "redução de 6,09% dos eventos [1].", {1}, {1: "HF events 6.09% vs 15.65%"}
    )
    assert ok, reason


def test_drug_name_not_grounded_is_ok():
    # nome de fármaco NÃO é ancorado (PT vs EN): basta ter citação válida
    ok, reason = v.validate_sentence(
        "iniciar dapagliflozina [1].", {1}, {1: "dapagliflozin reduced events [HR 0.82]"}
    )
    assert ok, reason


def test_valid_sentence_passes():
    ok, reason = v.validate_sentence(
        "SGLT2i reduziu eventos 6,09% vs 15,65% [1].", {1, 2},
        {1: "SGLT2i reduced HF events 6.09% vs 15.65% P=0.020", 2: "outro"}
    )
    assert ok, reason


def test_non_clinical_sentence_ok_without_citation():
    ok, reason = v.validate_sentence("A seguir, os detalhes.", {1}, {1: "qualquer"})
    assert ok, reason


def test_sentence_buffer():
    b = v.SentenceBuffer()
    assert b.feed("Primeira frase. Segunda ") == ["Primeira frase."]
    assert b.feed("parte. ") == ["Segunda parte."]
    # decimais não quebram a frase
    assert b.feed("Valor 6.09 ok") == []
    assert b.flush() == "Valor 6.09 ok"
