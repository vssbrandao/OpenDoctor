"""Áudio guardado da gravação (POST/GET /prontuario/recordings/audio, docs/audio-contrato.md) com o banco em memória
(tests/fake_gravacao.py) e o transcritor falso de tests/test_scribe_routes.py: nada sai para a OpenAI nem toca banco."""
import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, server
from tests.test_scribe_routes import REC, UID, fake, hdr, wav  # noqa: F401  (fake é a fixture)

URL = "/prontuario/recordings/audio"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x42\x86\x81\x01" + bytes(range(200))
OGG = b"OggS" + bytes(120)
MP4 = b"\x00\x00\x00\x1cftypisom" + bytes(80)
MEIO = bytes(range(256)) * 2                    # pedaço do meio: sem cabeçalho (o tipo vem do n = 0)
SESS, OUTRA = "sessao-aba-a-0001", "sessao-aba-b-0002"     # id da sessão do MediaRecorder (X-Sess), um por aba


def ah(part=0, n=0, at=0.0, upto=5.0, **kw):
    h = {"Content-Type": "application/octet-stream", "X-Patient-Id": "7", "X-Rec-Id": REC, "X-Part": str(part),
         "X-N": str(n), "X-At": str(at), "X-Upto": str(upto), "X-Event-Id": "ev9", "X-Sess": SESS}
    h.update(kw)
    return {k: v for k, v in h.items() if v is not None}


def _gravacao(c):
    """A gravação nasce no primeiro trecho transcrito (o áudio nunca a cria)."""
    assert c.post("/prontuario/transcribe", content=wav(1), headers=hdr(1)).status_code == 200


