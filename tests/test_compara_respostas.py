"""scripts/compara_respostas: o encanamento do antes × depois, sem OpenAI e sem banco. O planejamento, a busca, o PubMed e o
modelo são simulados; o _ask_stream é o de verdade, para conferir que a troca de configuração chega ao modelo e que
nenhum caminho de escrita no banco roda."""
import json
import os
import time

import pytest

from app import config, db, ingest, server, synthesize
from scripts import compara_respostas as cr

HIT = {"chunk_id": 1, "document_id": 1, "title": "Diabetes care standards", "url": "https://pmc.example/1",
       "source_type": "pmc", "evidence": "Diretriz", "publication_date": None, "section_title": None,
       "text": "HbA1c target below 7%.", "score": 0.9, "cosine_sim": 0.9}


def _prompt(nome):
    with open(os.path.join(config.ROOT, "prompts", nome), encoding="utf-8") as fh:
        return fh.read().strip()


@pytest.fixture
def falsos(monkeypatch):
    """_plan, busca, cálculo e modelo simulados; devolve o que o modelo recebeu."""
    vistos = {"modelo": [], "busca": 0.9, "fetch": []}
    monkeypatch.setattr(server, "_plan", lambda q, h: {"medical": True, "standalone": q, "question_en": "q",
                                                       "terms_en": "diabetes targets"})
    monkeypatch.setattr(server.tools, "renal_note", lambda q: None)

    def busca(q, k=6, fts_query=None):
        sim = vistos["busca"]
        return {"insufficient": False, "best_sim": sim, "hits": [dict(HIT, cosine_sim=sim, score=sim)] if sim else [],
                "qvec": [1.0, 0.0]}
    monkeypatch.setattr(server.search, "search", busca)

    def fetch(terms, retmax=10, mindate=None):
        vistos["fetch"].append(terms)
        art = {"title": "Diabetes guideline", "url": "https://pubmed.example/2", "year": 2024, "pub_types": ["Guideline"]}
        return [(art, [("Abstract", "HbA1c target below 7%.")])], [[1.0, 0.0]]
    monkeypatch.setattr(server.ingest, "fetch_and_embed", fetch)

    def modelo(msgs, **kw):
        vistos["modelo"].append((msgs[0]["content"], kw))
        yield "**A avaliação:** meta de HbA1c abaixo de 7% [1].\n\n## 1. Metas\n\n| Parâmetro | Meta |\n|---|---|\n| HbA1c | < 7% |\n\n"
        yield "```plano\n## Agora | Exames\n- HbA1c.\n```\n\n**Minha recomendação:** pedir a HbA1c."
    monkeypatch.setattr(server.llm, "stream_chat", modelo)
    return vistos


def test_perguntas_sem_nome_e_a_primeira_e_a_do_chatgpt():
    assert len(cr.PERGUNTAS) == 10 and len({s for s, _ in cr.PERGUNTAS}) == 10
    assert cr.PERGUNTAS[0][1].startswith("Mulher de 58 anos com hipertensão arterial e diabetes tipo 2")
    for _, q in cr.PERGUNTAS:
        assert "?" in q and len(q) < 1500           # cabe no MAX_QUERY_CHARS do /ask
        assert len(q) <= server.MAX_QUERY_CHARS


def test_medidas():
    t = ("Abertura [1] e [2, 3].\n\n## 1. Metas\n\n| A | B |\n|---|---|\n| x | y |\n\n## 2. Exames\n\n| C | D |\n|---|---|\n\n"
         "```plano\n## Agora | Exames\n- HbA1c.\n## Depois | Revisão\n```\n")
    m = cr.medidas(t)
    assert m["secoes"] == 2                      # o "## Agora" dentro do ```plano não conta
    assert m["tabelas"] == 2 and m["planos"] == 1
    assert m["citacoes"] == 2 and m["fontes_citadas"] == 3
    assert cr.medidas("")["palavras"] == 0


def test_coletar_junta_as_frases_e_tira_a_assinatura():
    evs = [server._sse("sources", {"sources": [{"n": 1}], "recommended": []}),
           server._sse("sentence", {"text": "Uma frase. "}), server._sse("sentence", {"text": "Outra."}),
           server._sse("done", {"insufficient": False, "cited": [1], "sig": "segredo"})]
    r = cr.coletar(iter(evs))
    assert r["texto"] == "Uma frase. Outra." and r["fontes"] == [{"n": 1}]
    assert "sig" not in r["fim"] and r["fim"]["cited"] == [1]
    r = cr.coletar(iter([server._sse("insufficient", {"text": "fora"}), server._sse("done", {"insufficient": True})]))
    assert r["texto"] == "fora" and r["aviso"]["tipo"] == "insufficient"


