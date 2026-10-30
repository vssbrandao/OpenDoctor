"""Testes contra um banco de verdade — o de TESTES (fixture test_db, ver conftest.py). Sem
TEST_DATABASE_URL eles são pulados; nunca tocam produção. Cada teste cria os próprios usuários e
apaga tudo no fim."""
import datetime
import uuid

import pytest

from app import db


@pytest.fixture
def novo_usuario(test_db):
    criados = []

    def criar(nome="Teste"):
        u = db.create_email_user(f"teste-{uuid.uuid4().hex[:12]}@example.invalid", nome, "x")
        criados.append(u["id"])
        return u
    yield criar
    with db.connection() as c:
        for uid in criados:
            c.execute("delete from patient_files where user_id = %s", (uid,))
            c.execute("delete from clinical_notes where user_id = %s", (uid,))
            c.execute("delete from patients where user_id = %s", (uid,))
            c.execute("delete from users where id = %s", (uid,))
        c.commit()


def test_aviso_so_para_aparelho_novo(novo_usuario):
    uid = novo_usuario()["id"]
    assert db.record_login(uid, "entrou", "senha", "1.2.3.4", "UA", "devA") is False   # primeira: sem aviso
    assert db.record_login(uid, "entrou", "senha", "1.2.3.4", "UA", "devA") is False   # mesmo aparelho
    assert db.record_login(uid, "senha_incorreta", "senha", "5.6.7.8", "UA", "devB") is False
    assert db.record_login(uid, "entrou", "senha", "5.6.7.8", "UA", "devB") is True     # aparelho novo
    assert db.record_login(uid, "entrou", "google", "5.6.7.8", "UA", "devB") is False


def test_medico_nao_ve_paciente_de_outro(novo_usuario):
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p = db.create_patient(ana, "Paciente da Ana")
    assert [x["id"] for x in db.list_patients(ana)] == [p["id"]]
    assert db.list_patients(beto) == []
    assert db.get_patient(beto, p["id"]) is None
    assert db.update_patient(beto, p["id"], {"name": "invadido"}) is None
    assert db.delete_patient(beto, p["id"]) == "not_found"
    assert db.get_patient(ana, p["id"])["name"] == "Paciente da Ana"


def test_trocar_senha_derruba_sessoes(novo_usuario):
    u = novo_usuario()
    assert db.set_password(u["id"], "novo-hash")["sv"] == (u.get("sv") or 0) + 1


def test_codigo_de_email(novo_usuario):
    email = f"teste-{uuid.uuid4().hex[:12]}@example.invalid"
    try:
        assert db.new_login_code(email, "hash-certo")[0] == "ok"
        assert db.check_login_code(email, "hash-errado")[0] == "errado"
        assert db.check_login_code(email, "hash-certo")[0] == "ok"
        assert db.check_login_code(email, "hash-certo")[0] != "ok"                      # uso único
    finally:
        with db.connection() as c:
            c.execute("delete from login_codes where email = %s", (email,))
            c.commit()


def test_limpeza_apaga_so_o_vencido(novo_usuario):
    uid = novo_usuario()["id"]
    with db.connection() as c:
        c.execute("""insert into login_events (user_id, event, method, created_at) values
                     (%s, 'entrou', 'senha', now() - interval '13 months'),
                     (%s, 'entrou', 'senha', now() - interval '11 months')""", (uid, uid))
        c.commit()
    db.cleanup_old_records()
    with db.connection() as c:
        n = c.execute("select count(*) from login_events where user_id = %s", (uid,)).fetchone()[0]
    assert n == 1                                       # ficou só o de 11 meses


def test_anexo_so_do_proprio_medico(novo_usuario):
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p = db.create_patient(ana, "Paciente da Ana")
    f = db.add_file(ana, p["id"], "laudo.pdf", "application/pdf", b"%PDF-1.7 teste")
    assert [x["id"] for x in db.list_files(ana, p["id"])] == [f["id"]]
    assert db.get_file(ana, f["id"])["data"] == b"%PDF-1.7 teste"
    assert db.get_file(beto, f["id"]) is None and db.delete_file(beto, f["id"]) is None
    assert db.delete_patient(ana, p["id"]) == "has_notes"     # exame anexado também é prontuário
    assert db.delete_file(ana, f["id"]) == p["id"] and db.list_files(ana, p["id"]) == []