def test_sem_login_401(fake, monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    c = TestClient(server.app)
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 401
    assert c.get(URL, params={"rec_id": REC, "part": 0}).status_code == 401
    assert fake.audio == {}


def test_porteiro_da_gravacao_sem_exigir_a_chave(fake, monkeypatch):
    c = TestClient(server.app)
    _gravacao(c)
    monkeypatch.setattr(config, "SCRIBE_EMAILS", set())
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 403
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_OFF", True)
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 503
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    assert fake.audio == {}
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")              # guardar o áudio não vai à OpenAI
    assert c.post(URL, content=WEBM, headers=ah()).json() == {"ok": True}
    assert (REC, 0, 0) in fake.audio


@pytest.mark.parametrize("ruim", [
    {"X-Rec-Id": "abc"}, {"X-Rec-Id": REC + "x"}, {"X-Rec-Id": None}, {"X-Part": "1000"}, {"X-Part": "-1"},
    {"X-Part": "²".encode("latin-1")}, {"X-N": "10000"}, {"X-N": "1.5"}, {"X-N": None}, {"X-At": None}, {"X-Upto": "nan"},
    {"X-At": "10", "X-Upto": "5"}, {"X-Upto": "90000"}, {"X-Patient-Id": "abc"}, {"X-Patient-Id": "²".encode("latin-1")},
    {"X-Patient-Id": "8"},                                         # paciente de outro médico (ou que não existe)
    {"X-Sess": None}, {"X-Sess": ""}, {"X-Sess": "curto7x"}, {"X-Sess": "a" * 65}, {"X-Sess": "sessao com espaco"},
    {"X-Sess": "sessao_sublinhado"}, {"X-Sess": "sessão-acento-1".encode("latin-1")},  # X-Sess obrigatório: [A-Za-z0-9-]{8,64}
])
def test_ids_ruins_400(fake, ruim):
    c = TestClient(server.app)
    _gravacao(c)
    assert c.post(URL, content=WEBM, headers=ah(**ruim)).status_code == 400
    assert fake.audio == {}


def test_get_ids_ruins_400(fake):
    c = TestClient(server.app)
    for q in ({"rec_id": "abc", "part": 0}, {"rec_id": REC, "part": "x"}, {"rec_id": REC, "part": "²"},
              {"rec_id": REC, "part": "1000"}, {"rec_id": REC}, {"part": 0}):
        assert c.get(URL, params=q).status_code == 400, q


def test_nunca_cria_a_gravacao_409(fake):
    c = TestClient(server.app)
    r = c.post(URL, content=WEBM, headers=ah())
    assert r.status_code == 409 and r.json() == {"error": "gravação ainda não começou"}
    assert fake.recs == {} and fake.audio == {}
    fake.recs[REC] = {"uid": "outro-medico", "pid": 7, "event_id": None, "note_id": None, "consent_at": None,
                      "status": "gravando", "seconds": 0}
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 409     # gravação de outro médico: não grava
    assert fake.audio == {}


def test_pedaco_do_meio_sem_o_comeco_409_e_herda_o_tipo(fake):
    c = TestClient(server.app)
    _gravacao(c)
    assert c.post(URL, content=MEIO, headers=ah(n=1, upto=10)).status_code == 409
    assert fake.audio == {}
    assert c.post(URL, content=OGG, headers=ah(**{"Content-Type": "audio/webm"})).json() == {"ok": True}
    assert c.post(URL, content=MEIO, headers=ah(n=1, upto=10)).json() == {"ok": True}
    # o tipo é o dos bytes do n = 0 (nunca o Content-Type do navegador); o do meio herda
    assert fake.audio[(REC, 0, 0)]["mime"] == fake.audio[(REC, 0, 1)]["mime"] == "audio/ogg"


def test_tipo_so_pelos_bytes_415(fake):
    c = TestClient(server.app)
    _gravacao(c)
    for ruim in (b"%PDF-1.4 nada", wav(1), b"\x00" * 50):
        assert c.post(URL, content=ruim, headers=ah(**{"Content-Type": "audio/webm"})).status_code == 415
    assert c.post(URL, content=b"", headers=ah()).status_code == 400
    assert fake.audio == {}
    for part, b, mime in ((0, WEBM, "audio/webm"), (1, OGG, "audio/ogg"), (2, MP4, "audio/mp4")):
        assert c.post(URL, content=b, headers=ah(part=part)).status_code == 200
        assert fake.audio[(REC, part, 0)]["mime"] == mime


def test_grande_demais_413(fake, monkeypatch):
    c = TestClient(server.app)
    _gravacao(c)
    assert server.MAX_AUDIO_BYTES == 512 * 1024
    monkeypatch.setattr(server, "MAX_AUDIO_BYTES", 100)
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 413             # pelo content-length

    def aos_poucos():                                                             # sem content-length: pelo stream
        yield WEBM[:80]
        yield WEBM[80:]
    assert c.post(URL, content=aos_poucos(), headers=ah()).status_code == 413
    assert fake.audio == {}


def test_limite_por_conta_e_teto_do_dia_429(fake, monkeypatch):
    c = TestClient(server.app)
    _gravacao(c)
    assert server.RATE_LIMITS["audio"] == (480, 600) and server.AUDIO_DAY_BYTES == 300 * 1024 * 1024
    monkeypatch.setitem(server.RATE_LIMITS, "audio", (2, 600))
    assert c.post(URL, content=WEBM, headers=ah(**{"CF-Connecting-IP": "203.0.113.1"})).status_code == 200
    assert c.post(URL, content=MEIO, headers=ah(n=1, **{"CF-Connecting-IP": "203.0.113.2"})).status_code == 200
    # outro IP não zera o limite: conta pela conta (uma clínica com vários médicos sai pelo mesmo IP, e o contrário)
    r = c.post(URL, content=MEIO, headers=ah(n=2, **{"CF-Connecting-IP": "198.51.100.9"}))
    assert r.status_code == 429 and (REC, 0, 2) not in fake.audio
    assert ("audio", UID) in server._RL and not [k for k in server._RL if k[0] == "audio" and k != ("audio", UID)]
    assert not server._rate_limited(None, "audio", key="outro-medico")       # outra conta tem o seu próprio balde
    server._RL.clear()
    monkeypatch.setattr(server, "AUDIO_DAY_BYTES", len(WEBM) + len(MEIO) + 10)   # já usou quase tudo nas 24 h
    r = c.post(URL, content=MEIO, headers=ah(n=2))
    assert r.status_code == 429 and (REC, 0, 2) not in fake.audio and "teto_parte" not in r.json()


def test_teto_da_parte_429(fake, monkeypatch):
    c = TestClient(server.app)
    _gravacao(c)
    assert server.MAX_PART_BYTES == 32 * 1024 * 1024
    monkeypatch.setattr(server, "MAX_PART_BYTES", len(WEBM) + len(MEIO) + 10)
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 200
    assert c.post(URL, content=MEIO, headers=ah(n=1)).status_code == 200
    r = c.post(URL, content=MEIO, headers=ah(n=2))
    assert r.status_code == 429 and r.json()["teto_parte"] is True and (REC, 0, 2) not in fake.audio
    assert c.post(URL, content=OGG, headers=ah(part=1)).json() == {"ok": True}     # a página troca de parte e segue
    monkeypatch.setattr(server, "MAX_PART_BYTES", 10)                              # nem o n = 0 cabe
    r = c.post(URL, content=WEBM, headers=ah(part=2))
    assert r.status_code == 429 and r.json()["teto_parte"] is True and (REC, 2, 0) not in fake.audio


def test_reenvio_do_mesmo_pedaco(fake):
    c = TestClient(server.app)
    _gravacao(c)
    assert c.post(URL, content=WEBM, headers=ah()).json() == {"ok": True}
    assert c.post(URL, content=OGG, headers=ah()).json() == {"ok": True, "repetido": True}
    assert c.post(URL, content=MEIO, headers=ah(n=1)).json() == {"ok": True}
    assert c.post(URL, content=MEIO, headers=ah(n=1)).json() == {"ok": True, "repetido": True}
    assert fake.audio[(REC, 0, 0)]["data"] == WEBM and len(fake.audio) == 2      # fica o primeiro
    assert fake.audio[(REC, 0, 0)]["sess"] == fake.audio[(REC, 0, 1)]["sess"] == SESS


def test_parte_de_outra_sessao_409_parte_ocupada(fake):
    """Duas abas que escolheram o mesmo número de parte: a segunda recebe parte_ocupada (e renumera); nada se mistura e
    nada é dado como enviado ("repetido") sem ser da mesma sessão."""
    c = TestClient(server.app)
    _gravacao(c)
    assert c.post(URL, content=WEBM, headers=ah()).json() == {"ok": True}
    ocupada = {"error": "parte ocupada", "parte_ocupada": True}
    r = c.post(URL, content=OGG, headers=ah(**{"X-Sess": OUTRA}))                # n = 0 de outra sessão
    assert r.status_code == 409 and r.json() == ocupada
    r = c.post(URL, content=MEIO, headers=ah(n=1, **{"X-Sess": OUTRA}))          # n > 0 com sess diferente do n = 0
    assert r.status_code == 409 and r.json() == ocupada
    assert c.post(URL, content=MEIO, headers=ah(n=1)).json() == {"ok": True}
    r = c.post(URL, content=b"outro", headers=ah(n=1, **{"X-Sess": OUTRA}))      # pedaço que já existe, de outra sessão
    assert r.status_code == 409 and r.json() == ocupada
    assert fake.audio[(REC, 0, 0)]["data"] == WEBM and fake.audio[(REC, 0, 1)]["data"] == MEIO and len(fake.audio) == 2
    assert c.post(URL, content=OGG, headers=ah(part=1, **{"X-Sess": OUTRA})).json() == {"ok": True}   # renumerou
    assert c.post(URL, content=MEIO, headers=ah(part=1, n=1, **{"X-Sess": OUTRA})).json() == {"ok": True}
    assert fake.audio[(REC, 1, 0)]["sess"] == OUTRA and fake.audio[(REC, 1, 1)]["mime"] == "audio/ogg"
    assert c.get(URL, params={"rec_id": REC, "part": 0}).content == WEBM + MEIO


def test_ouvir_junta_os_pedacos_e_so_o_dono_ouve(fake, monkeypatch):
    c = TestClient(server.app)
    _gravacao(c)
    c.post(URL, content=WEBM, headers=ah(n=0, upto=5))
    c.post(URL, content=MEIO, headers=ah(n=1, upto=10))
    c.post(URL, content=b"fim", headers=ah(n=3, upto=20))                        # buraco no 2: o 3 não toca ainda
    r = c.get(URL, params={"rec_id": REC, "part": 0})
    assert r.status_code == 200 and r.content == WEBM + MEIO
    assert r.headers["content-type"] == "audio/webm"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert "media-src 'self' blob:" in r.headers["content-security-policy"]
    assert ("recording_listen", 7, None) in fake.log
    assert c.get(URL, params={"rec_id": REC, "part": 1}).status_code == 404      # parte sem áudio
    assert c.get(URL, params={"rec_id": REC.upper(), "part": 0}).status_code == 200
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": "outro-medico", "email": "medica@exemplo.com", "sv": 0})
    assert c.get(URL, params={"rec_id": REC, "part": 0}).status_code == 404
    assert c.post(URL, content=MEIO, headers=ah(n=2, upto=15)).status_code == 400   # paciente não é dele


def test_estado_traz_as_partes_do_audio(fake):
    c = TestClient(server.app)
    _gravacao(c)
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"]
    assert st[0]["audio"] == []                                                     # gravação de antes: sem áudio
    c.post(URL, content=WEBM, headers=ah(part=0, n=0, at=0, upto=5))
    c.post(URL, content=MEIO, headers=ah(part=0, n=1, at=0, upto=10))
    c.post(URL, content=MEIO, headers=ah(part=0, n=3, at=0, upto=20))              # depois de um buraco: não conta
    c.post(URL, content=OGG, headers=ah(part=1, n=0, at=40, upto=45))
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"]
    assert st[0]["audio"] == [{"part": 0, "at": 0.0, "upto": 10.0}, {"part": 1, "at": 40.0, "upto": 45.0}]
    assert "data" not in str(st[0]["audio"])


def test_apagar_transcricao_leva_o_audio(fake):
    c = TestClient(server.app)
    _gravacao(c)
    c.post(URL, content=WEBM, headers=ah())
    assert c.delete("/prontuario/recordings/" + REC).json() == {"ok": True}
    assert fake.audio == {} and c.get(URL, params={"rec_id": REC, "part": 0}).status_code == 404


def test_consulta_com_evolucao_de_outro_paciente_409(fake):
    c = TestClient(server.app)
    _gravacao(c)
    fake.outro = {"ev9": 99}
    r = c.post(URL, content=WEBM, headers=ah())
    assert r.status_code == 409 and r.json()["other_patient"] is True and fake.audio == {}


def test_sem_a_migracao_0022_responde_503_e_a_gravacao_segue(fake):
    c = TestClient(server.app)
    fake.sem_migracao = True
    _gravacao(c)                                                                    # o texto continua
    assert c.post(URL, content=WEBM, headers=ah()).status_code == 503              # a página tenta de novo
    assert c.get(URL, params={"rec_id": REC, "part": 0}).status_code == 404
    st = c.post("/prontuario/recordings/state", json={"patient_id": 7, "event_id": "ev9"}).json()["recordings"]
    assert st[0]["audio"] == [] and [s["seq"] for s in st[0]["segments"]] == [1]


def test_log_so_com_numeros(fake, capsys):
    c = TestClient(server.app)
    _gravacao(c)
    capsys.readouterr()
    c.post(URL, content=WEBM, headers=ah())
    c.post(URL, content=MEIO, headers=ah(n=1))
    c.get(URL, params={"rec_id": REC, "part": 0})
    out = capsys.readouterr()
    log = out.out + out.err
    assert f"[audio] pedaço 0/0: {len(WEBM)} bytes" in log and f"[audio] pedaço 0/1: {len(MEIO)} bytes" in log
    assert "Maria" not in log and REC not in log and "\\x" not in log and "OggS" not in log


def test_tipo_pelos_bytes_e_partes():
    assert server._audio_mime(WEBM) == "audio/webm" and server._audio_mime(OGG) == "audio/ogg"
    assert server._audio_mime(MP4) == "audio/mp4" and server._audio_mime(b"RIFF....WAVE") is None
    assert server._audio_mime(b"") is None
    assert db._audio_partes([(0, 0, 0, 5), (0, 1, 0, 10), (0, 3, 0, 20), (1, 1, 30, 35), (2, 0, 40, 45)]) == [
        {"part": 0, "at": 0.0, "upto": 10.0}, {"part": 2, "at": 40.0, "upto": 45.0}]
    assert db._audio_partes([]) == []
    assert UID
