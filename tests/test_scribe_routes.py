"""Rotas da gravação da consulta (transcrever, estado, gerar, apagar) com banco em memória e transcritor/modelo
falsos: nada sai para a OpenAI nem toca banco."""
import json
import struct

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, scribe, server, stt
from tests.fake_gravacao import FakeGravacao
from tests.fake_receitas import FakeReceitas

UID = "00000000-0000-0000-0000-0000000000aa"
REC = "6dff997e-a076-444e-9db4-403c512c010c"
PAC = {"id": 7, "name": "Maria Silva", "key": "maria silva", "example": False, "birth_date": "1968-03-14", "sex": "F",
       "cpf": None, "phone": None, "allergies": "Dipirona", "problems": "Hipertensão arterial\nDiabetes tipo 2",
       "medications": "Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia"}


def wav(seconds, rate=16000, channels=1):
    n = int(seconds * rate) * channels
    data = struct.pack("<%dh" % n, *([300, -300] * (n // 2)))
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * 2 * channels, 2 * channels, 16)
            + b"data" + struct.pack("<I", len(data)) + data)


class FakeDB(FakeGravacao):
    """O banco da gravação em memória (tests/fake_gravacao.py, o mesmo do preview) + o resto que as rotas leem."""
    def __init__(self):
        super().__init__()
        self.log, self.today, self.outro = [], 0.0, {}     # outro: consulta → paciente dono da evolução dela

    def install(self, mp):
        super().install(mp.setattr)
        for name in ("get_patient", "rec_seconds_today", "recent_notes", "list_notes", "log_access", "last_note_content",
                     "event_note_other_patient"):
            mp.setattr(db, name, getattr(self, name))

    def event_note_other_patient(self, uid, eid, pid, key):
        return uid == UID and eid in self.outro and self.outro[eid] != pid

    def get_patient(self, uid, pid):
        return dict(PAC) if uid == UID and pid == PAC["id"] else None

    def rec_seconds_today(self, uid):              # o teto diário é testado mexendo direto neste número
        return self.today

    def recent_notes(self, uid, limit=30):
        return [{"content": "S: HAS controlada. PA 130x80. Mantido.", "data": {"mode": "soap"}}]

    def list_notes(self, uid, pid, key):
        return [{"id": 1, "event_id": "ev0", "content": "Maria Silva refere boa adesão. Losartana 50 mg.", "data": {"mode": "free"}}]

    def last_note_content(self, uid, pid, nid=None, eid=None):
        return next((n["content"] for n in self.list_notes(uid, pid, None) if n["id"] != nid and n["event_id"] != eid), "")

    def log_access(self, uid, action, pid=None, nid=None, dedupe_minutes=0):
        self.log.append((action, pid, nid))


@pytest.fixture
def fake(monkeypatch):
    f = FakeDB(); f.install(monkeypatch)
    FakeReceitas().install(monkeypatch.setattr)                   # a gravação também preenche o rascunho da receita
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": UID, "email": "medica@exemplo.com", "sv": 0})
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_ALL", False)
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    f.calls = []

    async def atranscribe(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
        f.calls.append({"bytes": len(audio), "prompt": prompt, "keywords": keywords})
        n = len(f.calls)
        return {"text": ["Pressão 128 por 82, frequência 74.", "Vamos manter a losartana 50 mg de 12 em 12 horas."][min(n, 2) - 1],
                "raw": "", "usage": {}, "duvidas": ["74"] if n == 1 else [], "confianca": 0.9}
    monkeypatch.setattr(stt, "atranscribe", atranscribe)
    server._RL.clear()
    return f


def hdr(seq=1, **kw):
    h = {"Content-Type": "audio/wav", "X-Patient-Id": "7", "X-Rec-Id": REC, "X-Seq": str(seq), "X-At": str((seq - 1) * 20.0),
         "X-Event-Id": "ev9", "X-Consent": "2026-10-15T10:00:00.000Z"}
    h.update(kw)
    return {k: v for k, v in h.items() if v is not None}


def test_transcrever_so_para_conta_liberada(fake, monkeypatch):
    c = TestClient(server.app)
    monkeypatch.setattr(config, "SCRIBE_EMAILS", set())
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr()).status_code == 403
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_OFF", True)           # desligado: 503, a página guarda e tenta depois
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr()).status_code == 503
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr()).status_code == 503
    assert fake.calls == []