def test_conta_nova_ganha_paciente_de_exemplo_que_pode_ser_excluida(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    assert pid and exemplo.seed(uid) is None                              # só uma vez
    p = db.get_patient(uid, pid)
    assert p["name"] == db.EXAMPLE_NAME and p["example"] and not p.get("cpf") and not p.get("phone")
    real = db.create_patient(uid, "Maria Silva")                         # homônima real: não é exemplo
    assert not db.get_patient(uid, real["id"])["example"]
    db.add_example_notes(uid, real["id"], real["key"], real["name"], [("Retorno", None, "texto real", {"mode": "free"}, None, datetime.datetime.now(datetime.timezone.utc))])
    assert db.delete_patient(uid, real["id"]) == "has_notes"             # prontuário real continua protegido
    assert db.update_patient(uid, pid, {"name": db.EXAMPLE_NAME})["example"]   # salvar o cadastro não tira a marca
    notas = db.list_notes(uid, pid, p["key"])
    assert len(notas) == 17 and sum(1 for n in notas if n["signed_at"]) == 11
    assert len(db.list_files(uid, pid)) == 1
    assert db.delete_patient(uid, pid) == "ok"                            # fictícia: sai com tudo
    assert db.list_notes(uid, pid, p["key"]) == [] and db.list_files(uid, pid) == []


def test_finalizar_guarda_o_tempo_de_documentacao_uma_vez(novo_usuario):
    uid = novo_usuario()["id"]
    p = db.create_patient(uid, "Paciente do Tempo")
    nid = db.upsert_note(uid, p["id"], p["key"], p["name"], None, None, None, "Evolução de teste.",
                         data={"mode": "free", "vitals": {}, "cid": []})
    nid = nid["id"] if isinstance(nid, dict) else nid
    assert db.finalize_note(uid, nid, {"active_s": 300, "wall_s": 420, "edits": 12})
    assert db.get_note(uid, nid)["data"]["timing"] == {"active_s": 300, "wall_s": 420, "edits": 12}
    db.finalize_note(uid, nid, {"active_s": 1, "wall_s": 1, "edits": 1})          # já finalizada: não muda
    assert db.get_note(uid, nid)["data"]["timing"]["active_s"] == 300


def test_gravacao_da_consulta(novo_usuario):
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p = db.create_patient(ana, "Paciente da Ana")
    rid = str(uuid.uuid4())
    assert db.rec_open(ana, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    assert db.rec_open(ana, p["id"], rid, "ev1")                      # reabrir a mesma gravação vale
    assert not db.rec_open(beto, p["id"], rid)                       # id de outro médico: não mistura
    db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "Pressão 128 por 82.", ["82"])
    db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "outro texto", [])     # reenvio: fica o primeiro
    db.rec_add_segment(beto, rid, 2, 20.0, 20.0, "invasão", [])       # gravação de outro médico: ignorado
    db.rec_add_segment(ana, rid, 2, 20.0, 18.5, "Manter losartana.", [])
    assert db.rec_segment(ana, rid, 1) == {"text": "Pressão 128 por 82.", "duvidas": ["82"]}
    assert db.rec_segment(beto, rid, 1) is None
    assert db.rec_prev_text(ana, rid, 2) == "Pressão 128 por 82."
    assert 38 <= db.rec_seconds_today(ana) <= 39 and db.rec_seconds_today(beto) == 0
    for where in ({"event_id": "ev1"}, {"rec_ids": [rid]}):
        recs = db.rec_list(ana, p["id"], **where)
        assert [r["rec_id"] for r in recs] == [rid] and [s["seq"] for s in recs[0]["segments"]] == [1, 2]
        assert recs[0]["seconds"] == 38.5 and recs[0]["status"] == "gravando"
    assert db.rec_list(beto, p["id"], event_id="ev1") == [] and db.rec_list(ana, p["id"]) == []
    assert db.delete_patient(ana, p["id"]) == "has_notes"            # só a transcrição já é prontuário
    nid = db.upsert_note(ana, p["id"], p["key"], p["name"], "ev1", "Consulta", None, "S: teste")
    db.rec_generated(ana, p["id"], [rid], {"prompt": "x"}, None)
    db.rec_link_note(ana, p["id"], [rid], nid)
    r = db.rec_list(ana, p["id"], note_id=nid)[0]
    assert r["status"] == "gerada" and r["note_id"] == nid
    assert db.rec_delete(beto, rid) is None and db.rec_delete(ana, rid) == p["id"]
    assert db.rec_segment(ana, rid, 1) is None


