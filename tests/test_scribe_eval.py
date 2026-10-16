"""Avaliação da gravação: o gabarito de cada consulta fictícia é coerente com a própria conversa — uma resposta
perfeita (transcrição = conversa) passa em todos os critérios e não levanta aviso grave. Pega gabarito com
número que ninguém falou, remédio com nome diferente da fala, e conferências que acusam o que está certo."""
import os
import pytest

from app import scribe as s
from app import scribe_eval as e

CASES = e.load_cases()


def perfect(c):
    g, pac = c["gabarito"], c["paciente"]
    segs = [{"seq": i, "at": i * 5, "text": f} for i, (_, f) in enumerate(c["falas"], 1)]
    every = [x["seq"] for x in segs]

    def src(pred):
        return [x["seq"] for x in segs if pred(x["text"])] or every
    meds = []
    for m in g.get("remedios") or []:
        nome = str(m["nome"]).split("|")[0]
        val = lambda k: "" if str(m.get(k, "")) == "*" else str(m.get(k, ""))
        meds.append({"nome": nome, "dose": val("dose"), "posologia": val("posologia"),
                     "acao": "iniciado" if m.get("acao", "*") == "*" else m["acao"].split("|")[0],
                     "src": src(lambda t: s.same_drug(nome, t))})
    vit = {}
    for k, v in (g.get("sinais") or {}).items():
        x = float(str(v).split("|")[0])
        vit[k] = {"v": str(v).split("|")[0].replace(".", ","), "src": src(lambda t: s._has_number(x, s.numbers(t)))}
    frases = [{"t": " ".join(p.split("|")[0].strip() for p in f.split("+")) + ".", "src": every, "tipo": "dito"}
              for f in g.get("fatos") or []]
    out = {"meds": meds, "vitals": vit, "cid": [{"code": str(x).split("|")[0], "src": [1]} for x in g.get("cid") or []],
           "pendencias": ["dose não dita"] if "pendencia" in (g.get("avisos") or []) else []}
    out["soap" if c.get("modo") == "soap" else "livre"] = {"s": frases} if c.get("modo") == "soap" else frases
    patient = {"problems": pac.get("problemas", ""), "medications": pac.get("medicacoes", ""), "allergies": pac.get("alergias", "")}
    return s.check(out, segs, c.get("modo", "soap"), patient)


def test_tem_os_casos_e_eles_sao_ficticios():
    assert len(CASES) >= 30 and len({c["id"] for c in CASES}) == len(CASES)
    assert all(c["paciente"].get("nome") and c["falas"] and c["gabarito"] for c in CASES)


@pytest.mark.parametrize("caso", CASES, ids=[c["id"] for c in CASES])
def test_resposta_perfeita_passa(caso):
    res, flags = perfect(caso)
    sc = e.score(caso, res, flags)
    esperados = set(caso["gabarito"].get("avisos") or [])
    graves = [f for f in flags if (f["nivel"] == "alto" or f["tipo"] in ("dose_longe", "vital_longe")) and f["tipo"] not in esperados]
    assert not graves, graves
    assert sc["rem_certo"] == len(caso["gabarito"].get("remedios") or []), sc["detalhe"]
    assert sc["rem_inventado"] == sc["proibidos"] == sc["avisos_faltando"] == 0, sc["detalhe"]
    assert (sc["vit_certo"], sc["cid_certo"], sc["fatos_ok"]) == (sc["vit_total"], sc["cid_total"], sc["fatos_total"]), sc["detalhe"]


def test_erro_de_palavra_compara_numeros_por_extenso():
    assert e.wer("A pressão está 128 por 82.", "a pressão está cento e vinte e oito por oitenta e dois") == 0


def test_avaliacao_reprova_dose_errada_e_remedio_inventado():
    caso = next(c for c in CASES if c["id"].startswith("02-"))
    res, flags = perfect(caso)
    los = next(m for m in res["meds"] if m["nome"] == "losartana")
    los["dose"] = "50 mg"                                          # a fala diz 100 mg
    res["meds"].append({"nome": "insulina glargina", "dose": "10 UI", "posologia": "", "acao": "iniciado", "src": [1]})
    segs = [{"seq": i, "at": 0, "text": f} for i, (_, f) in enumerate(caso["falas"], 1)]
    pac = caso["paciente"]
    out = {"meds": res["meds"], "soap": {"s": [{"t": x["t"], "src": x["src"], "tipo": "dito"} for x in res["fields"]["s"]]}}
    res2, flags2 = s.check(out, segs, "soap", {"medications": pac["medicacoes"], "allergies": pac["alergias"]})
    sc = e.score(caso, res2, flags2)
    assert sc["rem_certo"] == 2 and sc["rem_aviso"] == 1           # dose errada, mas avisada (é a do cadastro)
    assert sc["rem_inventado"] == 1 and sc["proibidos"] >= 1        # insulina: ninguém falou e é proibida no caso
    assert any(f["tipo"] == "remedio" and "insulina" in f["texto"] for f in flags2)