def test_transcrever_exige_identificacao_autorizacao_e_paciente_do_medico(fake):
    c = TestClient(server.app)
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr(**{"X-Rec-Id": "abc"})).status_code == 400
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr(**{"X-Seq": "0"})).status_code == 400
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr(**{"X-Consent": None})).status_code == 400
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr(**{"X-Patient-Id": "8"})).status_code == 400
    assert fake.calls == [] and fake.segs == {}


def test_transcrever_so_aceita_o_wav_da_pagina(fake, monkeypatch):
    c = TestClient(server.app)
    assert c.post("/prontuario/transcribe", content=b"%PDF-1.4 nada", headers=hdr()).status_code == 415
    assert c.post("/prontuario/transcribe", content=wav(1, rate=48000), headers=hdr()).status_code == 415
    assert c.post("/prontuario/transcribe", content=wav(1, channels=2), headers=hdr()).status_code == 415
    assert c.post("/prontuario/transcribe", content=wav(61), headers=hdr()).status_code == 413
    monkeypatch.setattr(server, "MAX_SEG_BYTES", 1000)
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr()).status_code == 413
    assert fake.calls == []


def test_transcrever_guarda_o_texto_e_reenvio_nao_cobra_de_novo(fake):
    c = TestClient(server.app)
    r = c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert r.status_code == 200 and r.json() == {"ok": True, "text": "Pressão 128 por 82, frequência 74.", "duvidas": ["74"]}
    assert fake.segs[(REC, 1)]["dur"] == 20 and fake.recs[REC]["consent_at"] == "2026-10-15T10:00:00.000Z"
    assert fake.recs[REC]["event_id"] == "ev9" and ("recording", 7, None) in fake.log
    again = c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)).json()
    assert again["repetido"] and again["text"] == "Pressão 128 por 82, frequência 74." and len(fake.calls) == 1
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2))
    second = fake.calls[1]
    assert second["prompt"] == "Pressão 128 por 82, frequência 74."      # o fim do trecho anterior dá contexto
    assert "Losartana" in second["keywords"] and not any("Maria" in k for k in second["keywords"])
    assert fake.recs[REC]["seconds"] == 40


def test_transcrever_respeita_o_teto_diario_e_o_dono_da_gravacao(fake):
    c = TestClient(server.app)
    fake.today = 6 * 3600 - 10
    assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr()).status_code == 429
    fake.today = 0
    fake.recs[REC] = {"uid": "outro", "pid": 7, "event_id": None, "note_id": None, "consent_at": None, "status": "gravando", "seconds": 0}
    assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr()).status_code == 404
    assert fake.calls == []


def test_transcricao_que_falha_nao_guarda_nada(fake, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("transcrição 500: erro")
    monkeypatch.setattr(stt, "atranscribe", boom)
    r = TestClient(server.app).post("/prontuario/transcribe", content=wav(20), headers=hdr())
    assert r.status_code == 502 and fake.segs == {}           # 502: a página tenta de novo


def _lines(r):
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def _record(fake, c):
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2))


SAIDA = {"soap": {"s": [], "o": [{"t": "PA 128x82 mmHg, FC 74 bpm.", "src": [1], "tipo": "dito"}], "a": [],
                  "p": [{"t": "Mantida losartana 50 mg 12/12h.", "src": [2], "tipo": "dito"}]},
         "livre": [], "vitals": {"pa_s": {"v": "128", "src": [1]}, "pa_d": {"v": "82", "src": [1]}, "fc": {"v": "74", "src": [1]}},
         "cid": [{"code": "I10", "src": [2]}],
         "meds": [{"nome": "losartana", "dose": "50 mg", "posologia": "12/12h", "acao": "mantido", "src": [2]}],
         "exames": [], "pendencias": []}


