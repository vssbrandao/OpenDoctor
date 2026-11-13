"""Quem fala em cada fala da transcrição (app/falante.py, docs/falante-contrato.md) e a rota de troca do rótulo, sem
crédito: o modelo é sempre falso e o banco é o de memória (tests/fake_gravacao.py). Confere a validação estrita da
resposta, o texto original preservado, o mascaramento antes do modelo e a reserva sem rótulo."""
import asyncio
import json
import os
import re
import time

import pytest
from fastapi.testclient import TestClient

from app import auth, config, falante, server
from tests.test_scribe_routes import PAC, REC, UID, fake, hdr, wav  # noqa: F401  (fake é a fixture)

TEXTO = ("Bom dia, dona Maria. Como a senhora passou? Bem, doutora. Estou tomando a losartana certinho! "
         "E a caminhada... conseguiu manter? Mais ou menos.")


def _cortes_json(*cortes):
    return json.dumps({"falas": [{"ate": a, "q": q} for a, q in cortes]})


# ----- frases e montagem: o texto original nunca muda -----
@pytest.mark.parametrize("texto", [TEXTO, "Sem pontuação nenhuma", "  Começa com espaço. E termina com espaço.  ",
                                   "Pergunta?\nResposta na outra linha.", "Ele disse \"pare.\" Depois saiu.", "", "...",
                                   "Pressão 12 por 8. Glicemia 6.9 e 1.200 ml.", ". Começa com ponto. Fim"])
def test_frases_juntas_dao_exatamente_o_texto(texto):
    p = falante.frases(texto)
    assert "".join(p) == texto
    assert all(re.search(r"\w", x) for x in p) or not re.search(r"\w", texto)


def test_frases_cortam_no_fim_de_frase_e_nao_em_numero():
    assert [x.strip() for x in falante.frases("Pressão 12 por 8. Glicemia 6.9 hoje? Sim!")] == \
        ["Pressão 12 por 8.", "Glicemia 6.9 hoje?", "Sim!"]


def test_montar_corta_o_texto_original_e_estima_o_minuto():
    p = falante.frases(TEXTO)
    assert len(p) == 7
    falas = falante.montar(TEXTO, p, [(2, "m"), (4, "p"), (6, "m"), (7, "p")], at=60.0, dur=20.0)
    assert [f["q"] for f in falas] == ["m", "p", "m", "p"]
    assert falas[0]["t"] == "Bom dia, dona Maria. Como a senhora passou?"           # o nome original fica no texto
    assert falas[1]["t"] == "Bem, doutora. Estou tomando a losartana certinho!"
    assert " ".join(f["t"] for f in falas) == TEXTO
    assert falas[0]["at"] == 60.0
    ini = TEXTO.index("Bem, doutora")
    assert falas[1]["at"] == round(60 + ini / len(TEXTO) * 20, 1)
    assert all(falas[i]["at"] < falas[i + 1]["at"] <= 80 for i in range(3))
    assert set(falas[0]) == {"q", "t", "at"}                                          # sem "manual" (só a troca à mão)


def test_montar_recusa_o_que_nao_bate():
    p = falante.frases(TEXTO)
    assert falante.montar(TEXTO, p, [(6, "m")]) is None                                # não cobre tudo
    assert falante.montar(TEXTO + " extra", p, [(7, "m")]) is None                     # os pedaços não dão o texto
    assert falante.montar(TEXTO, p, []) is None


# ----- validação estrita da resposta do modelo -----
@pytest.mark.parametrize("raw", [
    "não é json", "", None, "[]", '{"falas": []}', "{}", '{"falas": [{"ate": 3, "q": "m"}], "extra": 1}',
    _cortes_json((2, "m")),                                     # não cobre as 3 frases
    _cortes_json((2, "m"), (2, "p"), (3, "m")),                 # não cresce
    _cortes_json((2, "m"), (1, "p"), (3, "m")),                 # volta
    _cortes_json((0, "m"), (3, "p")),                           # índice fora (começa em 1)
    _cortes_json((2, "m"), (4, "p")),                           # índice fora (passa do fim)
    _cortes_json((3, "x")),                                     # quem fala desconhecido
    _cortes_json((3, "M")),
    '{"falas": [{"ate": true, "q": "m"}]}',                     # bool não é número
    '{"falas": [{"ate": 3.0, "q": "m"}]}',
    '{"falas": [{"ate": "3", "q": "m"}]}',
    '{"falas": [{"ate": 3, "q": "m", "t": "reescrito"}]}',      # o modelo não devolve texto
    '{"falas": [{"ate": 3}]}', '{"falas": [3]}', '{"falas": "m"}',
    json.dumps({"falas": [{"ate": i, "q": "m"} for i in (1, 2, 3, 3)]}),
])
def test_resposta_ruim_e_recusada(raw):
    assert falante.ler(raw, 3) is None


