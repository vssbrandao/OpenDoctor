"""Ingestão das diretrizes em PDF (scripts/ingest_diretrizes.py): limpeza, títulos, tamanho dos chunks e as travas do
banco. Sem rede, sem banco e sem OpenAI: o texto das páginas é montado aqui."""
import pytest

from scripts import ingest_diretrizes as ig

CAB = ["Arq Bras Cardiol. 2025; 122(9):e20250624", "Diretrizes", "Brandão et al.",
       "Diretriz Brasileira de Hipertensão Arterial – 2025"]


def _pagina(n, corpo):
    return "\n".join(CAB + corpo + [str(n)])


# ----- limpeza -----

def test_tira_cabecalho_rodape_e_numero_de_pagina():
    corpo = [[f"A PA de 1{i}0 mmHg na página {i + 1}.", f"Outra linha {i}."] for i in range(6)]
    limpas = ig.limpar_paginas([_pagina(i + 1, c) for i, c in enumerate(corpo)])
    assert limpas == corpo                                   # linha com número diferente por página não é cabeçalho


def test_numero_de_pagina_no_topo_e_rodape_de_pcdt():
    pags = [f" \n{i + 1} \n \nConteúdo {i} do protocolo.\n " for i in range(4)]
    assert [p for p in ig.limpar_paginas(pags)] == [[f"Conteúdo {i} do protocolo."] for i in range(4)]


def test_linha_repetida_so_no_meio_da_pagina_fica():
    pags = [_pagina(i + 1, ["Linha A", "FORTE ALTA", "Linha B", "Linha C", "Linha D", "Linha E"]) for i in range(5)]
    assert all("FORTE ALTA" in p for p in ig.limpar_paginas(pags))      # não está nas pontas: é conteúdo


def test_normaliza_espacos_e_glifos():
    assert ig._normaliza("órgãos -alvo e risco CV , alto") == "órgãos-alvo e risco CV, alto"
    assert ig._normaliza("LDL-c 50/uniF6BA99") == "LDL-c 5099"
    assert ig._normaliza("𝑇𝐹𝐺 = 141") == "TFG = 141"
    assert ig._normaliza("de -2,5 mmHg") == "de -2,5 mmHg"                 # sinal de menos não gruda
    assert ig._normaliza("Figura 8️.2 – Fluxograma") == "Figura 8.2 – Fluxograma"   # seletor de emoji da Dislipidemias


def test_junta_palavra_partida_pelo_pypdf():
    cont = ig._contagem("claudicação claudicação claudicação alto alto alto a a a a a a dose dose")
    assert ig.junta_partidas("dor, c laudicação, edema", cont) == "dor, claudicação, edema"
    assert ig.junta_partidas("risco a lto", cont) == "risco alto"
    assert ig.junta_partidas("a dose", cont) == "a dose"                 # duas palavras de verdade: não junta


# ----- hífen no fim da linha -----

def test_hifen_de_quebra_sai_e_hifen_de_verdade_fica():
    vocab = ig._vocab("hipertensão anti-hipertensivo recomenda-se")
    assert ig.junta_hifen("a hiperten-", "são arterial", vocab) == "a hipertensão arterial"
    assert ig.junta_hifen("tratamento anti-", "hipertensivo", vocab) == "tratamento anti-hipertensivo"
    assert ig.junta_hifen("recomenda-", "se o uso", vocab) == "recomenda-se o uso"          # clítico
    assert ig.junta_hifen("pós-", "infarto", set()) == "pós-infarto"                        # prefixo
    assert ig.junta_hifen("moderada-", "-severa", vocab) == "moderada-severa"     # hífen repetido
    assert ig.junta_hifen("LDL-", "colesterol", set()) == "LDL-colesterol"


def test_paragrafo_junta_linhas_e_tira_hifen_de_quebra():
    linhas = ["1. Introdução", "A hipertensão é comum. O trata-", "mento reduz eventos e a hipertensão", "mata."]
    blocos = ig.montar_blocos(linhas, ig._vocab("tratamento hipertensão"))
    assert [b.tipo for b in blocos] == ["h", "p"]
    assert blocos[1].texto == "A hipertensão é comum. O tratamento reduz eventos e a hipertensão mata."


# ----- títulos -----