def test_gerar_evolucao_mascara_o_nome_e_confere_sem_ia(fake, monkeypatch):
    c = TestClient(server.app)
    _record(fake, c)
    sent = []
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: sent.append(msgs) or json.dumps(SAIDA))
    r = c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ls = _lines(r)
    assert ls[0]["step"] == "escrevendo" and {"step": "conferindo"} in ls
    out = ls[-1]
    assert out["ok"] and out["result"]["fields"]["o"] == "PA 128x82 mmHg, FC 74 bpm."
    assert out["result"]["fields_src"] == {"s": [], "o": [1], "a": [], "p": [2]}   # de que trecho veio cada parte (os destaques)
    assert out["result"]["vitals"] == {"pa_s": "128", "pa_d": "82", "fc": "74"} and out["result"]["cid"][0]["code"] == "I10"
    assert [t["seq"] for t in out["segs"]] == [1, 2] and out["segs"][0]["rec_id"] == REC
    assert any(f["tipo"] == "duvida_grave" for f in out["flags"])          # o 74 foi ouvido com dúvida
    assert out["meta"]["prompt"] == scribe.PROMPT_VERSION and out["meta"]["rec_ids"] == [REC] and out["meta"]["segundos"] == 40
    texto = json.dumps(sent[0], ensure_ascii=False)
    assert "Maria" not in texto and "[PACIENTE]" in texto                   # nem a última evolução leva o nome
    assert fake.recs[REC]["status"] == "gerada" and ("scribe", 7, None) in fake.log
    # o remédio que a gravação extraiu foi para o rascunho da receita desta consulta, para revisar; gerar de novo não repete
    assert out["receita"] == 1
    (rx,) = db.list_receitas(UID, 7)
    assert rx["status"] == "rascunho" and rx["event_id"] == "ev9" and rx["itens"][0]["nome"] == "Losartana"
    assert rx["itens"][0]["origem"] == "gravacao" and rx["itens"][0]["continuo"] is True
    assert _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"}))[-1]["receita"] == 0


def test_gerar_avisa_quando_a_ia_falha_ou_nao_ha_trechos(fake, monkeypatch):
    c = TestClient(server.app)
    assert c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "mode": "soap"}).status_code == 400
    _record(fake, c)

    def boom(msgs, model=None):
        raise RuntimeError("OpenAI 503")
    monkeypatch.setattr(scribe, "ask_model", boom)
    ls = _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "mode": "soap"}))
    assert "error" in ls[-1] and fake.recs[REC]["status"] == "gravando"
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: "isto não é JSON")
    ls = _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "mode": "soap"}))
    assert "error" in ls[-1]


def test_estado_da_gravacao_e_apagar_transcricao(fake):
    c = TestClient(server.app)
    _record(fake, c)
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"]
    assert st[0]["rec_id"] == REC and [s["seq"] for s in st[0]["segments"]] == [1, 2] and st[0]["seconds"] == 40
    assert c.post("/prontuario/recordings/state", json={"patient_id": 7, "rec_ids": [REC]}).json()["recordings"][0]["rec_id"] == REC
    assert c.post("/prontuario/recordings/state", json={"patient_id": 7}).json()["recordings"] == []
    assert c.delete("/prontuario/recordings/nao-e-uuid").status_code == 404
    assert c.delete("/prontuario/recordings/" + REC).json() == {"ok": True} and ("recording_delete", 7, None) in fake.log
    assert c.delete("/prontuario/recordings/" + REC).status_code == 404