def test_posologia_por_frequencia_e_dose_incomum():
    assert e.freq("12/12h") == e.freq("duas vezes ao dia") == e.freq("de manhã e no começo da tarde") == 2
    assert e.freq("1x/dia") == e.freq("um comprimido de manhã") == e.freq("à noite") == 1 and e.freq("se dor") is None
    assert s.dose_incomum("ciprofloxacino", "5 mg") and s.dose_incomum("levotiroxina", "75 mg")    # troca de remédio / unidade
    assert not s.dose_incomum("levotiroxina", "75 mcg") and not s.dose_incomum("amoxicilina", "8 ml")
    assert not s.dose_incomum("dipirona", "1 g") and not s.dose_incomum("insulina nph", "20 UI")


def test_cortes_iguais_aos_da_pagina():
    """Blocos de 100 ms; corte depois de 15 s no silêncio de 300 ms (o bloco silencioso fica para o próximo trecho);
    aos 30 s, no bloco mais baixo; silêncio puro não vai para a transcrição; nenhuma amostra se perde."""
    import numpy as np
    rng = np.random.default_rng(2)
    fala = lambda sec: (rng.normal(0, 0.08, int(e.SR * sec))).astype(np.float32)
    pausa = lambda sec: np.zeros(int(e.SR * sec), np.float32)
    a = np.concatenate([fala(18), pausa(0.5), fala(40), pausa(25), fala(10)])
    cs = e.cortes_navegador(a)
    assert cs[0][0] == 0 and cs[-1][1] == len(a) and all(cs[i][1] == cs[i + 1][0] for i in range(len(cs) - 1))
    assert all((y - x) / e.SR <= 30.0001 for x, y, _ in cs) and all((y - x) / e.SR >= 14.9 for x, y, _ in cs[:-1])   # 150 blocos, menos o silencioso
    assert abs(cs[0][1] / e.SR - 18.2) < 0.15                           # 18 s de fala + 2 blocos de pausa
    assert any(m for _, _, m in cs) and not cs[0][2]                     # o trecho só de pausa é silêncio; o primeiro não


def test_cortes_da_avaliacao_usam_os_numeros_da_pagina():
    """A avaliação mede o que a página faz: os números do corte (SEG em web/opendoctor-agenda.html) são os mesmos."""
    import re
    html = open(os.path.join(e.config.ROOT, "web", "opendoctor-agenda.html"), encoding="utf-8").read()
    seg = re.search(r"var SEG = \{([^}]*)\}", html).group(1)
    pagina = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)(?=\s*[,}]|\s*$)", seg)}
    assert {k: pagina.get(k) for k in e.CORTE} == {k: float(v) for k, v in e.CORTE.items()}


def test_vazamento_confere_o_nome_inteiro_e_apelidos():
    assert e.vazamentos("Luiz Carlos Pinto", "O [PACIENTE] e o Carlinhos vieram. Pinto relata dor.") == ["Carlinhos", "Pinto"]
    assert e.vazamentos("Ana Clara Ribeiro", "[PACIENTE], a urina está clara?") == []
    assert e.vazamentos("Ana Clara Ribeiro", "Clara veio sozinha.") == ["Clara"]


def test_nome_partido_e_avisado_conta_como_erro_com_aviso_nao_inventado():
    """A transcrição partiu "trazodona" e saiu "Zodona", marcado como ouvido com dúvida: o médico foi avisado."""
    caso = {"falas": [["m", "Vou começar trazodona 50 mg à noite."]], "gabarito": {"remedios": [
        {"nome": "trazodona", "dose": "50 mg", "posologia": "à noite", "acao": "iniciado"}]}}
    res = {"meds": [{"nome": "Zodona", "dose": "50 mg", "posologia": "à noite", "acao": "iniciado", "src": [1]}],
           "fields": {}, "vitals": {}, "cid": []}
    aviso = [{"tipo": "duvida_grave", "nivel": "alto", "texto": "Zodona: nome do remédio ouvido com dúvida."}]
    assert e.score(caso, res, aviso)["rem_aviso"] == 1 and e.score(caso, res, aviso)["rem_inventado"] == 0
    sem = e.score(caso, res, [])
    assert sem["rem_inventado"] == 1 and sem["rem_falta"] == 1                 # sem aviso continua reprovando
    assert not e._parte_do_nome("trazodona", "insulina glargina") and e._parte_do_nome("trazodona", "Zodona 50 mg")