def test_titulos_numerados_maiusculos_e_quebrados():
    linhas = ["1. INTRODUÇÃO", "Texto da introdução com tamanho suficiente para ser um parágrafo.",
              "", "3. CLASSIFICAÇÃO ESTATÍSTICA INTERNACIONAL DE DOENÇAS E", "PROBLEMAS RELACIONADOS À SAÚDE (CID-10)",
              "I10 - Hipertensão essencial (primária)",
              "5. Início de Tratamento e Metas", "Terapêuticas", "5.1. Início de Tratamento",
              "É discutível se a decisão deve se basear nos níveis pressóricos.",
              "8.7. Hipertensão Arterial e Insuficiência Cardíaca com Fração", "de Ejeção Reduzida",
              "Mais de 90% dos pacientes que desenvolvem IC têm HA, e as"]
    titulos = [b.titulo for b in ig.montar_blocos(linhas) if b.tipo == "h"]
    assert titulos == ["1. INTRODUÇÃO",
                       "3. CLASSIFICAÇÃO ESTATÍSTICA INTERNACIONAL DE DOENÇAS E PROBLEMAS RELACIONADOS À SAÚDE (CID-10)",
                       "5. Início de Tratamento e Metas Terapêuticas", "5.1. Início de Tratamento",
                       "8.7. Hipertensão Arterial e Insuficiência Cardíaca com Fração de Ejeção Reduzida"]


def test_item_de_lista_e_linha_de_tabela_nao_sao_titulo():
    assert not ig._e_titulo_numerado("4. Avaliação do RCV geral, conforme estratificação de risco proposta pela")
    assert not ig._e_titulo_numerado("1 Hipertensão estágio 1")
    assert not ig._e_titulo_numerado("7. OPAS. HEARTS Pacote de medidas técnicas")
    assert not ig._e_titulo_numerado("2.3.1. Genética ..........................30")
    assert ig._e_titulo_numerado("2.3.1. Genética")
    assert not ig._e_titulo_maiusculo("FORTE MODERADA")


def test_frente_sumario_e_referencias_ficam_de_fora():
    linhas = ["Sumário", "1. Introdução ..........................24", "1. INTRODUÇÃO", "Membros: Fulano, Beltrano",
              "1. Introdução", "Corpo da diretriz que interessa ao assistente.",
              "Referências", "1. Silva AB, Souza CD. Um estudo. Arq Bras Cardiol. 2020;1(2):3-4. doi: 10.1/x.",
              "APÊNDICE 1 – METODOLOGIA DE BUSCA E AVALIAÇÃO DA LITERATURA", "Pergunta PICO número um do protocolo."]
    texto = "\n".join(b.texto for b in ig.montar_blocos(linhas))
    assert "Membros" not in texto and "Silva AB" not in texto and "......" not in texto
    assert "Corpo da diretriz" in texto and "Pergunta PICO" in texto


def test_caixa_de_recomendacao_vira_um_bloco():
    linhas = ["1. Introdução", "1.1. Principais Destaques",
              "Recomendações para metas terapêuticas Força da", "recomendação", "Certeza da", "evidência",
              "Recomenda-se a meta de PA < 130/80 mmHg para pacientes com PA 130-139/80-89 mmHg e risco",
              "CV alto. FORTE ALTA",
              "Recomenda-se que, para pacientes que não tolerem a meta, deve-se reduzir a",
              "PA até o valor mais baixo tolerado.", "FORTE MODERADA",
              "CV: cardiovascular; PA: pressão arterial."]
    blocos = ig.montar_blocos(linhas)
    recs = [b.texto for b in blocos if b.tipo == "r"]
    assert recs == ["Recomenda-se a meta de PA < 130/80 mmHg para pacientes com PA 130-139/80-89 mmHg e risco CV alto. "
                    "FORTE ALTA",
                    "Recomenda-se que, para pacientes que não tolerem a meta, deve-se reduzir a PA até o valor mais "
                    "baixo tolerado. FORTE MODERADA"]
    assert [b.titulo for b in blocos if b.tipo == "h"][-1] == "1.1. Principais Destaques › Recomendações para metas terapêuticas"


def test_tabela_fica_com_as_linhas_e_fecha_na_legenda():
    linhas = ["1. Introdução", "Quadro 3.2 – Classificação da pressão arterial", "Classificação da PA PAS (mmHg) PAD (mmHg)",
              "PA normal < 120 e < 80", "HA Estágio 1 140-159 e/ou 90-99",
              "HA: hipertensão arterial; PA: pressão arterial.", "Texto depois da tabela."]
    blocos = ig.montar_blocos(linhas)
    tab = [b for b in blocos if b.tipo == "t"][0]
    assert tab.texto.splitlines()[2] == "PA normal < 120 e < 80" and tab.texto.endswith("pressão arterial.")
    assert blocos[-1].tipo == "p" and blocos[-1].texto == "Texto depois da tabela."