def test_evolucao_guarda_so_o_rastreio_da_gravacao():
    d = server._note_data({"mode": "soap", "s": "x", "scribe": {
        "rec_ids": [REC, "nao-e-uuid"], "prompt": "2026-10-15.5", "model": "gpt-5.4", "consent_at": "2026-10-15T10:00:00Z",
        "generated_at": "2026-10-15T10:20:00Z", "pontos": {"alto": 1, "medio": 3, "info": "x"}, "conferidos": 2, "segundos": 912,
        "conf_idx": [3, 0, 3, -1, True, "2"], "gen_s": 14,
        "texto": "transcrição inteira não pode entrar aqui"}})
    assert d["scribe"] == {"rec_ids": [REC], "prompt": "2026-10-15.5", "model": "gpt-5.4", "consent_at": "2026-10-15T10:00:00Z",
                           "generated_at": "2026-10-15T10:20:00Z", "pontos": {"alto": 1, "medio": 3}, "segundos": 912, "conferidos": 2,
                           "conf_idx": [0, 3], "gen_s": 14}
    assert server._note_data({"mode": "free", "scribe": {"gen_s": True}})["scribe"]["gen_s"] == 0
    assert server._note_data({"mode": "free", "scribe": {"gen_s": 99999}})["scribe"]["gen_s"] == 0
    assert "scribe" not in server._note_data({"mode": "free"})


def test_duracao_do_wav():
    assert server._wav_seconds(wav(2)) == 2 and server._wav_seconds(wav(1, rate=8000)) is None
    assert server._wav_seconds(b"RIFF") is None and server._wav_seconds(wav(1)[:44]) is None


def test_geracao_fica_guardada_para_revisar_depois(fake, monkeypatch):
    """Recarregou a página ou voltou noutro dia: a evolução gerada e os pontos para conferir voltam."""
    c = TestClient(server.app)
    _record(fake, c)
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: json.dumps(SAIDA))
    out = _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap", "espera_s": 4}))[-1]
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"][0]
    assert st["status"] == "gerada" and st["scribe"]["generated_at"] == out["meta"]["generated_at"]
    assert st["scribe"]["gen_s"] == out["meta"]["gen_s"] >= 4          # tempo até a evolução pronta volta ao recarregar
    assert st["scribe"]["saida"]["flags"] == out["flags"] and st["scribe"]["saida"]["result"]["fields"] == out["result"]["fields"]
    assert st["scribe"]["saida"]["segs"] == out["segs"]


def test_consulta_avulsa_acha_a_gravacao_sem_consulta_nem_evolucao(fake):
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1, **{"X-Event-Id": None}))
    assert c.post("/prontuario/recordings/state", json={"patient_id": 7}).json()["recordings"] == []
    achou = c.post("/prontuario/recordings/state", json={"patient_id": 7, "orfas": True}).json()["recordings"]
    assert [r["rec_id"] for r in achou] == [REC]
    # numa consulta da agenda, a gravação avulsa não aparece
    assert c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9", "orfas": True}).json()["recordings"] == []


def test_mesmo_trecho_ao_mesmo_tempo_e_transcrito_uma_vez(fake, monkeypatch):
    """Duas abas abertas, ou o reenvio depois de o Cloudflare cortar em 100 s: um pedido espera o outro (não cobra 2x)."""
    import asyncio
    import httpx
    calls = []

    async def lento(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
        calls.append(1); await asyncio.sleep(0.3)
        return {"text": "Pressão 128 por 82.", "raw": "", "usage": {}, "duvidas": ["82"], "confianca": 0.9}
    monkeypatch.setattr(stt, "atranscribe", lento)

    async def dois():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            return await asyncio.gather(*[c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)) for _ in range(2)])
    rs = asyncio.run(dois())
    assert len(calls) == 1 and [r.status_code for r in rs] == [200, 200]
    assert {r.json()["text"] for r in rs} == {"Pressão 128 por 82."} and not server._EM_ANDAMENTO

    async def falha(audio, *a, **kw):
        calls.append(1); await asyncio.sleep(0.3); raise RuntimeError("fora do ar")
    calls.clear()
    monkeypatch.setattr(stt, "atranscribe", falha)
    async def dois_falham():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://t") as c:
            return await asyncio.gather(*[c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2)) for _ in range(2)])
    assert [r.status_code for r in asyncio.run(dois_falham())] == [502, 502] and len(calls) == 1 and not server._EM_ANDAMENTO


