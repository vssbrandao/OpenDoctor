"""Vaga das diretrizes brasileiras no /ask: a busca em português só nelas (search.br_guidelines) e a montagem dos k
documentos que vão ao modelo (server._com_diretrizes). Sem banco e sem OpenAI."""
import contextlib
import datetime

from app import search, server


def _linha(i, titulo, secao, cos, fonte_url="https://abccardiol.org/x.pdf"):
    return (i, 100 + i if titulo != "mesmo" else 100, secao, f"texto {i}", titulo, fonte_url, "guideline",
            datetime.date(2025, 1, 1), cos)


def _com_linhas(monkeypatch, linhas):
    @contextlib.contextmanager
    def conexao():
        yield None
    monkeypatch.setattr(search.db, "connection", conexao)
    monkeypatch.setattr(search, "_br_vector_search", lambda conn, qvec, limit: linhas)


def test_br_tira_secoes_administrativas_e_o_que_nao_e_do_tema(monkeypatch):
    _com_linhas(monkeypatch, [
        _linha(1, "PCDT DM2", "12. REGULAÇÃO, CONTROLE E AVALIAÇÃO PELO GESTOR", 0.75),
        _linha(2, "PCDT DM2", "8.1. Metas terapêuticas", 0.72),
        _linha(3, "Diretriz HAS 2025", "18. Avaliação da Subcomissão Técnica", 0.71),
        _linha(4, "Diretriz HAS 2025", "14.9. Bases do Tratamento", 0.69),
        _linha(5, "Diretriz Dislipidemias", "5.2.4. Risco Muito Alto", 0.66),   # mais de 0,05 abaixo do melhor
        _linha(6, "PCDT DRC", "Title", 0.70),
    ])
    hits = search.br_guidelines("pergunta", qvec=[0.0])
    assert [h["chunk_id"] for h in hits] == [2, 4]
    assert all(h["br"] and h["cosine_sim"] >= search.BR_FLOOR for h in hits)


def test_br_abaixo_do_corte_nao_entra(monkeypatch):
    _com_linhas(monkeypatch, [_linha(1, "Diretriz HAS 2025", "4. Diagnóstico", 0.55)])
    assert search.br_guidelines("asma grave na gestante", qvec=[0.0]) == []


def _doc(titulo, br=False):
    h = {"chunk_id": titulo, "document_id": titulo, "title": titulo, "url": "u/" + titulo, "text": "t " + titulo}
    if br:
        h["br"] = True
    return h


def test_diretrizes_nas_primeiras_vagas_sem_repetir_documento():
    br = [_doc("Diretriz HAS 2025", True), _doc("Diretriz HAS 2025", True), _doc("PCDT DM2", True), _doc("PCDT DRC", True)]
    docs = [_doc("Artigo A"), _doc("PCDT DM2"), _doc("Artigo B"), _doc("Artigo C"), _doc("Artigo D"), _doc("Artigo E")]
    hits = server._com_diretrizes(br, docs, 6)
    titulos = [h["title"] for h in hits]
    assert titulos == ["Diretriz HAS 2025", "PCDT DM2", "Artigo A", "Artigo B", "Artigo C", "Artigo D"]
    assert hits[0]["text"].count("t Diretriz HAS 2025") == 2      # os trechos do mesmo documento viram um [n] só


def test_sem_diretriz_fica_a_busca_principal():
    docs = [_doc("Artigo A"), _doc("Artigo B")]
    assert server._com_diretrizes([], docs, 6) == docs
