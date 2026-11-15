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


def test_clinical_without_citation_is_ok():
    # frase sem citação é permitida (complemento com conhecimento consolidado)
    ok, reason = v.validate_sentence("A conduta deve ser individualizada.", {1}, {1: "qualquer"})
    assert ok, reason


def test_number_not_grounded_is_ok():
    # número não precisa constar no trecho citado (validação relaxada)
    ok, reason = v.validate_sentence(
        "reduziu 42% dos eventos [1].", {1}, {1: "reduziu os eventos de forma significativa"}
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
    out = b.feed("Primeira frase. Segunda ")
    assert [s.strip() for s in out] == ["Primeira frase."]
    # quebra de parágrafo é preservada (vira \n\n)
    out = b.feed("parte.\n\nNovo")
    assert out and out[0].strip() == "Segunda parte." and out[0].endswith("\n\n")
    # decimais não quebram a frase
    b2 = v.SentenceBuffer()
    assert b2.feed("Valor 6.09 ok") == []
    assert b2.flush() == "Valor 6.09 ok"


# ---------- citação inválida: sai só o [n] ----------
def test_strip_invalid_keeps_table():
    tabela = "| Exame | Meta |\n|---|---|\n| HbA1c | <7% [1] |\n| LDL | <70 mg/dL [9] |\n\n"
    out, bad = v.strip_invalid(tabela, {1, 2})
    assert bad == {9}
    assert out == "| Exame | Meta |\n|---|---|\n| HbA1c | <7% [1] |\n| LDL | <70 mg/dL |\n\n"


def test_strip_invalid_keeps_plano_fence():
    plano = "```plano\n- pedir HbA1c [7]\n- retorno em 3 meses [1]\n```\n"
    out, bad = v.strip_invalid(plano, {1})
    assert bad == {7} and out == "```plano\n- pedir HbA1c\n- retorno em 3 meses [1]\n```\n"


# ---------- fidelidade linha a linha ----------
def test_ground_citations_per_line():
    tabela = ("| Parâmetro | Meta |\n|---|---|\n"
              "| HbA1c | <7% [1] |\n"
              "| LDL | <55 mg/dL [1] |\n")
    out, removed = v.ground_citations(tabela, {1: "target HbA1c below 7%"})
    assert removed == {1}
    linhas = out.splitlines()
    assert linhas[2] == "| HbA1c | <7% [1] |"          # a linha sustentada mantém a citação
    assert linhas[3] == "| LDL | <55 mg/dL |"           # só a linha sem respaldo perde o [1]


def test_ground_citations_keeps_indentation():
    lista = "1. Metas:\n   - PA < 130 mmHg [2]\n"
    out, removed = v.ground_citations(lista, {2: "nothing numeric"})
    assert removed == {2} and out == "1. Metas:\n   - PA < 130 mmHg\n"


# ---------- buffer: Markdown exato ----------
def _stream(text, step=3):
    b, out = v.SentenceBuffer(), []
    for i in range(0, len(text), step):
        out += b.feed(text[i:i + step])
    tail = b.flush()
    return out + ([tail] if tail else [])


def test_buffer_preserves_lists_exactly():
    text = "Rotina:\n1. HbA1c. A cada 6 meses.\n2. Perfil lipídico\n   - anual\n3. Retorno\n\nFim."
    out = _stream(text)
    assert "".join(out) == text
    assert not any(p.strip() in ("1.", "2.", "3.") for p in out)   # marcador nunca vira frase sozinho


def test_buffer_emits_table_and_fence_whole():
    tabela = "| Exame | Intervalo |\n|---|---|\n| HbA1c | 6 meses |\n| TFG | anual |\n\n"
    plano = "```plano\n- pedir HbA1c. Agora.\n- retorno 3 meses\n```\n"
    text = "Veja. " + tabela + plano + "Fim."
    out = _stream(text, 2)
    assert "".join(out) == text
    assert tabela in out and plano in out


# ---------- "sem fonte": repetir dado do paciente não conta ----------
def test_ungrounded_ignores_patient_own_data():
    own = "em uso de losartana 50 mg 12/12h, metformina 850 mg 2x/dia; peso 86,8 kg"
    assert not v.is_ungrounded_claim("Em uso de losartana 50 mg e metformina 850 mg.", own)
    assert not v.is_ungrounded_claim("| Peso | 86,8 kg |", own)
    # dose ou fármaco novos continuam contando
    assert v.is_ungrounded_claim("Aumentar losartana para 100 mg/dia.", own)
    assert v.is_ungrounded_claim("Associar dapagliflozina.", own)
    assert v.is_ungrounded_claim("usar 10 mg/dia de enalapril.")          # sem own_text, como antes
    assert v.ungrounded_lines("| losartana | 50 mg |\n| enalapril | 10 mg |\n", own) == 1


# ---------- frase quebrada em duas linhas: a citação da 2ª linha vale para a dose da 1ª ----------
def test_ground_citations_frase_quebrada():
    out, removed = v.ground_citations("Losartana 100 mg/dia\nem dose única [1].", {1: "losartan 50 mg"})
    assert removed == {1} and out == "Losartana 100 mg/dia\nem dose única."


def test_buffer_frase_quebrada_sai_junta():
    text = "Losartana 100 mg/dia\nem dose única [1]. Depois.\n- item\n- outro"
    out = _stream(text, 2)
    assert "".join(out) == text
    assert out[0] == "Losartana 100 mg/dia\nem dose única [1]. "


def test_buffer_linha_so_de_espacos_nao_some():
    text = "| a | b |\n|---|---|\n| x | 1 |\n   \nTexto final."
    out = _stream(text, 3)
    assert "".join(out) == text and all(p.strip() for p in out)