# ----- chunks -----

def _frase(i):
    return f"A frase número {i} fala de pressão arterial, de risco cardiovascular e de metas de tratamento."


def test_chunks_respeitam_o_teto_e_o_minimo():
    blocos = [ig.Bloco("h", "1. Introdução", "1. Introdução")]
    for s in range(12):
        blocos.append(ig.Bloco("h", f"1.{s + 1}. Seção {s + 1}", f"1.{s + 1}. Seção {s + 1}"))
        blocos += [ig.Bloco("p", " ".join(_frase(k) for k in range(6))) for _ in range(1 + s % 3)]
    chunks = ig.montar_chunks(blocos)
    tams = [len(x) for _, x in chunks]
    assert max(tams) <= ig.MAX_CHARS
    assert all(n >= ig.MIN_CHARS for n in tams[:-1])
    assert all(t and t.startswith("1.") for t, _ in chunks)


def test_bloco_gigante_quebra_por_frase_e_tabela_por_linha():
    p = ig.Bloco("p", " ".join(_frase(k) for k in range(60)))
    pedacos = ig._quebra(p)
    assert all(len(x.texto) <= ig.MAX_CHARS for x in pedacos) and all(x.texto.endswith(".") for x in pedacos)
    linhas = [f"Linha {k} da tabela | coluna a | coluna b | coluna c" for k in range(80)]
    t = ig._quebra(ig.Bloco("t", "\n".join(linhas)))
    assert all(len(x.texto) <= ig.MAX_CHARS for x in t)
    assert [y for x in t for y in x.texto.split("\n")] == linhas          # nenhuma linha cortada no meio


def test_recomendacao_e_tabela_nao_se_cortam_entre_chunks():
    rec = ig.Bloco("r", "Recomenda-se " + "x" * 500 + ". FORTE ALTA")
    tab = ig.Bloco("t", "\n".join(f"Linha {k} da tabela com valores" for k in range(20)))
    blocos = [ig.Bloco("h", "2. Metas", "2. Metas"), ig.Bloco("p", " ".join(_frase(k) for k in range(8))), rec, tab]
    textos = [x for _, x in ig.montar_chunks(blocos)]
    assert sum(rec.texto in x for x in textos) == 1
    assert sum(tab.texto in x for x in textos) == 1


def test_titulo_do_chunk_e_a_secao_que_mais_ocupa():
    blocos = [ig.Bloco("h", "1. A", "1. A"), ig.Bloco("p", "Curto."),
              ig.Bloco("h", "2. B", "2. B"), ig.Bloco("p", " ".join(_frase(k) for k in range(6)))]
    (titulo, texto), = ig.montar_chunks(blocos)
    assert titulo == "2. B" and texto.startswith("1. A\nCurto.\n2. B")


def test_processar_hash_do_texto_extraido_e_chunk_de_titulo():
    pags = [_pagina(1, ["1. Introdução"] + [_frase(k) for k in range(15)])] + \
           [_pagina(i, [_frase(k) for k in range(15)]) for i in range(2, 5)]
    fonte = ig.FONTES[0]
    h1, ch = ig.processar(pags, fonte)
    h2, _ = ig.processar(list(pags), fonte)
    assert h1 == h2 and len(h1) == 64
    assert ch[0] == ("Title", fonte["title"])
    assert all("Arq Bras Cardiol" not in x for _, x in ch[1:])


# ----- fontes e download -----

def test_fontes_tem_licenca_url_e_estao_no_sources_yaml():
    yaml = open(ig.os.path.join(ig.os.path.dirname(ig.os.path.dirname(ig.__file__)), "sources.yaml"),
                encoding="utf-8").read()
    for f in ig.FONTES:
        assert f["license"] and f["title"] and f["date"] and f["source"] in ("sbc", "conitec_pcdt")
        assert f["pdf"].startswith("https://") and f["pdf"] in yaml
        assert f["source_type"] == ("guideline" if f["source"] == "sbc" else "protocol")
    assert ig.HOSTS == {"abccardiol.org", "www.gov.br"}


def test_download_recusa_url_fora_da_lista(tmp_path):
    with pytest.raises(ValueError):
        ig.baixar({"slug": "x", "pdf": "https://exemplo.com/x.pdf"}, str(tmp_path))