def test_gravacao_liga_a_evolucao_certa_e_acha_a_avulsa(novo_usuario):
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p, outro = db.create_patient(ana, "Paciente A"), db.create_patient(ana, "Paciente B")
    nota_beto = db.upsert_note(beto, db.create_patient(beto, "Paciente do Beto")["id"], "x", "x", "evx", "Consulta", None, "S: x")
    rid = str(uuid.uuid4())
    assert db.rec_open(ana, p["id"], rid, None, 999999999, "2026-10-15T10:00:00Z")      # evolução que não existe: não derruba
    assert db.rec_open(ana, p["id"], rid, None, nota_beto)                              # evolução de outro médico: ignorada
    db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "Dor lombar há 3 dias.", [])
    assert db.rec_list(ana, p["id"])[0:1] == [] and [r["rec_id"] for r in db.rec_list(ana, p["id"], orphans=True)] == [rid]
    assert db.rec_list(ana, outro["id"], orphans=True) == []                            # só do mesmo paciente
    nota = db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "S: lombalgia")
    assert db.rec_open(ana, p["id"], rid, None, nota)                                   # a evolução salva entra na gravação
    r = db.rec_list(ana, p["id"], note_id=nota)[0]
    assert r["rec_id"] == rid and r["note_id"] == nota and db.rec_list(ana, p["id"], orphans=True) == []
    db.rec_generated(ana, p["id"], [rid], {"prompt": "x", "saida": {"flags": [{"tipo": "alergia"}]}}, nota_beto)   # nota de outro: não liga
    r = db.rec_list(ana, p["id"], note_id=nota)[0]
    assert r["status"] == "gerada" and r["note_id"] == nota and r["scribe"]["saida"]["flags"] == [{"tipo": "alergia"}]
    with db.connection() as c:
        c.execute("delete from clinical_notes where user_id = %s", (beto,)); c.commit()


def test_salvar_a_evolucao_avulsa_liga_a_gravacao_sem_tirar_de_outra(novo_usuario):
    ana = novo_usuario("Ana")["id"]
    p, outro = db.create_patient(ana, "Paciente A"), db.create_patient(ana, "Paciente B")
    solta, ligada = str(uuid.uuid4()), str(uuid.uuid4())
    n1 = db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "S: manhã")
    for rid, nid in ((solta, None), (ligada, n1)):
        assert db.rec_open(ana, p["id"], rid, None, nid, "2026-10-15T10:00:00Z")
        db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "Dor lombar.", [])
    n2 = db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "S: tarde")
    db.rec_link_orphans(ana, outro["id"], [solta], n2)                                  # paciente errado: nada
    assert [r["rec_id"] for r in db.rec_list(ana, p["id"], orphans=True)] == [solta]
    db.rec_link_orphans(ana, p["id"], [solta, ligada], n2)
    assert [r["rec_id"] for r in db.rec_list(ana, p["id"], note_id=n2)] == [solta]      # a solta ganhou a evolução
    assert [r["rec_id"] for r in db.rec_list(ana, p["id"], note_id=n1)] == [ligada]     # a ligada não mudou de evolução
    assert db.rec_list(ana, p["id"], orphans=True) == []


def test_evolucao_anterior_para_a_gravacao(novo_usuario):
    ana = novo_usuario("Ana")["id"]
    p = db.create_patient(ana, "Paciente C")
    velha = db.upsert_note(ana, p["id"], p["key"], p["name"], "ev1", "Consulta", "2026-09-01T10:00:00+00:00", "S: consulta antiga")
    db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "Resultado de exames", data={"mode": "free", "kind": "labs"})
    atual = db.upsert_note(ana, p["id"], p["key"], p["name"], "ev2", "Consulta", "2026-10-15T10:00:00+00:00", "S: consulta de hoje")
    assert db.last_note_content(ana, p["id"], atual, "ev2") == "S: consulta antiga"      # nem a de hoje, nem a de exames
    assert db.last_note_content(ana, p["id"], velha, "ev1") == "S: consulta de hoje"
    assert db.last_note_content(novo_usuario("Beto")["id"], p["id"]) == ""               # de outro médico: nada


def test_evolucao_anterior_ignora_a_atual_e_os_exames(novo_usuario):
    ana = novo_usuario("Ana")["id"]
    p = db.create_patient(ana, "Paciente A")
    antiga = db.upsert_note(ana, p["id"], p["key"], p["name"], "ev1", "Consulta", "2026-09-01T10:00:00Z", "S: consulta de setembro")
    db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "Exames", data={"mode": "soap", "kind": "labs"})
    atual = db.upsert_note(ana, p["id"], p["key"], p["name"], "ev2", "Consulta", "2026-10-15T10:00:00Z", "S: consulta de hoje")
    assert db.last_note_content(ana, p["id"], atual, "ev2") == "S: consulta de setembro"
    assert db.last_note_content(ana, p["id"], antiga, "ev1") == "S: consulta de hoje"
    assert db.last_note_content(novo_usuario("Beto")["id"], p["id"]) == ""        # de outro médico: nada


