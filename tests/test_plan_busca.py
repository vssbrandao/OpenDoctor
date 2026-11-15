"""Planejamento da busca com pergunta longa de caso clínico (sem rede: llm.chat simulado)."""
import json

from app import server

# a pergunta real do prontuário (~900 caracteres) do comparativo com o ChatGPT
PERGUNTA = (
    "Mulher de 58 anos com hipertensão arterial e diabetes tipo 2, em uso de losartana 50 mg 12/12h, metformina 850 mg "
    "2x/dia e atorvastatina 20 mg à noite; alergia a dipirona e penicilina. Últimos sinais vitais: pressão arterial "
    "128/82 mmHg (na referência), peso 86,8 kg, glicemia 108 mg/dL (na referência), frequência cardíaca 74 bpm (na "
    "referência). Exames de acompanhamento atrasados ou sem registro: hemoglobina glicada (HbA1c) (sem registro; a cada "
    "6 meses), perfil lipídico (sem registro; anual), creatinina e TFG (sem registro; anual), albuminúria (RAC) (sem "
    "registro; anual), potássio (sem registro; anual), ácido úrico (sem registro; anual), TGP (ALT) (sem registro; "
    "anual). Todos os sinais e exames com faixa de referência estão dentro dela. Quais metas e qual rotina de "
    "acompanhamento (exames, rastreamentos e intervalo de retorno) são recomendadas para esse perfil?"
)
VALIDO = json.dumps({"medical": True, "terms_en": "diabetes hypertension follow-up targets",
                     "question_en": "Targets and follow-up schedule for a 58-year-old woman with hypertension "
                                    "and type 2 diabetes?"})


def _fake(out, seen):
    def chat(messages, **kw):
        seen.update(kw, system=messages[0]["content"])
        return out
    return chat


def test_pergunta_longa_json_valido(monkeypatch):
    seen = {}
    monkeypatch.setattr(server.llm, "chat", _fake(VALIDO, seen))
    p = server._plan(PERGUNTA, [])
    assert len(PERGUNTA) > 800
    assert seen["max_tokens"] >= 600
    assert '"standalone"' not in seen["system"]          # sem histórico o modelo não repete a pergunta
    assert p["standalone"] == PERGUNTA and p["medical"] is True
    assert p["terms_en"] == "diabetes hypertension follow-up targets"
    assert p["question_en"].startswith("Targets")


def test_pergunta_longa_json_cortado_aproveita_campos(monkeypatch):
    cortado = VALIDO[:VALIDO.index('"question_en"') + 40]   # cortado no meio de question_en
    logs = []
    monkeypatch.setattr(server, "_log", lambda *a: logs.append(" ".join(map(str, a))))
    monkeypatch.setattr(server.llm, "chat", _fake(cortado, {}))
    p = server._plan(PERGUNTA, [])
    assert p["terms_en"] == "diabetes hypertension follow-up targets"
    assert p["standalone"] == PERGUNTA
    assert "losartana" not in p["question_en"]          # não cai para a pergunta em português
    assert any("cortado" in x for x in logs)
    assert not any("losartana" in x or "Mulher" in x for x in logs)   # o texto da pergunta nunca vai ao log


def test_json_cortado_sem_termos_nao_vai_ao_pubmed(monkeypatch):
    logs = []
    monkeypatch.setattr(server, "_log", lambda *a: logs.append(" ".join(map(str, a))))
    monkeypatch.setattr(server.llm, "chat", _fake('{"medical": true, "terms_en": "type 2 diab', {}))
    p = server._plan(PERGUNTA, [])
    assert p["medical"] is True and p["terms_en"] == ""
    assert not any("Mulher" in x for x in logs)

    seen, fetched = {}, []
    monkeypatch.setattr(server, "_plan", lambda q, h: p)

    def fake_search(q, k=None, fts_query=None):
        seen.update(q=q, fts=fts_query)
        return {"insufficient": True, "best_sim": 0.0, "hits": [], "qvec": [0.0]}
    monkeypatch.setattr(server.search, "search", fake_search)
    monkeypatch.setattr(server.ingest, "fetch_and_embed", lambda *a, **k: fetched.append(a) or ([], []))
    monkeypatch.setattr(server.llm, "stream_chat", lambda *a, **k: iter(["Resposta."]))
    evs = list(server._ask_stream(PERGUNTA, 6, []))
    assert fetched == []                                  # português cru não vai ao PubMed
    assert not (seen["fts"] or "").strip()                # nem ao full-text (inglês)
    assert any("sentence" in e for e in evs)


def test_com_historico_pede_standalone(monkeypatch):
    seen = {}
    out = json.dumps({"medical": True, "terms_en": "cystitis pregnancy antibiotics",
                      "question_en": "Cystitis treatment in pregnancy?", "standalone": "Cistite na gestante?"})
    monkeypatch.setattr(server.llm, "chat", _fake(out, seen))
    p = server._plan("e na gestante?", [{"role": "user", "content": "tratamento de cistite"}])
    assert '"standalone"' in seen["system"] and p["standalone"] == "Cistite na gestante?"