def test_resposta_boa_e_aceita():
    assert falante.ler(_cortes_json((1, "m"), (3, "p")), 3) == [(1, "m"), (3, "p")]
    assert falante.ler(json.dumps([{"ate": 3, "q": "a"}]), 3) == [(3, "a")]          # lista solta, como no contrato
    assert falante.ler(_cortes_json((1, "m"), (2, "m"), (3, "m")), 3) == [(1, "m"), (2, "m"), (3, "m")]


# ----- o que vai ao modelo: só texto mascarado -----
NOME = "Maria Aparecida Souza"
FALADO = ("Bom dia, dona Maria Aparecida. O CPF é 123.456.789-09 e o telefone 11 98765-4321? "
          "Sim. A Souza aqui sou eu. Meu e-mail é maria.souza@exemplo.com.")


def test_nome_e_documentos_nunca_vao_ao_modelo(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    enviados = []

    def modelo(msgs, model=None):
        enviados.append(msgs)
        return _cortes_json((2, "m"), (5, "p"))
    monkeypatch.setattr(falante, "ask_model", modelo)
    prev = {"text": "Entra, dona Maria Souza.", "falas": [{"q": "m", "t": "Entra, dona Maria Souza.", "at": 0.0},
                                                          {"q": "p", "t": "Obrigada. Meu telefone é 11 91234-5678.", "at": 2.0}]}
    falas = falante.rotular(FALADO, NOME, 30.0, 20.0, prev)
    assert len(enviados) == 1
    prompt = json.dumps(enviados[0], ensure_ascii=False)
    for proibido in ("Maria", "Aparecida", "Souza", "maria.souza", "123.456.789-09", "98765-4321", "91234-5678"):
        assert proibido not in prompt, proibido
    assert "[PACIENTE]" in prompt and "[CPF]" in prompt and "[TELEFONE]" in prompt and "[E-MAIL]" in prompt
    assert "Médico: Entra, dona [PACIENTE]" in prompt                                # o contexto vai com o rótulo
    # as falas guardadas têm o texto ORIGINAL (o prontuário guarda o que foi dito), cortado nas frases
    assert [f["q"] for f in falas] == ["m", "p"]
    assert " ".join(f["t"] for f in falas) == FALADO
    assert "Maria Aparecida" in falas[0]["t"] and falas[0]["at"] == 30.0


def test_contexto_sem_rotulo_usa_o_fim_do_texto_mascarado():
    ctx = falante.contexto({"text": "x" * 500 + " fale, dona Maria Souza.", "falas": []}, NOME)
    assert ctx.startswith("…") and ctx.endswith("fale, dona [PACIENTE].") and len(ctx) <= falante.CONTEXTO_CHARS + 1
    assert falante.contexto(None, NOME) == "" and falante.contexto({"text": "", "falas": []}, NOME) == ""


# ----- reserva: qualquer erro → sem rótulo -----
@pytest.mark.parametrize("resposta", ["não é json", _cortes_json((1, "m")), RuntimeError("OpenAI 500"), TimeoutError()])
def test_erro_do_modelo_fica_sem_rotulo(monkeypatch, resposta):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")

    def modelo(msgs, model=None):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    monkeypatch.setattr(falante, "ask_model", modelo)
    assert falante.rotular(TEXTO, NOME, 0, 20) == []


def test_sem_chave_ou_sem_texto_nao_chama_o_modelo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(falante, "ask_model", lambda *a, **k: chamadas.append(1) or _cortes_json((7, "m")))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert falante.rotular(TEXTO, NOME) == []
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    assert falante.rotular("   ", NOME) == [] and falante.rotular("Frase. " * (falante.MAX_FRASES + 1), NOME) == []
    assert chamadas == []
    assert falante.rotular(TEXTO, NOME) and chamadas == [1]


def test_log_do_rotulador_so_leva_numeros(monkeypatch, capsys):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    monkeypatch.setattr(falante, "ask_model", lambda *a, **k: _cortes_json((2, "m"), (5, "p")))
    assert falante.rotular(FALADO, NOME)
    monkeypatch.setattr(falante, "ask_model", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("OpenAI 500: " + FALADO)))
    falante.rotular(FALADO, NOME)
    out = capsys.readouterr().out
    assert "[falante]" in out and "Maria" not in out and "dona" not in out and "500" not in out


