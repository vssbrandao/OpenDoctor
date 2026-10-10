"""Testes das ferramentas determinísticas (sem rede)."""
from app import tools


def test_egfr_male_scr2_age65():
    # referência NKF/KDIGO: ~36 mL/min/1,73 m² (G3b)
    v = tools.egfr_ckd_epi_2021(2.0, 65, "M")
    assert 35.5 <= v <= 37.0
    assert tools.ckd_stage(v) == "G3b"


def test_egfr_female_normal():
    # mulher 40 anos, Scr 0,7 → ~110 (G1)
    v = tools.egfr_ckd_epi_2021(0.7, 40, "F")
    assert 105 <= v <= 115
    assert tools.ckd_stage(v) == "G1"


def test_ckd_stages_boundaries():
    assert tools.ckd_stage(90) == "G1"
    assert tools.ckd_stage(60) == "G2"
    assert tools.ckd_stage(45) == "G3a"
    assert tools.ckd_stage(30) == "G3b"
    assert tools.ckd_stage(15) == "G4"
    assert tools.ckd_stage(14.9) == "G5"


def test_cockcroft_gault():
    # (140-65)*70/(72*2.0) = 36.46 → 36.5
    assert tools.cockcroft_gault(2.0, 65, "M", 70) == 36.5
    assert tools.cockcroft_gault(2.0, 65, "F", 70) == round(36.458 * 0.85, 1)


def test_renal_note_ignores_unrelated(monkeypatch):
    called = []
    monkeypatch.setattr(tools, "_extract_renal_inputs", lambda t: called.append(t) or {})
    assert tools.renal_note("conduta na sepse") is None
    assert called == []   # nem chama o LLM


def test_renal_note_missing_data(monkeypatch):
    monkeypatch.setattr(tools, "_extract_renal_inputs", lambda t: {"scr": 1.5, "age": None, "sex": "M"})
    note = tools.renal_note("calcule o eGFR com creatinina 1,5")
    assert "falta" in note and "idade" in note


def test_renal_note_computes(monkeypatch):
    monkeypatch.setattr(tools, "_extract_renal_inputs",
                        lambda t: {"scr": 2.0, "age": 65, "sex": "M", "weight": 70})
    note = tools.renal_note("estime a TFG")
    assert "CKD-EPI 2021" in note and "G3b" in note and "Cockcroft-Gault" in note