def test_download_recusa_o_que_nao_e_pdf(tmp_path):
    import httpx
    html = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html>404</html>")))
    with pytest.raises(RuntimeError, match="não é PDF"):
        ig.baixar(ig.FONTES[0], str(tmp_path), cliente=html)
    falso = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"oi")))
    with pytest.raises(RuntimeError, match="%PDF"):
        ig.baixar(ig.FONTES[0], str(tmp_path), cliente=falso)
    ok = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7 ...")))
    assert ig.baixar(ig.FONTES[0], str(tmp_path), cliente=ok).endswith("sbc-hipertensao-2025.pdf")


def test_download_recusa_pdf_grande_demais(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setattr(ig, "MAX_BYTES", 10)
    grande = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-" + b"x" * 50)))
    with pytest.raises(RuntimeError, match="teto"):
        ig.baixar(ig.FONTES[2], str(tmp_path), cliente=grande)


# ----- travas do banco -----

class _Conexao:
    def __init__(self, marcado):
        self.marcado = marcado

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        assert params == ("public.ambiente_de_teste",)
        return self

    def fetchone(self):
        return (self.marcado,)


TESTE = "postgresql://postgres.testeabc:x@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
PROD = "postgresql://postgres.prodxyz:x@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"


def test_prod_exige_sim_producao():
    with pytest.raises(SystemExit, match="--sim-producao"):
        ig.url_do_banco("prod", sim_producao=False, env={}, prod_url=PROD)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        ig.url_do_banco("prod", sim_producao=True, env={}, prod_url="")
    assert ig.url_do_banco("prod", sim_producao=True, env={}, prod_url=PROD) == PROD


def test_cli_prod_sem_flag_para_antes_de_baixar(monkeypatch):
    monkeypatch.setattr(ig, "baixar", lambda *a, **k: pytest.fail("não devia baixar"))
    with pytest.raises(SystemExit):
        ig.main(["--db", "prod", "--embed"])
    with pytest.raises(SystemExit):
        ig.main(["--db", "test"])                                       # --db sem --embed
    with pytest.raises(SystemExit):
        ig.main(["--dry-run", "--embed"])


def test_banco_de_teste_precisa_da_marca():
    with pytest.raises(SystemExit, match="TEST_DATABASE_URL"):
        ig.url_do_banco("test", env={}, prod_url=PROD)
    with pytest.raises(SystemExit, match="mesmo projeto"):
        ig.url_do_banco("test", env={"TEST_DATABASE_URL": PROD}, prod_url=PROD, conectar=lambda *a, **k: _Conexao(True))
    with pytest.raises(SystemExit, match="marca"):
        ig.url_do_banco("test", env={"TEST_DATABASE_URL": TESTE}, prod_url=PROD,
                        conectar=lambda *a, **k: _Conexao(False))
    assert ig.url_do_banco("test", env={"TEST_DATABASE_URL": TESTE}, prod_url=PROD,
                           conectar=lambda *a, **k: _Conexao(True)) == TESTE


class _Documentos:
    """documents de mentira: só responde à consulta do ja_no_banco."""
    def __init__(self, linhas):
        self.linhas = linhas

    def execute(self, sql, params):
        source, h, url = params
        self.achados = [(x,) for s, x, u in self.linhas if s == source and (x == h or u == url)]
        return self

    def fetchall(self):
        return self.achados


def test_ja_no_banco_mesmo_hash_e_outra_versao_da_mesma_url():
    f = ig.FONTES[2]
    assert ig.ja_no_banco(_Documentos([]), f, "h1") is None
    assert ig.ja_no_banco(_Documentos([(f["source"], "h1", f["pdf"])]), f, "h1") == "mesmo"
    assert ig.ja_no_banco(_Documentos([(f["source"], "h0", f["pdf"])]), f, "h1") == "outra versão"
    assert ig.ja_no_banco(_Documentos([("pubmed", "h0", f["pdf"])]), f, "h1") is None


def test_cache_grande_demais_nao_vale_como_pdf(tmp_path, monkeypatch):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.7\n" + b"0" * 100)
    assert ig._e_pdf(str(p))
    monkeypatch.setattr(ig, "MAX_BYTES", 50)
    assert not ig._e_pdf(str(p))


def test_marca_e_a_mesma_do_setup_do_banco_de_testes():
    from scripts import setup_test_db
    assert ig.TEST_MARKER == setup_test_db.TEST_MARKER == "ambiente_de_teste"