def test_contexto_da_transcricao_vai_sem_documentos(fake, monkeypatch):
    sent = []

    async def atr(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
        sent.append(prompt)
        return {"text": "Bom dia, dona Maria Silva. CPF 123.456.789-09, celular 98877-6655.", "raw": "", "usage": {},
                "duvidas": [], "confianca": 0.9}
    monkeypatch.setattr(stt, "atranscribe", atr)
    c = TestClient(server.app)
    for seq in (1, 2):
        assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr(seq)).status_code == 200
    assert sent[1] == "Bom dia, dona Maria Silva. CPF [CPF], celular [TELEFONE]."     # o nome fica: o áudio já o tem
    assert fake.segs[(REC, 1)]["text"].endswith("98877-6655.")                       # o prontuário guarda o texto inteiro


def test_orfas_so_em_consulta_sem_agenda_e_sem_evolucao():
    assert server._rec_where({"orfas": True})[3] is True
    assert server._rec_where({"orfas": True, "note_id": 12})[3] is False                 # já tem evolução: acha por ela
    assert server._rec_where({"orfas": True, "event_id": "ev1"})[3] is False


def test_salvar_a_evolucao_liga_a_gravacao_da_consulta(fake, monkeypatch):
    ligou = []
    monkeypatch.setattr(db, "upsert_note", lambda *a, **k: 55)
    monkeypatch.setattr(db, "touch_patient", lambda *a, **k: None)
    monkeypatch.setattr(db, "rec_link_orphans", lambda uid, pid, rids, nid: ligou.append((pid, tuple(rids), nid)))
    c = TestClient(server.app)
    r = c.post("/prontuario/notes", json={"patient_id": 7, "content": "S: dor lombar", "data": {"mode": "free"},
                                          "rec_ids": [REC, "nao-e-uuid"]})
    assert r.json() == {"ok": True, "id": 55} and ligou == [(7, (REC,), 55)]
    c.post("/prontuario/notes", json={"patient_id": 7, "content": "S: x", "data": {"mode": "free"}})
    assert len(ligou) == 1                                                               # sem gravação: nada a ligar


def test_gravacao_nao_entra_na_consulta_com_evolucao_de_outro_paciente(fake, monkeypatch):
    """O paciente do evento foi trocado (Ana → Maria) com a evolução da Ana escrita: nem o trecho nem a geração entram
    nessa consulta — nada vai ao transcritor, ao modelo ou à receita."""
    c = TestClient(server.app)
    fake.outro = {"ev9": 99}                                        # a evolução da consulta ev9 é de outro paciente (99)
    r = c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1))
    assert r.status_code == 409 and r.json()["other_patient"] is True
    assert fake.calls == [] and fake.recs == {} and fake.segs == {}
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: pytest.fail("foi ao modelo"))
    r = c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"})
    assert r.status_code == 409 and r.json()["other_patient"] is True and db.list_receitas(UID, 7) == []
    fake.outro = {"ev9": 7}                                         # a evolução é desta paciente: grava normal
    assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1)).status_code == 200
    assert c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2, **{"X-Event-Id": None})).status_code == 200


SAIDA_2 = dict(SAIDA, meds=SAIDA["meds"] + [{"nome": "metformina", "dose": "850 mg", "posologia": "2x/dia", "acao": "mantido", "src": [2]}])


