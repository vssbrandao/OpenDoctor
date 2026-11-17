"""IMC/KDIGO classificados pelo código (tools.clinical_facts) e a limpeza das citações (validate.thin_citations,
validate.sem_bastidor). Sem banco e sem OpenAI."""
from app import tools, validate


def test_imc_29_e_sobrepeso_nao_obesidade():
    f = tools.clinical_facts("Homem de 49 anos, peso 92 kg, altura 1,78 m, PA 138/88 mmHg")
    assert "IMC = 92,0 kg / (1,78 m)² = 29,0 kg/m² → sobrepeso (pré-obesidade)" in f


def test_imc_em_cm_e_obesidade_grau_ii():
    assert "38,2 kg/m² → obesidade grau II" in tools.clinical_facts("peso 104 kg, altura 165 cm")


def test_kdigo_g3a_a2_e_drc():
    f = tools.clinical_facts("TFG estimada 48 mL/min/1,73 m² (abaixo), relação albumina/creatinina 120 mg/g")
    assert "categoria G3a (KDIGO)" in f and "categoria A2 (KDIGO)" in f and "G3a/A2 → doença renal crônica" in f


def test_tfg_78_sozinha_nao_e_drc():
    f = tools.clinical_facts("TFG estimada 78 mL/min/1,73 m² (na referência)")
    assert "G2 sozinho não define doença renal crônica" in f


def test_potassio_5_pede_controle_em_1_a_2_semanas():
    f = tools.clinical_facts("enalapril 10 mg 12/12h; potássio 5,0 mEq/L (na referência)")
    assert "Potássio 5,0 mEq/L (≥5,0)" in f and "1–2 semanas (não 2–4)" in f


def test_potassio_normal_nao_gera_regra():
    assert tools.clinical_facts("potássio 4,2 mEq/L") is None


def test_varfarina_traz_o_inr_da_troca():
    assert "INR <2,0 (apixabana, dabigatrana)" in tools.clinical_facts("em uso de varfarina 5 mg")


def test_ldl_em_estatina_moderada_estima_o_basal():
    f = tools.clinical_facts("rosuvastatina 10 mg à noite. Últimos exames: LDL-c 142 mg/dL (acima da referência)")
    assert "Rosuvastatina 10 mg = estatina de intensidade moderada" in f
    assert "~203–278 mg/dL" in f and "provável LDL basal ≥190" in f


def test_sinvastatina_40_e_moderada_e_atorva_80_e_alta():
    assert tools.estatina_intensidade("sinvastatina", 40) == "moderada"
    assert tools.estatina_intensidade("atorvastatina", 80) == "alta"
    assert tools.estatina_intensidade("sinvastatina", 10) == "baixa"


def test_sulfonilureia_e_betabloqueador_congesto():
    f = tools.clinical_facts("gliclazida MR 60 mg; carvedilol 12,5 mg 12/12h; peso 77 kg (2 kg acima do peso seco)")
    assert "Em uso de sulfonilureia" in f and "não suba a dose do betabloqueador" in f


def test_betabloqueador_sem_congestao_nao_avisa():
    assert tools.clinical_facts("metoprolol 50 mg 12/12h") is None


def test_estatina_moderada_lembra_alta_mais_ezetimiba_no_alto_risco():
    f = tools.clinical_facts("sinvastatina 40 mg à noite")
    assert "ezetimiba 10 mg desde o início" in f


def test_ieca_bra_lembra_controle_ao_somar_espironolactona():
    f = tools.clinical_facts("losartana 100 mg/dia, anlodipino 10 mg/dia e clortalidona 25 mg/dia")
    assert "se associar espironolactona" in f and "1–2 semanas (não 2–4)" in f


def test_sem_dado_nao_ha_bloco():
    assert tools.clinical_facts("Qual a profilaxia da enxaqueca crônica?") is None


def test_grupo_de_citacoes_fica_com_duas_sem_repetir():
    t, n = validate.thin_citations("A meta é <130/80 mmHg [1][2][1][3].")
    assert t == "A meta é <130/80 mmHg [1][2]." and n == 2


def test_tabela_cita_cada_fonte_uma_vez():
    tab = ("| Exame | Periodicidade |\n|---|---|\n| Creatinina | Anual [1][2] |\n| Potássio | Anual [1][2] |\n"
           "| Ácido úrico | Anual [3] |\n")
    t, n = validate.thin_citations(tab)
    assert t == ("| Exame | Periodicidade |\n|---|---|\n| Creatinina | Anual [1][2] |\n| Potássio | Anual |\n"
                 "| Ácido úrico | Anual [3] |\n") and n == 2


def test_plano_cita_cada_fonte_uma_vez():
    plano = "```plano\n## Agora | Exames\n- HbA1c [1].\n- RAC [1].\n## Anual | Rotina\n- Pés [2].\n```"
    t, _ = validate.thin_citations(plano)
    assert t == "```plano\n## Agora | Exames\n- HbA1c [1].\n- RAC.\n## Anual | Rotina\n- Pés [2].\n```"