def test_chamada_usa_o_modelo_barato_em_json(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    pedidos = []

    class R:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": _cortes_json((1, "m"))}}], "usage": {"prompt_tokens": 10}}

    def post(url, headers=None, json=None, timeout=None):
        pedidos.append((url, json, timeout))
        return R()
    monkeypatch.setattr(httpx, "post", post)                     # nada sai para a OpenAI
    out = falante.chamar(falante.build_messages(["Oi."]))
    url, body, timeout = pedidos[0]
    assert body["model"] == config.OPENAI_FALANTE_MODEL and body["response_format"] == {"type": "json_object"}
    assert timeout <= 10 and out == {"raw": _cortes_json((1, "m")), "usage": {"prompt_tokens": 10}}


def test_modelo_padrao_e_o_barato():
    assert config.OPENAI_FALANTE_MODEL == os.environ.get("OPENAI_FALANTE_MODEL", "gpt-5.4-mini")


# ----- na rota da transcrição -----
def test_transcricao_grava_as_falas_e_o_estado_devolve(fake):
    c = TestClient(server.app)
    r = c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)).json()
    assert r["falas"] == [{"q": "m", "t": "Pressão 128 por 82, frequência 74.", "at": 0.0}]
    assert fake.segs[(REC, 1)]["falas"] == r["falas"]
    again = c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)).json()
    assert again["repetido"] and again["falas"] == r["falas"] and len(fake.falante) == 1    # reenvio não rotula de novo
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2))
    ctx = fake.falante[1][-1]["content"]
    assert "Médico: Pressão 128 por 82" in ctx                    # o trecho anterior com o rótulo, como contexto
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"][0]
    assert [s["falas"][0]["at"] for s in st["segments"]] == [0.0, 20.0]
    assert all("Maria" not in json.dumps(m, ensure_ascii=False) for m in fake.falante)


def test_rotulador_que_falha_nao_derruba_a_transcricao(fake, monkeypatch):
    monkeypatch.setattr(falante, "ask_model", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fora")))
    r = TestClient(server.app).post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert r.status_code == 200 and r.json()["falas"] == [] and r.json()["text"]
    assert fake.segs[(REC, 1)]["falas"] == [] and fake.segs[(REC, 1)]["text"]


def test_rotulador_lento_passa_do_teto_e_fica_sem_rotulo(fake, monkeypatch):
    async def lento(*a, **k):
        await asyncio.sleep(5)
        return [{"q": "m", "t": "x", "at": 0}]
    monkeypatch.setattr(falante, "arotular", lento)
    monkeypatch.setattr(server, "FALANTE_TETO_S", 0.05)
    t0 = time.time()
    r = TestClient(server.app).post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert r.status_code == 200 and r.json()["falas"] == [] and time.time() - t0 < 3
    assert server.FALANTE_TETO_S == 0.05 and fake.segs[(REC, 1)]["falas"] == []


def test_teto_do_rotulador_e_8_segundos():
    assert server.FALANTE_TETO_S == 8


def test_sem_a_migracao_0023_a_transcricao_segue_sem_rotulo(fake):
    fake.sem_falas = True
    c = TestClient(server.app)
    assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)).status_code == 200
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"][0]
    assert st["segments"][0]["falas"] == []
    r = c.post("/prontuario/recordings/fala", json={"patient_id": 7, "rec_id": REC, "seq": 1, "i": 0, "q": "p"})
    assert r.status_code == 503


# ----- troca do rótulo à mão: POST /prontuario/recordings/fala -----
FALA = "/prontuario/recordings/fala"