def test_gerar_de_novo_nao_desfaz_o_que_o_medico_fez_na_receita(fake, monkeypatch):
    """Gerar de novo não traz de volta o remédio que o médico tirou do rascunho nem abre rascunho depois de emitida;
    remédio novo (de um trecho que chegou depois) ainda entra no rascunho."""
    c = TestClient(server.app)
    _record(fake, c)
    saida = [SAIDA]
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: json.dumps(saida[0]))

    def gera():
        return _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"}))[-1]
    assert gera()["receita"] == 1
    (rx,) = db.list_receitas(UID, 7)
    db.update_receita(UID, rx["id"], [])                            # o médico tirou a losartana
    assert gera()["receita"] == 0 and db.get_receita(UID, rx["id"])["itens"] == []
    saida[0] = SAIDA_2
    assert gera()["receita"] == 1                                   # a metformina é nova: entra; a losartana não volta
    assert [i["nome"] for i in db.get_receita(UID, rx["id"])["itens"]] == ["Metformina"]
    db.emit_receita(UID, rx["id"], [("simples", db.get_receita(UID, rx["id"])["itens"])])
    saida[0] = dict(SAIDA_2, meds=SAIDA_2["meds"] + [{"nome": "atorvastatina", "dose": "20 mg", "posologia": "à noite",
                                                      "acao": "iniciado", "src": [2]}])
    assert gera()["receita"] == 0                                   # emitida: não abre outro rascunho sozinho
    assert [r["status"] for r in db.list_receitas(UID, 7)] == ["emitida"]


def test_gerar_de_novo_lembra_os_remedios_de_todas_as_geracoes(fake, monkeypatch):
    """O modelo varia: a 1ª geração cita a losartana, a 2ª não, a 3ª cita de novo — o remédio que o médico tirou
    continua fora. E uma geração sem evolução válida não mexe na receita."""
    c = TestClient(server.app)
    _record(fake, c)
    saida = [SAIDA]
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: json.dumps(saida[0]))

    def gera():
        return _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"}))[-1]
    assert gera()["receita"] == 1
    (rx,) = db.list_receitas(UID, 7)
    db.update_receita(UID, rx["id"], [])                            # o médico tirou a losartana
    saida[0] = dict(SAIDA, meds=[])
    assert gera()["receita"] == 0                                   # esta não cita a losartana
    saida[0] = SAIDA
    assert gera()["receita"] == 0 and db.get_receita(UID, rx["id"])["itens"] == []   # citada de novo: não volta
    for _ in range(3):
        gera()
    assert fake.recs[REC]["scribe"]["receita_meds"] == ["Losartana"]  # lembrada uma vez só: a lista não cresce
    duas = [{"scribe": {"receita_meds": ["Losartana", "Metformina", "D3"]}}] * 2   # duas gravações, a mesma lista
    assert server._lembrados(server._meds_gerados(duas) + ["metformina", "D3"]) == ["Losartana", "Metformina", "D3"]

    db.update_receita(UID, rx["id"], [])
    vazia = {"soap": {"s": [], "o": [], "a": [], "p": []}, "livre": [], "vitals": {}, "cid": [], "exames": [], "pendencias": [],
             "meds": [{"nome": "atorvastatina", "dose": "20 mg", "posologia": "à noite", "acao": "iniciado", "src": [2]}]}
    saida[0] = vazia
    assert "error" in gera()                                        # sem evolução: a receita fica como estava
    assert db.get_receita(UID, rx["id"])["itens"] == []


def _gerador(c, monkeypatch, corpo):
    saida = [SAIDA]
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: json.dumps(saida[0]))

    def gera(nova=None):
        if nova is not None:
            saida[0] = nova
        return _lines(c.post("/prontuario/scribe", json=dict({"patient_id": 7, "rec_id": REC, "mode": "soap"}, **corpo)))[-1]
    return gera