def test_receitas_rascunho_emitida_cancelada(novo_usuario):
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p = db.create_patient(ana, "Paciente da Receita")
    r = db.create_receita(ana, p["id"], [{"nome": "Losartana"}])
    assert r["status"] == "rascunho" and r["note_id"] is None
    assert db.get_receita(beto, r["id"]) is None and db.update_receita(beto, r["id"], []) is None
    assert r["orientacoes"] == ""
    u = db.update_receita(ana, r["id"], [{"nome": "Losartana", "dose": "50 mg"}], "Beber água")
    assert u["itens"][0]["dose"] == "50 mg" and u["orientacoes"] == "Beber água"
    assert db.update_receita(ana, r["id"], [{"nome": "Losartana", "dose": "50 mg"}])["orientacoes"] == "Beber água"   # None: fica
    out = db.emit_receita(ana, r["id"], [("simples", [{"nome": "Losartana"}]), ("especial", [{"nome": "Sertralina"}])])
    assert [(x["tipo"], x["status"]) for x in out] == [("simples", "emitida"), ("especial", "emitida")] and out[0]["id"] == r["id"]
    assert [x["orientacoes"] for x in out] == ["Beber água", "Beber água"]              # vai em cada receita emitida
    assert db.emit_receita(ana, r["id"], [("simples", [])]) is None                     # emitida não emite de novo
    assert db.update_receita(ana, r["id"], []) is None and db.delete_receita(ana, r["id"]) is None
    assert db.cancel_receita(beto, out[1]["id"], "x") is None
    c = db.cancel_receita(ana, out[1]["id"], "Dose errada")
    assert c["status"] == "cancelada" and c["motivo_cancelamento"] == "Dose errada" and c["cancelada_em"]
    assert len(db.list_receitas(ana, p["id"])) == 2 and db.list_receitas(beto, p["id"]) == []
    assert db.delete_patient(ana, p["id"]) == "has_notes"                               # receita emitida é prontuário
    p2 = db.create_patient(ana, "Só rascunho")
    db.create_receita(ana, p2["id"], [])
    assert db.delete_patient(ana, p2["id"]) == "ok"                                      # o rascunho sai junto


def test_dados_do_medico(novo_usuario):
    uid = novo_usuario("Dra. Ana")["id"]
    assert db.get_medico(uid)["crm"] is None
    m = db.update_medico(uid, {"crm": "123456", "crm_uf": "SP", "consultorio_endereco": "Rua A, 1", "invadir": "x"})
    assert (m["name"], m["crm"], m["crm_uf"], m["consultorio_endereco"]) == ("Dra. Ana", "123456", "SP", "Rua A, 1")
    assert db.update_medico(uid, {"receita_papel": "A5"})["receita_papel"] == "A5"


def test_exemplo_vem_com_as_receitas(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    rs = db.list_receitas(uid, pid)
    assert len(rs) == len(exemplo.CONSULTAS) and all(r["status"] == "emitida" and r["note_id"] for r in rs)
    assert [i["nome"] for i in rs[0]["itens"]] == ["Losartana", "Metformina", "Atorvastatina"]   # a mais nova


def test_conexao_morta_e_reconexao(novo_usuario):
    """O Google recusou a renovação: a linha perde o refresh_token e aparece em dead_providers; conectar de novo
    (set_token com token novo) a tira de lá. users on delete cascade apaga a linha no fim."""
    uid = novo_usuario()["id"]
    agora = datetime.datetime.now(datetime.timezone.utc)
    db.set_token(uid, "google", access_token="a", refresh_token="r", expires_at=agora - datetime.timedelta(hours=1),
                 scope="calendar.events", account_email="ana@gmail.com")
    assert db.dead_providers(uid) == set()                      # vencido, mas ainda renova
    db.mark_token_dead(uid, "google", "outro")                  # o que falhou já foi trocado por uma reconexão
    assert db.dead_providers(uid) == set() and db.get_token(uid, "google")["refresh_token"] == "r"
    db.mark_token_dead(uid, "google", "r")
    assert db.dead_providers(uid) == {"google"} and db.connected_providers(uid) == {"google": "ana@gmail.com"}
    assert db.get_token(uid, "google")["refresh_token"] is None and db.get_token(uid, "google")["access_token"] == ""
    db.set_token(uid, "google", access_token="b", refresh_token="r2", expires_at=agora + datetime.timedelta(hours=1),
                 scope="calendar.events", account_email=None)
    assert db.dead_providers(uid) == set() and db.connected_providers(uid) == {"google": "ana@gmail.com"}