def test_configuracao_troca_e_devolve(falsos):
    velho = (synthesize.PROMPT_PATH, config.ASK_REASONING_EFFORT, config.ASK_VERBOSITY, config.ASK_MAX_TOKENS)
    with cr.configuracao("clinical_answer.v3.md", "low", "low", 2000):
        r = cr.coletar(server._ask_stream("pergunta", 6))
    prompt, kw = falsos["modelo"][0]
    assert prompt == _prompt("clinical_answer.v3.md")
    assert {k: v for k, v in kw.items() if k != "estado"} == {"max_tokens": 2000, "reasoning": "low", "verbosity": "low"}
    assert kw["estado"] == {}                              # o fim da resposta é por pergunta (não global)
    assert (synthesize.PROMPT_PATH, config.ASK_REASONING_EFFORT, config.ASK_VERBOSITY, config.ASK_MAX_TOKENS) == velho
    assert "Minha recomendação" in r["texto"] and r["fontes"]


def _espera(reg, nome):
    fim = time.time() + 2
    while nome not in reg and time.time() < fim:
        time.sleep(0.01)
    return nome in reg


def test_sem_gravar_bloqueia_o_enriquecimento_em_2o_plano(falsos, monkeypatch):
    chamou = []
    monkeypatch.setattr(ingest, "persist", lambda *a: chamou.append("persist"))
    falsos["busca"] = 0.64                      # entre FETCH_BLOCK_SIM e FETCH_SIM → _bg_enrich em thread
    with cr.sem_gravar() as reg:
        cr.coletar(server._ask_stream("pergunta", 6))
        assert _espera(reg, "_bg_enrich")
    assert not chamou and not falsos["fetch"]    # nem PubMed nem gravação


def test_sem_gravar_bloqueia_o_cache_do_pubmed_ao_vivo(falsos, monkeypatch):
    chamou = []
    monkeypatch.setattr(ingest, "persist", lambda *a: chamou.append("persist"))
    falsos["busca"] = 0                         # sem trecho local → PubMed ao vivo, resultado "cacheable"
    with cr.sem_gravar() as reg:
        r = cr.coletar(server._ask_stream("pergunta", 6))
        assert _espera(reg, "_safe_persist")
    assert falsos["fetch"] and r["fontes"] and not chamou


def test_sem_gravar_recusa_escrita_direta_e_devolve_tudo():
    velhos = (server._bg_enrich, server._safe_persist, ingest.persist, db.insert_chunks_bulk, db.upsert_documents_bulk)
    with cr.sem_gravar() as reg:
        ingest.persist([("a", [])], [])
        for f in (db.insert_chunks_bulk, db.upsert_documents_bulk, db.insert_chunks, db.upsert_document):
            with pytest.raises(RuntimeError):
                f(None, [])
    assert reg[0] == "ingest.persist" and len(reg) == 5
    assert (server._bg_enrich, server._safe_persist, ingest.persist, db.insert_chunks_bulk,
            db.upsert_documents_bulk) == velhos


def test_rodar_com_o_ask_real_grava_md_e_resumo(falsos, tmp_path, capsys):
    resumo = cr.rodar([1, 3], str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == ["01-dm2-has.md", "03-dislipidemia-primaria.md", "resumo.json"]
    assert [kw["reasoning"] for _, kw in falsos["modelo"]] == ["low", config.ASK_REASONING_EFFORT] * 2
    assert [p for p, _ in falsos["modelo"]] == [_prompt("clinical_answer.v3.md"), _prompt(os.path.basename(synthesize.PROMPT_PATH))] * 2
    d = json.loads((tmp_path / "resumo.json").read_text(encoding="utf-8"))
    assert d == json.loads(json.dumps(resumo))
    r = d["perguntas"][0]["resultados"]
    assert set(r) == {"ANTES", "DEPOIS"} and r["DEPOIS"]["tabelas"] == 1 and r["DEPOIS"]["planos"] == 1
    md = (tmp_path / "01-dm2-has.md").read_text(encoding="utf-8")
    assert "## ANTES" in md and "## DEPOIS" in md and "### Fontes" in md
    log = capsys.readouterr().out
    assert "Mulher de 58" not in log and "hipertensão" not in log     # o log não leva a pergunta


def test_dry_run_e_only(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(server.llm, "stream_chat", lambda *a, **k: pytest.fail("dry-run chamou o modelo"))
    monkeypatch.setattr(server, "_plan", lambda *a: pytest.fail("dry-run chamou o planejamento"))
    assert cr.main(["--dry-run", "--only", "2", "--out", str(tmp_path)]) == 0
    d = json.loads((tmp_path / "resumo.json").read_text(encoding="utf-8"))
    assert [p["n"] for p in d["perguntas"]] == [2]
    r = d["perguntas"][0]["resultados"]
    assert r["ANTES"]["tabelas"] == 0 and r["DEPOIS"]["tabelas"] == 1
    assert "→" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cr.main(["--dry-run", "--only", "11", "--out", str(tmp_path)])