def test_frase_solta_nao_perde_citacao():
    assert validate.thin_citations("Iniciar iSGLT2 [2].")[0] == "Iniciar iSGLT2 [2]."


def test_sem_bastidor():
    assert validate.sem_bastidor("Pelo cálculo determinístico do sistema, a TFG é 52.") == "Pelo cálculo, a TFG é 52."
    assert validate.sem_bastidor("Cálculo determinístico: 52.") == "Cálculo: 52."


# ===== achados da revisão do commit fdeaa43 =====
def test_mencao_nao_e_uso():
    for q in ("Posso iniciar varfarina na FA?", "Devo associar gliclazida?",
              "Paciente com alergia a captopril, qual anti-hipertensivo?", "LDL-c 160 mg/dL, vou iniciar rosuvastatina 10 mg"):
        assert tools.clinical_facts(q) is None, q


def test_ldl_de_antes_do_tratamento_nao_e_estimado():
    f = tools.clinical_facts("LDL 150 mg/dL antes do tratamento; em uso de sinvastatina 20 mg") or ""
    assert "antes do tratamento estaria" not in f


def test_estimativa_do_ldl_e_condicional():
    f = tools.clinical_facts("rosuvastatina 10 mg. LDL-c 142 mg/dL")
    assert "SE o LDL-c 142 foi medido já em uso dela" in f and "nesse caso, provável LDL basal ≥190" in f


def test_peso_que_variou_e_reposicao_de_potassio_nao_entram():
    assert tools.clinical_facts("perda de peso de 8 kg em 3 meses, altura 1,70 m") is None
    assert tools.clinical_facts("cloreto de potássio 6 mEq 2x/dia") is None


def test_linha_da_tabela_que_perde_o_n_repetido_nao_vira_sem_fonte():
    tab = "| Metformina | 500 mg 2x/dia [1] |\n| Empagliflozina | 10 mg/dia [1] |\n"
    assert validate.ungrounded_lines(tab) == 0          # contado antes de enxugar (como no /ask)


def test_frase_quebrada_em_duas_linhas_e_uma_so():
    assert validate.ungrounded_lines("A dose é 100 mg\nao dia [1].\n") == 0


def test_titulo_em_negrito_nao_continua_a_linha_anterior():
    assert len(validate._logical_lines("Use 10 mg ao dia\n**Metas:** HbA1c <7% [1]\n")) == 2


# ===== avisos de dose (16/11/2026): só remédio em uso, a partir do perfil =====
def test_metformina_acima_do_teto_renal():
    f = tools.clinical_facts("Em uso: metformina 850 mg 2x/dia. TFG estimada 34 mL/min/1,73 m²")
    assert "Metformina 1700 mg/dia com TFG 34 (30–44)" in f and "ACIMA: reduzir para ≤1.000 mg/dia" in f
    assert "CONTRAINDICADA" in tools.clinical_facts("metformina 500 mg 1x/dia; TFG estimada 25 mL/min")
    assert "ACIMA" not in tools.clinical_facts("metformina 500 mg 2x/dia; TFG estimada 40 mL/min")


def test_metformina_so_em_uso():
    assert "Metformina" not in (tools.clinical_facts("Posso iniciar metformina 500 mg? TFG estimada 34 mL/min") or "")


def test_dose_maxima_e_frequencia():
    f = tools.clinical_facts("losartana 50 mg 2x/dia; anlodipino 5 mg/dia")
    assert "Losartana 100 mg/dia = dose máxima habitual" in f and "Anlodipino" not in f
    assert "Enalapril" not in (tools.clinical_facts("enalapril 10 mg 12/12h") or "")
    assert "Atorvastatina 80 mg/dia = dose máxima" in tools.clinical_facts("atorvastatina 80 mg à noite")


def test_alergia_a_sulfa_com_sulfonamida_em_uso():
    f = tools.clinical_facts("Em uso: hidroclorotiazida 25 mg/dia; gliclazida 60 mg. Alergias: sulfa.")
    assert "sulfametoxazol-trimetoprima (sulfonamida antibiótica) CONTRAINDICADO" in f
    assert "hidroclorotiazida, gliclazida (sulfonamida NÃO antibiótica)" in f
    assert "sulfametoxazol" not in (tools.clinical_facts("Em uso: hidroclorotiazida 25 mg/dia. Alergias: penicilina.") or "")


def test_aine_com_ieca_e_diuretico_e_tfg_baixa():
    assert "tríade" in tools.clinical_facts("enalapril 10 mg 2x/dia; furosemida 40 mg/dia")
    assert "AINE sistêmico contraindicado" in tools.clinical_facts("TFG estimada 22 mL/min")


def test_espironolactona_com_potassio_alto_e_glibenclamida_no_idoso():
    f = tools.clinical_facts("homem, 76 anos. espironolactona 25 mg/dia; potássio 5,6 mEq/L; glibenclamida 5 mg")
    assert "Espironolactona com K 5,6 (>5,5): reduzir à metade ou suspender" in f
    assert "Glibenclamida com 76 anos: evitar" in f