def test_receita_que_falha_nao_fica_lembrada(fake, monkeypatch):
    """Erro do banco na receita: a evolução sai, e o remédio não conta como levado — gerar de novo o põe."""
    c = TestClient(server.app)
    _record(fake, c)
    gera = _gerador(c, monkeypatch, {"event_id": "ev9"})
    certo = db.list_receitas

    def boom(*a):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(db, "list_receitas", boom)
    out = gera()
    assert out["ok"] and out["receita"] == 0 and fake.recs[REC]["scribe"]["receita_meds"] == []
    monkeypatch.setattr(db, "list_receitas", certo)
    assert gera()["receita"] == 1 and [i["nome"] for i in db.list_receitas(UID, 7)[0]["itens"]] == ["Losartana"]


def test_memoria_na_duvida_nao_repoe_e_lembra_nome_curto(fake, monkeypatch):
    """O médico tirou a losartana e a D3: nenhuma volta, nem a associação com a losartana (na dúvida a gravação não
    sugere: o médico vê no SOAP). A D3 (nome curto: vale o texto) não volta nem se repete, e a lista não cresce."""
    c = TestClient(server.app)
    _record(fake, c)
    gera = _gerador(c, monkeypatch, {"event_id": "ev9"})
    d3 = {"nome": "D3", "dose": "7.000 UI", "posologia": "1x/semana", "acao": "iniciado", "src": [2]}
    assert gera(dict(SAIDA, meds=SAIDA["meds"] + [d3]))["receita"] == 2
    (rx,) = db.list_receitas(UID, 7)
    db.update_receita(UID, rx["id"], [])                            # tirou as duas
    assoc = {"nome": "losartana + hidroclorotiazida", "dose": "50/12,5 mg", "posologia": "1x/dia", "acao": "iniciado", "src": [2]}
    assert gera(dict(SAIDA, meds=SAIDA["meds"] + [d3, assoc]))["receita"] == 0
    assert db.get_receita(UID, rx["id"])["itens"] == []
    for _ in range(3):
        gera(dict(SAIDA, meds=SAIDA["meds"] + [d3, assoc]))
    assert db.get_receita(UID, rx["id"])["itens"] == [] and fake.recs[REC]["scribe"]["receita_meds"] == ["Losartana", "D3"]


def test_avulsa_com_receita_emitida_nao_ganha_rascunho_sozinho(fake, monkeypatch):
    """Consulta avulsa sem evolução salva: emitida a receita feita durante a gravação, gerar de novo não abre outra."""
    c = TestClient(server.app)
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(1, **{"X-Event-Id": None}))
    c.post("/prontuario/transcribe", content=wav(20), headers=hdr(2, **{"X-Event-Id": None}))
    gera = _gerador(c, monkeypatch, {})
    assert gera()["receita"] == 1
    (rx,) = db.list_receitas(UID, 7)
    assert rx["note_id"] is None and rx["event_id"] is None
    db.emit_receita(UID, rx["id"], [("simples", rx["itens"])])
    nova = {"nome": "atorvastatina", "dose": "20 mg", "posologia": "à noite", "acao": "iniciado", "src": [2]}
    assert gera(dict(SAIDA, meds=SAIDA["meds"] + [nova]))["receita"] == 0
    assert [r["status"] for r in db.list_receitas(UID, 7)] == ["emitida"]


def test_memoria_vale_com_o_sal_e_o_rascunho_nao_repete(fake, monkeypatch):
    """O modelo reescreve "metformina" como "cloridrato de metformina": a que o médico tirou não volta. Com a losartana
    no rascunho, a associação não entra repetida (na dúvida, não repete); um remédio novo de verdade entra."""
    c = TestClient(server.app)
    _record(fake, c)
    gera = _gerador(c, monkeypatch, {"event_id": "ev9"})
    met = {"nome": "metformina", "dose": "850 mg", "posologia": "2x/dia", "acao": "mantido", "src": [2]}
    assert gera(dict(SAIDA, meds=SAIDA["meds"] + [met]))["receita"] == 2
    (rx,) = db.list_receitas(UID, 7)
    db.update_receita(UID, rx["id"], [i for i in rx["itens"] if i["nome"] != "Metformina"])     # tirou a metformina
    sal = dict(met, nome="cloridrato de metformina")
    troca = [dict(SAIDA["meds"][0], acao="suspenso"),
             {"nome": "losartana + hidroclorotiazida", "dose": "50/12,5 mg", "posologia": "1x/dia", "acao": "iniciado", "src": [2]}]
    atorva = {"nome": "atorvastatina", "dose": "20 mg", "posologia": "à noite", "acao": "iniciado", "src": [2]}
    assert gera(dict(SAIDA, meds=troca + [sal, atorva]))["receita"] == 1
    assert [i["nome"] for i in db.get_receita(UID, rx["id"])["itens"]] == ["Losartana", "Atorvastatina"]