def _corpo(**kw):
    b = {"patient_id": 7, "rec_id": REC, "seq": 1, "i": 0, "q": "p"}
    b.update(kw)
    return {k: v for k, v in b.items() if v is not None}


def test_troca_sem_login_401(fake, monkeypatch):
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    assert c.post(FALA, json=_corpo()).status_code == 401
    assert fake.segs[(REC, 1)]["falas"][0]["q"] == "m"


@pytest.mark.parametrize("ruim", [{"q": "x"}, {"q": "M"}, {"q": None}, {"q": ["p"]}, {"i": -1}, {"i": "0"}, {"i": True},
                                  {"i": 1.0}, {"i": None}, {"seq": 0}, {"seq": "1"}, {"seq": None}, {"rec_id": "abc"},
                                  {"rec_id": REC + "x"}, {"rec_id": None}, {"patient_id": None}, {"patient_id": "abc"},
                                  {"patient_id": 8}])          # 8: paciente de outro médico (ou que não existe)
def test_troca_com_dados_ruins_400(fake, ruim):
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert c.post(FALA, json=_corpo(**ruim)).status_code == 400
    assert fake.segs[(REC, 1)]["falas"][0]["q"] == "m" and ("recording_edit", 7, None) not in fake.log


def test_troca_so_numa_fala_que_existe_404(fake):
    c = TestClient(server.app)
    assert c.post(FALA, json=_corpo()).status_code == 404                     # gravação ainda não existe
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert c.post(FALA, json=_corpo(i=1)).status_code == 404                  # só há a fala 0
    assert c.post(FALA, json=_corpo(seq=2)).status_code == 404                # trecho que não existe
    assert c.post(FALA, json=_corpo(rec_id="6dff997e-a076-444e-9db4-403c512c0000")).status_code == 404
    assert ("recording_edit", 7, None) not in fake.log


def test_troca_so_do_dono_e_do_paciente(fake):
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    fake.recs[REC]["uid"] = "outro-medico"                                  # a gravação é de outro médico
    assert c.post(FALA, json=_corpo()).status_code == 404
    fake.recs[REC].update(uid=UID, pid=99)                                  # do médico, mas de outro paciente
    assert c.post(FALA, json=_corpo()).status_code == 404
    assert fake.segs[(REC, 1)]["falas"][0]["q"] == "m"
    fake.recs[REC]["pid"] = 7
    r = c.post(FALA, json=_corpo(q="a"))
    assert r.status_code == 200 and r.json() == {"ok": True, "falas": [
        {"q": "a", "t": "Pressão 128 por 82, frequência 74.", "at": 0.0, "manual": True}]}
    assert fake.segs[(REC, 1)]["falas"][0] == {"q": "a", "t": "Pressão 128 por 82, frequência 74.", "at": 0.0, "manual": True}
    assert ("recording_edit", 7, None) in fake.log                          # fica no histórico de acessos
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"][0]
    assert st["segments"][0]["falas"][0]["manual"] is True


def test_troca_tem_limite_por_conta(fake, monkeypatch):
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    monkeypatch.setitem(server.RATE_LIMITS, "fala", (2, 600))
    assert [c.post(FALA, json=_corpo(q=q)).status_code for q in "pma"] == [200, 200, 429]


def test_rota_da_troca_e_privada():
    """Dentro de /prontuario/: fechada por padrão (nunca em PUBLIC_*)."""
    assert FALA not in server.PUBLIC_PATHS and not any(FALA.startswith(x) for x in server.PUBLIC_PREFIXES)
    assert TestClient(server.app).post(FALA, json=_corpo()).status_code in (401, 302, 303)


def test_migracao_0023_aditiva_e_idempotente():
    sql = open(os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations", "0023_falantes.sql"),
               encoding="utf-8").read()
    linhas = [x for x in (l.split("--")[0].strip() for l in sql.splitlines()) if x]
    assert "alter table recording_segments add column if not exists falas jsonb not null default '[]'::jsonb;" in linhas
    assert not re.search(r"\b(drop|delete|truncate|update)\b", " ".join(linhas), re.I)


