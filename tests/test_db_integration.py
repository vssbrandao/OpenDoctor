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
            c.execute("delete from note_addenda where user_id = %s", (uid,))     # o adendo segura a evolução
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


def test_tiquete_da_nova_senha_vale_uma_vez_no_banco(novo_usuario):
    """O banco confere a versão do tíquete: o segundo uso (outro processo no ar) não troca a senha."""
    u = novo_usuario()
    sv = db.get_user(u["id"])["sv"]
    assert db.set_password(u["id"], "hash-1", sv)["sv"] == sv + 1
    assert db.set_password(u["id"], "hash-2", sv) is None
    assert db.get_user(u["id"])["sv"] == sv + 1


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


def test_receita_avulsa_vai_para_a_evolucao_escrita_depois(novo_usuario):
    """Prontuário avulso: a receita feita antes de a evolução existir (rascunho ou já emitida) passa a ser dela, e aparece
    no card e no PDF. A que já tem consulta fica; só evolução deste médico e deste paciente."""
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p, q = db.create_patient(ana, "Paciente Avulso"), db.create_patient(ana, "Outro Paciente")
    rasc = db.create_receita(ana, p["id"], [{"nome": "Losartana"}])
    emit = db.create_receita(ana, p["id"], [{"nome": "Metformina"}])
    db.emit_receita(ana, emit["id"], [("simples", [{"nome": "Metformina"}])])
    ev = db.create_receita(ana, p["id"], [{"nome": "Dipirona"}], event_id="ev1")
    nid = db.upsert_note(ana, p["id"], p["key"], p["name"], None, None, None, "S: renovação")
    outra = db.upsert_note(ana, q["id"], q["key"], q["name"], None, None, None, "S: outro paciente")
    ids = [rasc["id"], emit["id"], ev["id"], str(uuid.uuid4())]
    assert db.rx_link_orphans(beto, p["id"], ids, nid) == [] and db.rx_link_orphans(ana, p["id"], ids, outra) == []
    assert sorted(db.rx_link_orphans(ana, p["id"], ids, nid)) == sorted([rasc["id"], emit["id"]])
    assert {r["id"]: r["note_id"] for r in db.list_receitas(ana, p["id"])} == {rasc["id"]: nid, emit["id"]: nid, ev["id"]: None}
    assert db.rx_link_orphans(ana, p["id"], ids, nid) == []                             # já ligadas: nada muda
    # emitir com a evolução já escrita: o rascunho sem consulta sai dela, com as receitas separadas
    r = db.create_receita(ana, p["id"], [{"nome": "Losartana"}])
    assert db.emit_receita(ana, r["id"], [("simples", [{"nome": "Losartana"}])], note_id=outra)[0]["note_id"] is None
    r = db.create_receita(ana, p["id"], [{"nome": "Losartana"}])
    out = db.emit_receita(ana, r["id"], [("simples", [{"nome": "Losartana"}]), ("especial", [{"nome": "Sertralina"}])], note_id=nid)
    assert [x["note_id"] for x in out] == [nid, nid]
    r = db.create_receita(ana, p["id"], [{"nome": "Losartana"}], event_id="ev2")       # da agenda: fica com a consulta dela
    assert db.emit_receita(ana, r["id"], [("simples", [{"nome": "Losartana"}])], note_id=nid)[0]["note_id"] is None


def test_dados_do_medico(novo_usuario):
    uid = novo_usuario("Dra. Ana")["id"]
    assert db.get_medico(uid)["crm"] is None
    m = db.update_medico(uid, {"crm": "123456", "crm_uf": "SP", "consultorio_endereco": "Rua A, 1", "invadir": "x"})
    assert (m["name"], m["crm"], m["crm_uf"], m["consultorio_endereco"]) == ("Dra. Ana", "123456", "SP", "Rua A, 1")
    assert db.update_medico(uid, {"receita_papel": "A5"})["receita_papel"] == "A5"


def test_login_google_nao_troca_o_nome_da_receita(novo_usuario):
    """O nome corrigido em Configurações (cabeçalho da receita) fica; o do Google só preenche nome vazio."""
    u = novo_usuario("Dra. Ana")
    db.update_medico(u["id"], {"name": "Dra. Ana Souza Lima"})
    assert db.upsert_user(u["email"], "Ana Souza", None, "sub-" + uuid.uuid4().hex)["name"] == "Dra. Ana Souza Lima"
    assert db.get_medico(u["id"])["name"] == "Dra. Ana Souza Lima"
    vazio = novo_usuario("")
    assert db.upsert_user(vazio["email"].upper(), "Beto Google", None, "sub-" + uuid.uuid4().hex)["name"] == "Beto Google"


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