def test_geracao_que_nao_foi_guardada_nao_mexe_na_receita(fake, monkeypatch):
    """Falhou ao guardar a geração: a receita fica como estava (ela só muda depois)."""
    c = TestClient(server.app)
    _record(fake, c)
    gera = _gerador(c, monkeypatch, {"event_id": "ev9"})

    def boom(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(db, "rec_generated", boom)
    with pytest.raises(RuntimeError):
        gera()
    assert db.list_receitas(UID, 7) == []



def test_mesma_geracao_nao_repete_e_variantes_nao_voltam(fake, monkeypatch):
    """O mesmo remédio duas vezes na mesma geração entra uma vez; a D3 tirada não volta como "D3 7.000 UI" nem como
    "Vitamina D3"; e o sal na frente não esconde um remédio diferente (tirada a sertralina, a fluoxetina entra)."""
    c = TestClient(server.app)
    _record(fake, c)
    gera = _gerador(c, monkeypatch, {"event_id": "ev9"})
    m = lambda nome: {"nome": nome, "dose": "", "posologia": "", "acao": "iniciado", "src": [2]}  # noqa: E731
    out = gera(dict(SAIDA, meds=[m("D3"), m("D3"), m("Aradois H (losartana potássica + hidroclorotiazida)"),
                                 m("losartana + hidroclorotiazida"), m("cloridrato de sertralina")]))
    (rx,) = db.list_receitas(UID, 7)
    assert out["receita"] == 3 and [i["nome"] for i in rx["itens"]] == [
        "D3", "Aradois H (losartana potássica + hidroclorotiazida)", "Cloridrato de sertralina"]
    db.update_receita(UID, rx["id"], [])                            # tirou tudo
    assert gera(dict(SAIDA, meds=[m("D3 7.000 UI"), m("Vitamina D3"), m("cloridrato de fluoxetina")]))["receita"] == 1
    assert [i["nome"] for i in db.get_receita(UID, rx["id"])["itens"]] == ["Cloridrato de fluoxetina"]


def test_duas_geracoes_juntas_criam_um_rascunho_so(fake, monkeypatch):
    """Clique duplo ou duas abas: as duas gerações terminam juntas e a receita ganha um rascunho só, com a memória das
    duas."""
    import threading
    import time
    c = TestClient(server.app)
    _record(fake, c)
    juntas = threading.Barrier(2)

    def modelo(msgs, model=None):
        juntas.wait(5)                                              # as duas leem o mesmo estado antes de gravar
        return json.dumps(SAIDA_2)
    monkeypatch.setattr(scribe, "ask_model", modelo)
    criar = db.create_receita

    def criar_devagar(*a, **k):
        time.sleep(0.2)                                             # abre a janela da corrida
        return criar(*a, **k)
    monkeypatch.setattr(db, "create_receita", criar_devagar)
    server._RL.clear()
    outs = []

    def gera():
        outs.append(_lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"}))[-1])
    ts = [threading.Thread(target=gera) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert sorted(o["receita"] for o in outs) == [0, 2]
    (rx,) = db.list_receitas(UID, 7)
    assert [i["nome"] for i in rx["itens"]] == ["Losartana", "Metformina"]
    sc = fake.recs[REC]["scribe"]
    assert sc["receita_meds"] == ["Losartana", "Metformina"] and sc["receita_id"] == rx["id"]