# ----- scripts/falante_eval.py sem crédito (a chamada ao modelo é falsa) -----
def test_avaliacao_monta_trechos_e_compara_sem_chamar_nada(monkeypatch):
    from app import scribe_eval
    from scripts import falante_eval as fe
    caso = next(c for c in scribe_eval.load_cases(["04"]))                    # pediatria: tem acompanhante
    trs = fe.trechos(caso)
    assert trs and all(t["dur"] <= fe.SEG_MAX + 1e-6 for t in trs) and all(t["dur"] >= fe.SEG_MIN for t in trs[:-1])
    juntos = " ".join(t["text"] for t in trs)
    assert juntos == " ".join(" ".join(x.strip() for x in falante.frases(str(f).strip())) for _, f in caso["falas"])
    assert "Médico" not in juntos and not any(t["text"].startswith(("m:", "p:", "a:")) for t in trs)   # sem rótulo
    enviados = []

    def perfeito(msgs, model=None, timeout=None):                       # devolve a referência: acerto de 100%
        enviados.append(msgs)
        tr = next(t for t in trs if falante.preparar(t["text"], caso["paciente"]["nome"])[1][-1]["content"].split(
            "Frases deste trecho:")[1] == msgs[-1]["content"].split("Frases deste trecho:")[1])
        ped, pos, cortes = falante.frases(tr["text"]), 0, []
        for i, p in enumerate(ped, 1):
            q = next(q for a, b, q, _ in tr["ref"] if a <= pos < b)
            pos += len(p)
            if cortes and cortes[-1]["q"] == q:
                cortes[-1]["ate"] = i
            else:
                cortes.append({"ate": i, "q": q})
        return {"raw": json.dumps({"falas": cortes}), "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}
    monkeypatch.setattr(falante, "chamar", perfeito)
    res = fe.roda_caso(caso, "gpt-5.4-mini", teto=1.0)
    m = fe.soma_matriz([t["matriz"] for t in res["trechos"]])
    assert len(enviados) == len(trs) and fe.acerto(m) == 1.0 and sum(m["a"].values()) > 0
    assert all(t["falas_ok"] == t["falas_n"] for t in res["trechos"]) and all(not t["vazamentos"] for t in res["trechos"])
    assert fe.custo("gpt-5.4-mini", {"prompt_tokens": 1000, "completion_tokens": 100}) == pytest.approx((1000 * 0.75 + 100 * 4.5) / 1e6)
    errado = fe.comparar(trs[0], [])                                    # sem rótulo: tudo na coluna "sem"
    assert sum(errado[0][q]["sem"] for q in "mpa") == sum(sum(v.values()) for v in errado[0].values())


def test_dry_run_da_avaliacao_nao_chama_nada(monkeypatch, capsys):
    from scripts import falante_eval as fe
    monkeypatch.setattr(falante, "chamar", lambda *a, **k: pytest.fail("o dry-run chamou o modelo"))
    assert fe.main(["--dry-run", "--max-casos", "2"]) == 0
    out = capsys.readouterr().out
    assert "2 casos" in out and "chamadas" in out and "US$" in out and "nada foi chamado" in out


# ----- revisão de 13/11/2026: o nome que também é palavra comum não pode escapar da máscara ao cortar as frases -----
def test_nome_comum_depois_de_tratamento_nao_vaza():
    txt = "A sra. Rosa voltou hoje? O Sr. Dias melhorou. Rosa, sente dor?"
    ped, msgs = falante.preparar(txt, "Rosa Dias")
    assert "".join(ped) == txt
    prompt = "\n".join(m["content"] for m in msgs)
    assert "Rosa" not in prompt and "Dias" not in prompt


def test_nome_no_comeco_do_trecho_depois_de_sra_no_anterior():
    ped, msgs = falante.preparar("Rosa voltou a sentir tontura.", "Rosa Dias", prev={"text": "Bom dia, sra.", "falas": []})
    prompt = "\n".join(m["content"] for m in msgs)
    assert "Rosa" not in prompt


def test_contexto_mascara_com_a_fala_anterior():
    ctx = falante.contexto({"falas": [{"q": "m", "t": "Bom dia, sra."}, {"q": "p", "t": "Rosa aqui, doutor."}]}, "Rosa Dias")
    assert "Rosa" not in ctx and "Paciente:" in ctx
