"""Rotas da gravação da consulta (transcrever, estado, gerar, apagar) com banco em memória e transcritor/modelo
falsos: nada sai para a OpenAI nem toca banco."""
import json
import struct

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, scribe, server, stt

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


class FakeDB:
    def __init__(self):
        self.recs, self.segs, self.log, self.today, self.linked = {}, {}, [], 0.0, []

    def install(self, mp):
        for name in ("get_patient", "rec_open", "rec_segment", "rec_prev_text", "rec_add_segment", "rec_seconds_today",
                     "rec_list", "rec_generated", "rec_link_note", "rec_delete", "recent_notes", "list_notes", "log_access"):
            mp.setattr(db, name, getattr(self, name))

    def get_patient(self, uid, pid):
        return dict(PAC) if uid == UID and pid == PAC["id"] else None

    def rec_open(self, uid, pid, rid, eid=None, nid=None, consent=None):
        r = self.recs.setdefault(rid, {"uid": uid, "pid": pid, "event_id": eid, "note_id": nid, "consent_at": consent,
                                       "status": "gravando", "seconds": 0, "scribe": None})
        return r["uid"] == uid and r["pid"] == pid

    def rec_segment(self, uid, rid, seq):
        s = self.segs.get((rid, seq))
        return {"text": s["text"], "duvidas": s["duvidas"]} if s and self.recs[rid]["uid"] == uid else None

    def rec_prev_text(self, uid, rid, seq):
        prev = [s for (r, q), s in sorted(self.segs.items()) if r == rid and q < seq]
        return prev[-1]["text"] if prev else ""

    def rec_add_segment(self, uid, rid, seq, at, dur, text, duvidas):
        self.segs.setdefault((rid, seq), {"seq": seq, "at": at, "dur": dur, "text": text, "duvidas": list(duvidas)})
        self.recs[rid]["seconds"] = max(self.recs[rid]["seconds"], at + dur)

    def rec_seconds_today(self, uid):
        return self.today

    def rec_list(self, uid, pid, eid=None, nid=None, ids=(), orphans=False):
        out = []
        for rid, r in self.recs.items():
            if r["uid"] == uid and r["pid"] == pid and ((eid and r["event_id"] == eid) or (nid and r["note_id"] == nid) or rid in ids
                                                       or (orphans and not r["event_id"] and not r["note_id"])):
                segs = [s for (q, _), s in sorted(self.segs.items()) if q == rid]
                out.append({"rec_id": rid, "status": r["status"], "consent_at": r["consent_at"], "seconds": r["seconds"],
                            "updated_at": "2026-10-15T10:00:00+00:00", "event_id": r["event_id"], "note_id": r["note_id"],
                            "scribe": r.get("scribe"), "segments": segs})
        return out

    def rec_generated(self, uid, rids, meta, nid=None):
        for rid in rids:
            self.recs[rid].update(status="gerada", scribe=meta)

    def rec_link_note(self, uid, pid, rids, nid):
        self.linked.append((tuple(rids), nid))

    def rec_delete(self, uid, rid):
        r = self.recs.get(rid)
        if not r or r["uid"] != uid:
            return None
        self.recs.pop(rid)
        return r["pid"]

    def recent_notes(self, uid, limit=30):
        return [{"content": "S: HAS controlada. PA 130x80. Mantido.", "data": {"mode": "soap"}}]

    def list_notes(self, uid, pid, key):
        return [{"id": 1, "event_id": "ev0", "content": "Maria Silva refere boa adesão. Losartana 50 mg.", "data": {"mode": "free"}}]

    def log_access(self, uid, action, pid=None, nid=None, dedupe_minutes=0):
        self.log.append((action, pid, nid))


@pytest.fixture
def fake(monkeypatch):
    f = FakeDB(); f.install(monkeypatch)
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
    assert out["result"]["vitals"] == {"pa_s": "128", "pa_d": "82", "fc": "74"} and out["result"]["cid"][0]["code"] == "I10"
    assert [t["seq"] for t in out["segs"]] == [1, 2] and out["segs"][0]["rec_id"] == REC
    assert any(f["tipo"] == "duvida_grave" for f in out["flags"])          # o 74 foi ouvido com dúvida
    assert out["meta"]["prompt"] == scribe.PROMPT_VERSION and out["meta"]["rec_ids"] == [REC] and out["meta"]["segundos"] == 40
    texto = json.dumps(sent[0], ensure_ascii=False)
    assert "Maria" not in texto and "[PACIENTE]" in texto                   # nem a última evolução leva o nome
    assert fake.recs[REC]["status"] == "gerada" and ("scribe", 7, None) in fake.log


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
        "conf_idx": [3, 0, 3, -1, True, "2"],
        "texto": "transcrição inteira não pode entrar aqui"}})
    assert d["scribe"] == {"rec_ids": [REC], "prompt": "2026-10-15.5", "model": "gpt-5.4", "consent_at": "2026-10-15T10:00:00Z",
                           "generated_at": "2026-10-15T10:20:00Z", "pontos": {"alto": 1, "medio": 3}, "segundos": 912, "conferidos": 2,
                           "conf_idx": [0, 3]}
    assert "scribe" not in server._note_data({"mode": "free"})


def test_duracao_do_wav():
    assert server._wav_seconds(wav(2)) == 2 and server._wav_seconds(wav(1, rate=8000)) is None
    assert server._wav_seconds(b"RIFF") is None and server._wav_seconds(wav(1)[:44]) is None


def test_geracao_fica_guardada_para_revisar_depois(fake, monkeypatch):
    """Recarregou a página ou voltou noutro dia: a evolução gerada e os pontos para conferir voltam."""
    c = TestClient(server.app)
    _record(fake, c)
    monkeypatch.setattr(scribe, "ask_model", lambda msgs, model=None: json.dumps(SAIDA))
    out = _lines(c.post("/prontuario/scribe", json={"patient_id": 7, "event_id": "ev9", "rec_id": REC, "mode": "soap"}))[-1]
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"][0]
    assert st["status"] == "gerada" and st["scribe"]["generated_at"] == out["meta"]["generated_at"]
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