def test_renomear_a_de_exemplo_nao_tira_a_marca(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    assert not db.has_example(uid)
    pid = exemplo.seed(uid)
    assert db.has_example(uid)
    p = db.update_patient(uid, pid, {"name": "Maria Teste"})
    assert p["name"] == "Maria Teste" and p["example"] and p["key"] == db.EXAMPLE_KEY
    assert len(db.list_notes(uid, pid, db.EXAMPLE_KEY)) == 17
    with db.connection() as c:
        marcas = c.execute("select distinct patient_key, patient_name from clinical_notes where user_id = %s", (uid,)).fetchall()
    assert marcas == [(db.EXAMPLE_KEY, "Maria Teste")]                   # as evoluções levam o nome novo e a mesma marca
    assert exemplo.seed(uid) is None                                     # continua sendo a de exemplo: não ganha outra
    real = db.create_patient(uid, "Ana Real")
    assert db.update_patient(uid, real["id"], {"name": "Ana Souza"})["key"] == "ana souza"   # paciente real: a chave segue o nome
    assert db.delete_patient(uid, pid) == "ok"                           # e a renomeada ainda sai com tudo


def test_exemplo_com_consulta_de_verdade_nao_e_excluido(novo_usuario):
    from app import exemplo
    uid, outro = novo_usuario()["id"], novo_usuario()["id"]
    pid = exemplo.seed(uid)
    db.upsert_note(uid, pid, db.EXAMPLE_KEY, db.EXAMPLE_NAME, "ev-real", "Consulta", None, "S: consulta de verdade")
    assert db.delete_patient(uid, pid) == "has_notes"                    # evolução de consulta da agenda: fica
    assert len(db.list_notes(uid, pid, db.EXAMPLE_KEY)) == 18 and len(db.list_files(uid, pid)) == 1   # nada saiu
    pid2 = exemplo.seed(outro)
    db.upsert_note(outro, pid2, db.EXAMPLE_KEY, db.EXAMPLE_NAME, "ev-vazia", "Consulta", None, "")    # abriu, não escreveu
    assert db.delete_patient(outro, pid2) == "ok"
    assert db.list_notes(outro, pid2, db.EXAMPLE_KEY) == [] and not db.has_example(outro)


def _exemplo_fica(uid, pid):
    """A de exemplo com algo que o médico gravou nela: não sai, e nada dela some."""
    assert db.delete_patient(uid, pid) == "has_notes"
    assert len(db.list_notes(uid, pid, db.EXAMPLE_KEY)) >= 17 and len(db.list_receitas(uid, pid)) >= 11
    assert db.EXAMPLE_FILE in [f["name"] for f in db.list_files(uid, pid)]


def test_exemplo_so_sai_com_o_que_e_do_exemplo(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    f = db.add_file(uid, pid, "exame.pdf", "application/pdf", b"%PDF-1.7 de verdade")
    _exemplo_fica(uid, pid)                                               # exame anexado pelo médico
    assert db.delete_file(uid, f["id"]) == pid
    f = db.add_file(uid, pid, db.EXAMPLE_FILE, "application/pdf", b"%PDF-1.7 de verdade")
    _exemplo_fica(uid, pid)                                               # mesmo nome do laudo, mas anexado depois
    assert db.delete_file(uid, f["id"]) == pid
    r = db.create_receita(uid, pid, [{"nome": "Losartana", "dose": "50 mg"}])
    _exemplo_fica(uid, pid)                                               # rascunho de receita
    assert db.delete_receita(uid, r["id"]) == pid
    rid = str(uuid.uuid4())
    assert db.rec_open(uid, pid, rid, None, None, "2026-10-15T10:00:00Z")
    _exemplo_fica(uid, pid)                                               # gravação (mesmo sem trecho)
    assert db.rec_delete(uid, rid) == pid
    assert db.cancel_receita(uid, db.list_receitas(uid, pid)[0]["id"], "Teste")   # cancelar a fictícia: continua fictícia
    db.upsert_note(uid, pid, db.EXAMPLE_KEY, db.EXAMPLE_NAME, None, None, None, "")   # avulsa aberta e não escrita
    assert db.delete_patient(uid, pid) == "ok"                            # só o exemplo: sai inteiro
    with db.connection() as c:
        sobra = [c.execute(f"select count(*) from {t} where user_id = %s", (uid,)).fetchone()[0]
                 for t in ("patients", "clinical_notes", "receitas", "patient_files", "recordings")]
    assert sobra == [0, 0, 0, 0, 0]


def test_exemplo_com_registro_do_medico_nao_e_excluido(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    notas = db.list_notes(uid, pid, db.EXAMPLE_KEY)
    exame = next(n for n in notas if not n["signed_at"])                  # "Resultado de exames" fictício (não finalizado)
    consulta = next(n for n in notas if n["signed_at"])

    def desfaz(sql, *args):                                               # só no banco de testes: volta ao exemplo puro
        with db.connection() as c:
            c.execute(sql, args)
            c.commit()
    r = db.create_receita(uid, pid, [{"nome": "Amoxicilina"}])
    assert db.emit_receita(uid, r["id"], [("simples", [{"nome": "Amoxicilina"}])])
    _exemplo_fica(uid, pid)                                               # receita emitida sem consulta (renovação)
    desfaz("delete from receitas where id = %s", r["id"])
    nid = db.upsert_note(uid, pid, db.EXAMPLE_KEY, db.EXAMPLE_NAME, None, None, None, "S: paciente de verdade")
    _exemplo_fica(uid, pid)                                               # evolução avulsa escrita nela
    assert db.finalize_note(uid, nid)
    _exemplo_fica(uid, pid)                                               # e finalizada
    desfaz("delete from clinical_notes where id = %s", nid)
    assert db.update_note(uid, exame["id"], "Resultado de exames: HbA1c 7,0%", exame["data"])
    _exemplo_fica(uid, pid)                                               # registro fictício editado pelo médico
    desfaz("update clinical_notes set updated_at = created_at where id = %s", exame["id"])
    assert db.finalize_note(uid, exame["id"])
    _exemplo_fica(uid, pid)                                               # registro fictício finalizado pelo médico
    desfaz("update clinical_notes set signed_at = null where id = %s", exame["id"])
    assert db.add_addendum(uid, consulta["id"], "Adendo de verdade")
    _exemplo_fica(uid, pid)                                               # adendo numa consulta fictícia
    desfaz("delete from note_addenda where note_id = %s", consulta["id"])
    assert db.delete_patient(uid, pid) == "ok"                            # cada um, sozinho, já a segurava


def test_evolucao_da_consulta_nao_passa_para_outro_paciente(novo_usuario):
    uid = novo_usuario()["id"]
    ana, bruno = db.create_patient(uid, "Ana Troca"), db.create_patient(uid, "Bruno Troca")

    def salva(p, ev, texto):
        return db.upsert_note(uid, p["id"], p["key"], p["name"], ev, "Consulta", None, texto)
    nid = salva(ana, "ev-troca", "S: dor de cabeça")
    with pytest.raises(db.NoteOtherPatient):                             # rascunho da Ana: não vira o texto do Bruno
        salva(bruno, "ev-troca", "S: outro texto")
    n = db.get_note(uid, nid)
    assert n["content"] == "S: dor de cabeça" and n["patient_id"] == ana["id"]
    assert salva(ana, "ev-troca", "S: dor de cabeça forte") == nid       # a dona continua escrevendo
    assert db.finalize_note(uid, nid)
    with pytest.raises(db.NoteOtherPatient):                             # finalizada da Ana: o 409 próprio, não "finalizada"
        salva(bruno, "ev-troca", "S: outro texto")
    with pytest.raises(db.NoteLocked):
        salva(ana, "ev-troca", "S: mudança")
    vazia = salva(ana, "ev-vazia", "")                                   # escreveu e apagou: nada a proteger
    assert salva(bruno, "ev-vazia", "S: do Bruno") == vazia and db.get_note(uid, vazia)["patient_id"] == bruno["id"]
    with db.connection() as c:                                           # evolução antiga, só com o nome (sem o id)
        c.execute("update clinical_notes set patient_id = null where id = %s", (vazia,)); c.commit()
    with pytest.raises(db.NoteOtherPatient):
        salva(ana, "ev-vazia", "S: da Ana")
    assert salva(bruno, "ev-vazia", "S: do Bruno de novo") == vazia      # pelo nome é a do Bruno
    assert db.get_note(uid, vazia)["patient_id"] == bruno["id"]


def test_gravacao_nao_entra_na_consulta_com_evolucao_de_outro_paciente(novo_usuario):
    """A mesma regra do NoteOtherPatient para a gravação: escrita ou finalizada para outro paciente, recusa."""
    uid = novo_usuario()["id"]
    ana, bruno = db.create_patient(uid, "Ana Grava"), db.create_patient(uid, "Bruno Grava")
    outro = lambda p, ev: db.event_note_other_patient(uid, ev, p["id"], p["key"])  # noqa: E731
    assert not outro(bruno, "ev-g") and not outro(bruno, None)            # consulta sem evolução ou avulsa: grava
    nid = db.upsert_note(uid, ana["id"], ana["key"], ana["name"], "ev-g", "Consulta", None, "S: dor de cabeça")
    assert outro(bruno, "ev-g") and not outro(ana, "ev-g")
    assert not db.event_note_other_patient(novo_usuario("Outro")["id"], "ev-g", bruno["id"], bruno["key"])   # de outro médico
    db.finalize_note(uid, nid)
    assert outro(bruno, "ev-g")
    vazia = db.upsert_note(uid, ana["id"], ana["key"], ana["name"], "ev-v", "Consulta", None, "")
    assert vazia and not outro(bruno, "ev-v")                             # vazia: passa para quem gravar/salvar


def _marcas(uid):
    with db.connection() as c:
        return c.execute("select patient_id, note_id from access_log where user_id = %s and action = %s",
                         (uid, db.EXAMPLE_DELETED)).fetchall()


def test_excluir_a_de_exemplo_deixa_a_marca_e_ela_nao_volta(novo_usuario):
    from app import exemplo
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    db.log_access(uid, "view", pid)
    assert _marcas(uid) == []
    assert db.delete_patient(uid, pid) == "ok"
    assert _marcas(uid) == [(None, None)]                                # sem paciente nem evolução: sobrevive a ela
    assert exemplo.seed(uid) is None                                     # nem o cadastro a cria de novo
    exemplo._conferidas.discard(uid)
    assert exemplo.garante(uid) is None and not db.has_example(uid)      # nem a conferência
    db.cleanup_old_records()                                             # a limpeza diária não leva a marca
    real = db.create_patient(uid, "Paciente Real")
    assert db.delete_patient(uid, real["id"]) == "ok"                    # só a de exemplo deixa marca
    assert _marcas(uid) == [(None, None)]
    exemplo._conferidas.discard(uid)
    assert exemplo.garante(uid) is None and not db.has_example(uid)


def test_conta_sem_a_de_exemplo_ganha_a_sua_uma_vez_so(novo_usuario):
    """Conta de antes da paciente de exemplo (ou cuja criação falhou no cadastro): a conferência cria a sua, inteira,
    e várias ao mesmo tempo criam uma só."""
    from concurrent.futures import ThreadPoolExecutor
    from app import exemplo
    uid = novo_usuario()["id"]
    assert not db.has_example(uid)
    exemplo._conferidas.discard(uid)
    with ThreadPoolExecutor(4) as ex:
        ids = [i for i in ex.map(lambda _: exemplo.garante(uid), range(4)) if i]
    assert len(ids) == 1
    with db.connection() as c:
        n = c.execute("select count(*) from patients where user_id = %s and patient_key = %s", (uid, db.EXAMPLE_KEY)).fetchone()[0]
    assert n == 1
    ps = db.list_patients(uid)
    assert [(p["id"], p["example"], p["notes"]) for p in ps] == [(ids[0], True, 17)]
    assert len(db.list_receitas(uid, ids[0])) == 11 and len(db.list_files(uid, ids[0])) == 1
    exemplo._conferidas.discard(uid)
    assert exemplo.garante(uid) is None and len(db.list_patients(uid)) == 1   # já tem: nada muda


def test_a_de_exemplo_sem_receitas_e_sem_laudo_e_completada(novo_usuario):
    """A de exemplo de antes das receitas (ou cujo extra falhou na criação): a conferência grava as receitas, ligadas
    às consultas fictícias e com as datas delas, e o mesmo laudo; ela continua podendo ser excluída. Com o laudo excluído
    pelo médico, ou com algo dele gravado nela, nada volta."""
    from app import exemplo

    def tira(sql, *args):                                                 # só no banco de testes: uma Maria de antes
        with db.connection() as c:
            c.execute(sql, args)
            c.commit()
    uid = novo_usuario()["id"]
    pid = exemplo.seed(uid)
    rx0 = sorted((r["note_id"], r["emitida_em"], [i["nome"] for i in r["itens"]]) for r in db.list_receitas(uid, pid))
    laudo0 = db.get_file(uid, db.list_files(uid, pid)[0]["id"])["data"]
    tira("delete from receitas where user_id = %s", uid)
    tira("delete from patient_files where user_id = %s", uid)
    assert db.example_state(uid) == (pid, False, False, False)
    exemplo._conferidas.discard(uid)
    assert exemplo.garante(uid) is None
    rx = sorted((r["note_id"], r["emitida_em"], [i["nome"] for i in r["itens"]]) for r in db.list_receitas(uid, pid))
    assert len(rx) == 11 and rx == rx0                                    # as mesmas receitas, nas mesmas consultas
    fs = db.list_files(uid, pid)
    assert [f["name"] for f in fs] == [db.EXAMPLE_FILE] and db.get_file(uid, fs[0]["id"])["data"] == laudo0
    assert db.example_state(uid) == (pid, False, True, True)
    assert db.delete_patient(uid, pid) == "ok"                            # continua só do exemplo

    outro = novo_usuario()["id"]                                          # o médico excluiu o laudo: não volta
    pid2 = exemplo.seed(outro)
    assert db.delete_file(outro, db.list_files(outro, pid2)[0]["id"]) == pid2
    db.log_access(outro, "file_delete", pid2)                             # como a rota registra
    exemplo._conferidas.discard(outro)
    exemplo.garante(outro)
    assert db.list_files(outro, pid2) == [] and len(db.list_receitas(outro, pid2)) == 11

    terceiro = novo_usuario()["id"]                                       # algo do médico nela: fica como está
    pid3 = exemplo.seed(terceiro)
    tira("delete from receitas where user_id = %s", terceiro)
    db.upsert_note(terceiro, pid3, db.EXAMPLE_KEY, db.EXAMPLE_NAME, None, None, None, "S: paciente de verdade")
    exemplo._conferidas.discard(terceiro)
    exemplo.garante(terceiro)
    assert db.list_receitas(terceiro, pid3) == []


def test_busca_de_pacientes_ve_todos(novo_usuario):
    """GET /patients corta nos mais recentes; a busca (POST /patients/search) procura o nome entre todos, sem acento nem
    maiúscula, acha a de exemplo pelo nome e nunca traz paciente de outro médico."""
    from app import exemplo
    uid, outro = novo_usuario()["id"], novo_usuario()["id"]
    antigo = db.create_patient(uid, "Otávio Antigo")
    with db.connection() as c:
        c.execute("update patients set updated_at = now() - interval '1 year' where id = %s", (antigo["id"],))
        c.commit()
    for i in range(3):
        db.create_patient(uid, f"Recente {i}")
    exemplo.seed(uid)
    db.create_patient(outro, "Otávio do Outro")
    assert antigo["id"] not in [p["id"] for p in db.list_patients(uid, 3)]          # fora da lista cortada
    assert [p["id"] for p in db.list_patients(uid, 200, q="otavio")] == [antigo["id"]]
    assert [p["name"] for p in db.list_patients(uid, 200, q="  OTÁVIO   antigo ")] == ["Otávio Antigo"]
    assert [p["example"] for p in db.list_patients(uid, 200, q="maria sil")] == [True]
    assert db.list_patients(uid, 200, q="exemplo") == []                           # nem pela chave dela (" exemplo")
    assert db.list_patients(uid, 200, q="100%") == [] and db.list_patients(uid, 200, q="_") == []   # sem curinga
    r = db.list_patients(uid, 2, q="recente")
    assert [p["name"] for p in r] == ["Recente 2", "Recente 1"] and r[0]["notes"] == 0 and r[0]["last"] is None


def test_trava_do_banco_vale_entre_conexoes(test_db):
    """A trava por chave (pg_advisory_xact_lock): enquanto uma conexão a segura, outra espera ou desiste no prazo;
    solta ao sair. É o que faz duas gerações, cada uma num servidor, mexerem na receita uma de cada vez."""
    import threading
    import time
    pegou, solta = threading.Event(), threading.Event()

    def segura():
        with db.trava("teste:trava") as ok:
            assert ok
            pegou.set()
            solta.wait(5)
    t = threading.Thread(target=segura)
    t.start()
    assert pegou.wait(10)
    with db.trava("teste:trava", espera=0.3) as ok:
        assert not ok                                                    # ocupada: desiste no prazo
    with db.trava("teste:outra", espera=0.3) as ok:
        assert ok                                                        # outra chave não espera
    t0 = time.monotonic()
    threading.Timer(0.5, solta.set).start()
    with db.trava("teste:trava", espera=5) as ok:
        assert ok and time.monotonic() - t0 >= 0.4                       # esperou a primeira soltar
    t.join(5)
