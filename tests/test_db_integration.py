"""Testes contra um banco de verdade — o de TESTES (fixture test_db, ver conftest.py). Sem
TEST_DATABASE_URL eles são pulados; nunca tocam produção. Cada teste cria os próprios usuários e
apaga tudo no fim."""
import contextlib
import datetime
import os
import re
import uuid

import pytest

from app import db


@pytest.fixture
def novo_usuario(test_db):
    criados = []

    def criar(nome="Teste", crm=None):
        u = db.create_email_user(f"teste-{uuid.uuid4().hex[:12]}@example.invalid", nome, "x", crm=crm)
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
        # os 30 s contam do código que ainda dá para usar: o usado e o que acabou nas tentativas não seguram o novo
        assert db.new_login_code(email, "hash-2")[0] == "ok"                           # o anterior já foi usado
        assert db.new_login_code(email, "hash-2b")[0] == "aguarde"                     # este ainda vale
        for _ in range(db.CODE_MAX_ATTEMPTS):
            db.check_login_code(email, "hash-errado")
        assert db.new_login_code(email, "hash-3")[0] == "ok"
        assert db.check_login_code(email, "hash-3")[0] == "ok"
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
    assert db.rec_segment(ana, rid, 1) == {"text": "Pressão 128 por 82.", "duvidas": ["82"], "falas": []}   # sem rótulo (0023)
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


def test_busca_de_receitas(novo_usuario):
    """Busca da aba Receitas (POST /prontuario/receitas/busca): o termo no nome do paciente ou de um remédio, sem acento
    nem maiúscula e sem curinga; só as do médico, da mais nova para a mais velha; o rascunho vazio fica de fora. A de
    exemplo é achada pelo nome, nunca pela chave."""
    from app import exemplo
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    joao, outra = db.create_patient(ana, "João Conceição"), db.create_patient(ana, "Outra Pessoa")
    r = db.create_receita(ana, joao["id"], [{"nome": "Losartana"}])
    emit = db.emit_receita(ana, r["id"], [("simples", [{"nome": "Losartana", "dose": "50 mg"}, {"nome": "Ácido fólico"}]),
                                          ("especial", [{"nome": "Sertralina", "dose": " 50 mg "}])])
    canc = db.cancel_receita(ana, emit[1]["id"], "Dose errada")
    ureia = db.create_receita(ana, outra["id"], [{"nome": "Ureia 10%", "dose": "creme"}])    # rascunho com remédio: entra
    vazio = db.create_receita(ana, outra["id"], [])                                         # rascunho vazio: fora
    busca = lambda uid, q, n=30: db.search_receitas(uid, q, n)                              # noqa: E731
    ids = lambda uid, q: {x["id"] for x in busca(uid, q)}                                   # noqa: E731
    assert ids(ana, "  CONCEICAO ") == ids(ana, "joão") == {emit[0]["id"], canc["id"]}       # pelo paciente
    assert ids(ana, "acido FOL") == {emit[0]["id"]} and ids(ana, "sertralína") == {canc["id"]}   # pelo remédio; cancelada entra
    assert ids(ana, "10%") == ids(ana, "%") == {ureia["id"]}                                 # % é letra
    assert busca(ana, "l%a") == [] and busca(ana, "u_eia") == [] and busca(ana, "_") == []  # sem curinga
    todas = busca(ana, "", 20)
    assert [x["id"] for x in todas][0] == ureia["id"] and {x["id"] for x in todas} == {ureia["id"], emit[0]["id"], canc["id"]}
    assert vazio["id"] not in ids(ana, "outra")
    (s,) = [x for x in todas if x["id"] == emit[0]["id"]]
    assert s == {"id": emit[0]["id"], "patient_id": joao["id"], "patient": "João Conceição", "tipo": "simples",
                 "status": "emitida", "data": emit[0]["emitida_em"], "remedios": ["Losartana 50 mg", "Ácido fólico"]}
    (c,) = [x for x in todas if x["id"] == canc["id"]]
    assert (c["tipo"], c["status"], c["remedios"]) == ("especial", "cancelada", ["Sertralina 50 mg"])
    assert busca(beto, "") == [] and busca(beto, "conceicao") == [] and busca(beto, "losartana") == []   # de outro médico
    # o join também confere o dono do paciente: receita (inconsistente) da Ana apontando para paciente do Beto não aparece
    carlos = db.create_patient(beto, "Carlos do Beto")
    with db.connection() as c:
        c.execute("""insert into receitas (user_id, patient_id, status, itens)
                     values (%s, %s, 'emitida', '[{"nome": "Losartana"}]'::jsonb)""", (ana, carlos["id"]))
        c.commit()
    assert busca(ana, "carlos") == [] and ids(ana, "losartana") == {emit[0]["id"]} and busca(beto, "carlos") == []
    # a de exemplo: pelo nome ("Maria Silva"), nunca pela chave; da mais nova para a mais velha; o limite vale
    exemplo.seed(ana)
    maria = busca(ana, "maria")
    assert maria and {x["patient"] for x in maria} == {db.EXAMPLE_NAME} and busca(ana, "exemplo") == []
    datas = [x["data"] for x in busca(ana, "")]
    assert datas == sorted(datas, reverse=True) and len(busca(ana, "", 2)) == 2


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


def test_conta_pela_conta_google(novo_usuario):
    """O `sub` do Google acha a conta mesmo depois de o e-mail mudar no Google; vazio não acha nenhuma."""
    u = novo_usuario("Ana")
    sub = "sub-" + uuid.uuid4().hex
    db.upsert_user(u["email"], None, None, sub)
    assert db.user_by_google_sub(sub)["id"] == u["id"]
    assert db.user_by_google_sub("sub-" + uuid.uuid4().hex) is None
    assert db.user_by_google_sub("") is None and db.user_by_google_sub(None) is None


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


def test_limpeza_tira_a_agenda_so_da_conta_recusada(novo_usuario):
    """A recusa apaga a agenda conectada no cadastro; a limpeza diária cobre a falha dela (e uma volta do Google que a
    recusa não viu). Pendente, aprovada e conta antiga ficam com a agenda."""
    agora = datetime.datetime.now(datetime.timezone.utc)
    recusada = novo_usuario(crm={"crm": _crm_novo(), "uf": "SP", "status": "pendente"})["id"]
    pendente = novo_usuario(crm={"crm": _crm_novo(), "uf": "SP", "status": "pendente"})["id"]
    aprovada = novo_usuario(crm={"crm": _crm_novo(), "uf": "SP", "status": "pendente"})["id"]
    antiga = novo_usuario()["id"]
    db.decide_crm(recusada, False)
    db.decide_crm(aprovada, True)
    for uid in (recusada, pendente, aprovada, antiga):
        db.set_token(uid, "google", access_token="a", refresh_token="r", expires_at=agora + datetime.timedelta(hours=1),
                     scope="calendar.events", account_email="ana@gmail.com")
    assert db.cleanup_old_records()["oauth_tokens_recusadas"] >= 1
    assert db.get_token(recusada, "google") is None
    assert all(db.get_token(uid, "google") for uid in (pendente, aprovada, antiga))


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


# ----- conferência do CRM no cadastro (0017_crm.sql) -----

def _crm_novo():
    return str(1000000 + uuid.uuid4().int % 8999999)          # 7 dígitos que nenhuma outra conta de teste usa


def _crm_cols(uid):
    with db.connection() as c:
        return c.execute("""select crm, crm_uf, crm_status, crm_fonte, crm_situacao, crm_verificado_em is not null,
                                   crm_pedido_em is not null from users where id = %s""", (uid,)).fetchone()


def test_conta_antiga_segue_sem_conferencia(novo_usuario):
    u = novo_usuario()
    assert (u["crm_status"], u["crm_fonte"]) == (None, None)
    assert _crm_cols(u["id"])[2:] == (None, None, None, False, False)


def test_cadastro_pendente_aprovado_a_mao_e_confirmado(novo_usuario):
    n = _crm_novo()
    u = novo_usuario("Ana Lima", crm={"crm": n, "uf": "SP", "status": "pendente"})
    assert (u["crm_status"], u["crm_fonte"]) == ("pendente", None)
    assert _crm_cols(u["id"]) == (n, "SP", "pendente", None, None, False, True)
    assert db.password_login_info(u["email"])["crm_status"] == "pendente"
    assert db.crm_in_use(n, "SP") and not db.crm_in_use(n, "RJ")
    outro = novo_usuario("Ana Lima", crm={"crm": n, "uf": "SP", "status": "pendente"})
    meus = {p["id"]: p for p in db.pending_doctors() if p["id"] in (u["id"], outro["id"])}
    assert meus[u["id"]]["crm"] == n and meus[u["id"]]["outras_contas"] == 1 and meus[u["id"]]["name"] == "Ana Lima"
    assert db.decide_crm(outro["id"], False)["email"] == outro["email"]
    assert db.get_user(outro["id"])["crm_status"] == "recusado"
    assert [p for p in db.pending_doctors() if p["id"] == u["id"]][0]["outras_contas"] == 0   # recusada não conta
    assert db.decide_crm(u["id"], True)["id"] == u["id"]
    assert db.decide_crm(u["id"], False) is None                                       # já decidido: não muda
    assert _crm_cols(u["id"])[2:] == ("verificado", "manual", None, True, True)
    assert all(p["id"] != u["id"] for p in db.pending_doctors())
    assert db.crm_confirmed(u["id"]) is True and db.get_user(u["id"])["crm_fonte"] == "cfm"
    assert db.crm_confirmed(u["id"]) is False                                          # uma vez só


def test_cadastro_verificado_no_cfm_e_google_sem_trocar_o_crm(novo_usuario):
    n = _crm_novo()
    u = novo_usuario("Ana Lima", crm={"crm": n, "uf": "MG", "status": "verificado", "fonte": "cfm", "situacao": "A"})
    assert _crm_cols(u["id"]) == (n, "MG", "verificado", "cfm", "A", True, False)
    # entrar depois pelo Google (conta que já existe) não mexe no CRM
    assert db.upsert_user(u["email"], "Outro Nome", None, None, crm={"crm": "1", "uf": "SP", "status": "pendente"})["crm_status"] == "verificado"
    assert _crm_cols(u["id"])[:3] == (n, "MG", "verificado")
    # conta nova pelo Google, com o Registro profissional
    email = f"teste-{uuid.uuid4().hex[:12]}@example.invalid"
    g = db.upsert_user(email, "Bia Souza", None, "sub-" + uuid.uuid4().hex, crm={"crm": _crm_novo(), "uf": "RJ", "status": "pendente"})
    try:
        assert (g["crm_status"], g["name"]) == ("pendente", "Bia Souza")
        assert db.get_user(g["id"])["crm_status"] == "pendente"
    finally:
        with db.connection() as c:
            c.execute("delete from users where id = %s", (g["id"],))
            c.commit()


def test_crm_repetido_decidido_na_hora_de_criar_a_conta(novo_usuario):
    """Dois cadastros do mesmo CRM/UF começados antes de qualquer conta existir: os dois tíquetes dizem 'verificado',
    mas quem decide é o banco, na hora de criar (db._crm_decisao) — o 2º nasce pendente e sem fonte."""
    n = _crm_novo()
    dec = {"crm": n, "uf": "SP", "status": "verificado", "fonte": "cfm", "situacao": "A"}
    a = novo_usuario("Ana Lima", crm=dec)
    b = novo_usuario("Ana Lima", crm=dec)
    assert (a["crm_status"], a["crm_fonte"]) == ("verificado", "cfm")
    assert (b["crm_status"], b["crm_fonte"]) == ("pendente", None)
    assert _crm_cols(b["id"]) == (n, "SP", "pendente", None, "A", False, True)
    assert [p["outras_contas"] for p in db.pending_doctors() if p["id"] == b["id"]] == [1]
    # pelo Google também (conta nova com o Registro profissional)
    email = f"teste-{uuid.uuid4().hex[:12]}@example.invalid"
    g = db.upsert_user(email, "Ana Lima", None, "sub-" + uuid.uuid4().hex, crm=dec)
    try:
        assert (g["crm_status"], g["crm_fonte"]) == ("pendente", None)
    finally:
        with db.connection() as c:
            c.execute("delete from users where id = %s", (g["id"],))
            c.commit()
    # conta recusada com o mesmo CRM não conta; outra UF também não
    m = _crm_novo()
    r = novo_usuario("Outra Pessoa", crm={"crm": m, "uf": "RJ", "status": "pendente"})
    db.decide_crm(r["id"], False)
    assert novo_usuario("Ana Lima", crm=dict(dec, crm=m, uf="RJ"))["crm_status"] == "verificado"
    assert novo_usuario("Ana Lima", crm=dict(dec, crm=m, uf="MG"))["crm_status"] == "verificado"


def test_crm_repetido_com_cadastros_ao_mesmo_tempo(novo_usuario):
    """Os verify do mesmo CRM chegando juntos (conexões diferentes, como dois processos): um só fica verificado."""
    import threading
    n = _crm_novo()
    dec = {"crm": n, "uf": "BA", "status": "verificado", "fonte": "cfm", "situacao": "A"}
    largada, contas, erros = threading.Barrier(3), [], []

    def cria():
        try:
            largada.wait(10)
            contas.append(novo_usuario("Ana Lima", crm=dec))
        except Exception as e:          # o teste mostra o erro
            erros.append(e)
    ts = [threading.Thread(target=cria) for _ in range(3)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert erros == []
    assert sorted(u["crm_status"] for u in contas) == ["pendente", "pendente", "verificado"]


def test_limite_de_conferencias_no_cfm_no_banco(test_db):
    """O contador por CRM vale entre processos (está no banco): até `maximo` na janela; outra chave conta à parte."""
    k1, k2 = f"teste:{uuid.uuid4().hex}", f"teste:{uuid.uuid4().hex}"
    try:
        assert [db.cfm_tentativa_usa(k1, 2, 3600) for _ in range(3)] == [True, True, False]
        assert db.cfm_tentativas(k1, 3600) == 2 and db.cfm_tentativas(k1, 0) == 0
        assert db.cfm_tentativa_usa(k2, 2, 3600) is True
        db.cfm_tentativa_registra(k2)
        assert db.cfm_tentativas(k2, 3600) == 2 and db.cfm_tentativa_usa(k2, 2, 3600) is False
        with db.connection() as c:                                   # passou da janela: volta a valer
            c.execute("update cfm_tentativas set created_at = now() - interval '2 hours' where chave = %s", (k1,))
            c.commit()
        assert db.cfm_tentativa_usa(k1, 2, 3600) is True
        assert "cfm_tentativas" in db.RETENTION
    finally:
        with db.connection() as c:
            c.execute("delete from cfm_tentativas where chave in (%s, %s)", (k1, k2))
            c.commit()


# ----- aprovada à mão liberada sem a confirmação no CFM (0019_crm_dispensado.sql) -----

def _dispensado_em(uid):
    with db.connection() as c:
        return c.execute("select crm_dispensado_em from users where id = %s", (uid,)).fetchone()[0]


def test_liberar_aprovada_a_mao_sem_confirmar(novo_usuario):
    """A lista dos aprovados à mão (com o e-mail e as confirmações que não bateram), a liberação só de conta aprovada à
    mão, uma vez só (a data da primeira fica), e o usuário/login que passam a dizer que está liberada."""
    with db.connection() as c:
        assert db.tem_dispensa(c), "falta a 0019 no banco de testes"
    n = _crm_novo()
    u = novo_usuario("Ana Lima", crm={"crm": n, "uf": "SP", "status": "pendente"})
    assert [p["email"] for p in db.pending_doctors() if p["id"] == u["id"]] == [u["email"]]      # o e-mail na lista
    assert db.crm_dispensa(u["id"]) is None and _dispensado_em(u["id"]) is None              # pendente: não libera
    db.decide_crm(u["id"], True)
    falhas = "conf:" + u["id"]
    try:
        db.cfm_tentativa_registra(falhas)
        db.cfm_tentativa_registra(falhas)
        manuais, disp = db.manual_doctors(24 * 3600)
        meu = [m for m in manuais if m["id"] == u["id"]]
        assert disp is True and len(meu) == 1
        assert (meu[0]["email"], meu[0]["crm"], meu[0]["crm_uf"], meu[0]["falhas"]) == (u["email"], n, "SP", 2)
        assert meu[0]["aprovado_em"]
        assert db.get_user(u["id"])["crm_dispensado"] is False
        assert db.crm_dispensa(u["id"]) == {"id": u["id"], "email": u["email"], "name": "Ana Lima"}
        primeira = _dispensado_em(u["id"])
        assert primeira is not None
        assert db.crm_dispensa(u["id"])["id"] == u["id"] and _dispensado_em(u["id"]) == primeira   # de novo: nada muda
        assert all(m["id"] != u["id"] for m in db.manual_doctors(24 * 3600)[0])                      # saiu da lista
        assert db.get_user(u["id"])["crm_dispensado"] is True
        assert db.user_by_email(u["email"])["crm_dispensado"] is True
        assert db.password_login_info(u["email"])["crm_dispensado"] is True
        assert db.set_password(u["id"], "outro-hash")["crm_dispensado"] is True
    finally:
        with db.connection() as c:
            c.execute("delete from cfm_tentativas where chave = %s", (falhas,))
            c.commit()
    # conferida no CFM, recusada, antiga (sem CRM) ou inexistente: não libera
    cfm_ok = novo_usuario("Bia Souza", crm={"crm": _crm_novo(), "uf": "RJ", "status": "verificado", "fonte": "cfm", "situacao": "A"})
    recusada = novo_usuario("Caio Lima", crm={"crm": _crm_novo(), "uf": "MG", "status": "pendente"})
    db.decide_crm(recusada["id"], False)
    antiga = novo_usuario("Dora")
    for outra in (cfm_ok, recusada, antiga):
        assert db.crm_dispensa(outra["id"]) is None and _dispensado_em(outra["id"]) is None
        assert db.get_user(outra["id"])["crm_dispensado"] is False
    assert db.crm_dispensa(str(uuid.uuid4())) is None
    assert all(m["id"] not in (cfm_ok["id"], recusada["id"], antiga["id"]) for m in db.manual_doctors(24 * 3600)[0])


def test_aparelho_conhecido_e_id_de_paciente(novo_usuario):
    """device_known: a conta já entrou por este aparelho? patient_id_exists: o id é de algum paciente (qualquer médico)?"""
    ana, bia = novo_usuario("Ana")["id"], novo_usuario("Bia")["id"]
    db.record_login(ana, "entrou", "senha", "1.2.3.4", "UA", "dev-ana")
    db.record_login(ana, "senha_incorreta", "senha", "1.2.3.4", "UA", "dev-tentou")
    assert db.device_known(ana, "dev-ana") and not db.device_known(ana, "dev-tentou") and not db.device_known(bia, "dev-ana")
    assert not db.device_known(ana, None)
    p = db.create_patient(ana, "Paciente da Ana")
    assert db.patient_id_exists(p["id"]) and db.get_patient(bia, p["id"]) is None
    assert not db.patient_id_exists(p["id"] + 10_000_000)


def test_erradas_somadas_por_email_e_o_teto_do_aparelho_conhecido(test_db):
    """Pedir códigos novos não dá mais chutes: passadas 25 erradas na hora (somando os códigos do e-mail), nem o código
    certo vale. E o teto de envios do e-mail não vale para o aparelho conhecido (teto=False), os 30 s sim."""
    email = f"teste-{uuid.uuid4().hex[:12]}@example.invalid"
    try:
        for i in range(db.CODE_MAX_WRONG_PER_HOUR // db.CODE_MAX_ATTEMPTS):
            assert db.new_login_code(email, f"h{i}")[0] == "ok"
            for _ in range(db.CODE_MAX_ATTEMPTS):
                db.check_login_code(email, "errado")
        assert db.new_login_code(email, "certo")[0] == "limite"                 # passado o teto, nem manda código
        assert db.new_login_code(email, "certo", teto=False)[0] == "ok"        # o aparelho conhecido recebe
        assert db.check_login_code(email, "certo")[0] == "bloqueado_email"
        assert db.check_login_code(email, "certo", soma=False)[0] == "ok"      # e, dele, o código vale
        with db.connection() as c:
            c.execute("update login_codes set attempts = 0, used_at = now() where email = %s", (email,))   # recomeça sem chutes
            c.commit()
        while db.new_login_code(email, "x")[0] == "ok":
            db.check_login_code(email, "x")                                     # usado: o próximo não espera os 30 s
        assert db.new_login_code(email, "y")[0] == "limite"
        assert db.new_login_code(email, "z", teto=False)[0] == "ok"
        assert db.new_login_code(email, "w", teto=False)[0] == "aguarde"
    finally:
        with db.connection() as c:
            c.execute("delete from login_codes where email = %s", (email,))
            c.commit()


def test_excluir_conta_encerra_sem_apagar_o_prontuario_e_libera_o_email(novo_usuario):
    """Excluir a conta (Perfil): a linha não é apagada — o prontuário e o registro de acessos ficam pelo id antigo, com o
    nome e o CRM (autoria) — mas a conta não entra mais por e-mail, senha, Google, sessão ou tíquete; saem a agenda, os
    códigos de e-mail e o contador do CFM; e o mesmo e-mail, a mesma conta Google e o mesmo CRM criam uma conta nova,
    vazia e verificada. Uma segunda exclusão não muda nada, e a volta do Google depois dela não grava a agenda."""
    n = _crm_novo()
    dec = {"crm": n, "uf": "SP", "status": "verificado", "fonte": "cfm", "situacao": "A"}
    u = novo_usuario("Ana Souza", crm=dec)
    uid, email, sub = u["id"], u["email"], "sub-" + uuid.uuid4().hex
    db.upsert_user(email, None, None, sub)                       # entrou também pelo Google
    p = db.create_patient(uid, "Paciente Fictícia")
    db.log_access(uid, "view", p["id"])
    agora = datetime.datetime.now(datetime.timezone.utc)
    token = dict(access_token="a", refresh_token="r", expires_at=agora + datetime.timedelta(hours=1),
                 scope="calendar.events", account_email="ana@gmail.com")
    db.set_token(uid, "google", **token)
    assert db.new_login_code(email, "h" * 64)[0] == "ok"
    db.cfm_tentativa_registra("conf:" + uid)
    assert db.crm_in_use(n, "SP")

    assert db.excluir_conta(uid, "  " + email.upper()) == {"email": email, "name": "Ana Souza"}
    assert db.excluir_conta(uid, email) is None                  # já excluída
    # não entra mais
    assert db.get_user(uid) is None and db.user_by_email(email) is None and db.account(email) is None
    assert db.password_login_info(email) is None and db.user_by_google_sub(sub) is None
    assert db.set_password(uid, "outro-hash") is None
    assert db.upsert_user(email, None, None, sub, so_existente=True) is None
    assert db.create_email_user(email, "Ana", "z", so_existente=True) is None
    # o prontuário e a autoria ficam; o que era da conta sai
    assert [x["id"] for x in db.list_patients(uid)] == [p["id"]]
    with db.connection() as c:
        linha = c.execute("""select email, email_excluido, google_sub, google_sub_excluido, password_hash,
                                    excluida_em is not null, name, crm, crm_uf from users where id = %s""", (uid,)).fetchone()
        assert linha == ("excluida:" + uid, email, None, sub, None, True, "Ana Souza", n, "SP")
        acessos = dict(c.execute("select action, count(*) from access_log where user_id = %s group by action",
                                 (uid,)).fetchall())
        assert acessos == {"view": 1, "conta_excluida": 1}
        assert c.execute("select count(*) from oauth_tokens where user_id = %s", (uid,)).fetchone()[0] == 0
        assert c.execute("select count(*) from login_codes where lower(email) = %s", (email,)).fetchone()[0] == 0
        assert c.execute("select count(*) from cfm_tentativas where chave = %s", ("conf:" + uid,)).fetchone()[0] == 0
    db.set_token(uid, "google", **token)                         # a volta do Google que chegou depois
    assert db.get_token(uid, "google") is None
    assert not db.crm_in_use(n, "SP")                            # o CRM não conta mais como de outra conta
    db.cleanup_old_records()
    assert [x["id"] for x in db.list_patients(uid)] == [p["id"]]
    # a conta nova do mesmo médico: outro id, vazia, verificada (o CRM da excluída não a deixa pendente)
    nova = db.create_email_user(email, "Ana Souza", "y", crm=dec)
    try:
        assert nova["id"] != uid and nova["crm_status"] == "verificado" and db.list_patients(nova["id"]) == []
        assert db.user_by_email(email)["id"] == nova["id"]
        assert db.upsert_user(email, None, None, sub, so_existente=True)["id"] == nova["id"]
        assert db.user_by_google_sub(sub)["id"] == nova["id"]   # a mesma conta Google entra na nova
    finally:
        with db.connection() as c:
            c.execute("delete from patients where user_id = %s", (nova["id"],))
            c.execute("delete from users where id = %s", (nova["id"],))
            c.commit()


def test_conta_excluida_some_das_listas_dos_administradores(novo_usuario):
    """A aprovada à mão que se excluiu sai da lista de confirmação e não pode mais ser liberada; o CRM dela não aparece
    como "outra conta" no cadastro pendente do mesmo CRM."""
    n = _crm_novo()
    manual = novo_usuario("Bia Souza", crm={"crm": n, "uf": "RJ", "status": "pendente"})
    assert db.decide_crm(manual["id"], True)
    assert manual["id"] in [x["id"] for x in db.manual_doctors(86400)[0]]
    pendente = novo_usuario("Bia Souza", crm={"crm": n, "uf": "RJ", "status": "pendente"})
    assert next(x for x in db.pending_doctors() if x["id"] == pendente["id"])["outras_contas"] == 1
    assert db.excluir_conta(manual["id"], manual["email"])
    assert manual["id"] not in [x["id"] for x in db.manual_doctors(86400)[0]]
    assert db.crm_dispensa(manual["id"]) is None and db.crm_confirmed(manual["id"]) is False
    assert next(x for x in db.pending_doctors() if x["id"] == pendente["id"])["outras_contas"] == 0


def test_paciente_com_email_convenio_e_plano(novo_usuario):
    """Migração 0021: e-mail, particular/convênio e plano gravados, lidos e trocados; só com o nome ficam vazios."""
    uid = novo_usuario()["id"]
    p = db.create_patient(uid, "Joana Teste", phone="(11) 91234-5678", email="joana@exemplo.invalid",
                          coverage="convenio", health_plan="Plano Teste")
    g = db.get_patient(uid, p["id"])
    assert (g["phone"], g["email"], g["coverage"], g["health_plan"]) == (
        "(11) 91234-5678", "joana@exemplo.invalid", "convenio", "Plano Teste")
    u = db.update_patient(uid, p["id"], {"coverage": "particular", "health_plan": None})
    assert (u["coverage"], u["health_plan"], u["email"]) == ("particular", None, "joana@exemplo.invalid")
    s = db.create_patient(uid, "Só Nome Teste")
    assert (s["email"], s["coverage"], s["health_plan"]) == (None, None, None)
    with pytest.raises(Exception):                     # o banco também só aceita particular ou convênio
        db.create_patient(uid, "Outro Teste", coverage="sus")


def test_sem_a_migracao_0021_o_cadastro_segue(novo_usuario, monkeypatch):
    """Sem a 0021 (db.tem_contato falso): criar e editar sem os campos novos funciona; com eles, MigracaoPendente."""
    uid = novo_usuario()["id"]
    monkeypatch.setattr(db, "tem_contato", lambda conn: False)
    # o banco de testes já tem a 0021: o que prova é o SQL que sai (nenhuma consulta pode citar as colunas novas)
    vistos, real = [], db.connection

    class _Grava:
        def __init__(self, c):
            self.c = c

        def execute(self, sql, *a, **k):
            vistos.append(str(sql))
            return self.c.execute(sql, *a, **k)

        def __getattr__(self, nome):
            return getattr(self.c, nome)

    @contextlib.contextmanager
    def grava():
        with real() as c:
            yield _Grava(c)
    monkeypatch.setattr(db, "connection", grava)
    p = db.create_patient(uid, "Só Nome Teste")
    assert p["email"] is None and db.get_patient(uid, p["id"])["name"] == "Só Nome Teste"
    with pytest.raises(db.MigracaoPendente):
        db.create_patient(uid, "Com Email Teste", email="a@exemplo.invalid")
    with pytest.raises(db.MigracaoPendente):
        db.update_patient(uid, p["id"], {"email": "a@exemplo.invalid"})
    assert db.update_patient(uid, p["id"], {"name": "Outro Nome Teste", "email": None})["name"] == "Outro Nome Teste"
    assert db.find_patients(uid, "Outro Nome Teste") and vistos
    citam = [q for q in vistos if re.search(r"\b(email|coverage|health_plan)\b", q)]
    assert not citam, citam


WEBM = b"\x1a\x45\xdf\xa3" + bytes(64)
SESS, OUTRA = "sessao-aba-a-0001", "sessao-aba-b-0002"


def _add(*a, sess=SESS, max_part_bytes=10 ** 9):
    return db.rec_add_audio(*a, sess=sess, max_part_bytes=max_part_bytes)


def test_audio_da_gravacao(novo_usuario):
    """Migração 0022: o pedaço só entra na gravação deste médico e paciente (nunca a cria), uma vez só; o do meio precisa
    do começo da parte e herda o tipo; o teto de 24 h; só o dono ouve; apagar a transcrição leva o áudio (cascata)."""
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p, outro = db.create_patient(ana, "Paciente da Ana"), db.create_patient(ana, "Outro da Ana")
    rid, teto = str(uuid.uuid4()), 10 ** 9
    assert _add(ana, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, teto) == "sem_gravacao"
    with db.connection() as c:
        assert c.execute("select count(*) from recordings where id = %s", (rid,)).fetchone()[0] == 0
    assert db.rec_open(ana, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    assert _add(beto, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, teto) == "sem_gravacao"
    assert _add(ana, outro["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, teto) == "sem_gravacao"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"meio-1", teto) == "sem_inicio"
    assert _add(ana, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, teto) == "ok"
    assert _add(ana, p["id"], rid, 0, 0, 0.0, 5.0, "audio/ogg", b"OggS outro", teto) == "repetido"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"meio-1", teto) == "ok"
    assert _add(ana, p["id"], rid, 0, 3, 0.0, 20.0, None, b"meio-3", teto) == "ok"   # buraco no 2
    assert _add(ana, p["id"], rid, 0, 2, 0.0, 15.0, None, b"x" * 100, len(WEBM) + 20) == "teto"
    assert _add(ana, p["id"], rid, 1, 0, 40.0, 45.0, "audio/ogg", b"OggS" + bytes(8), teto) == "ok"
    with db.connection() as c:
        assert c.execute("select mime from recording_audio where rec_id = %s and part = 0 and n = 1",
                         (rid,)).fetchone()[0] == "audio/webm"                    # herdou da parte
    a = db.rec_audio(ana, rid, 0)
    assert a == {"mime": "audio/webm", "data": WEBM + b"meio-1", "patient_id": p["id"]}   # para no buraco
    assert db.rec_audio(ana, rid, 1)["mime"] == "audio/ogg" and db.rec_audio(ana, rid, 2) is None
    assert db.rec_audio(beto, rid, 0) is None
    (r,) = db.rec_list(ana, p["id"], event_id="ev1")
    assert r["audio"] == [{"part": 0, "at": 0.0, "upto": 10.0}, {"part": 1, "at": 40.0, "upto": 45.0}]
    assert db.delete_patient(ana, p["id"]) == "has_notes"            # gravação só com áudio também é prontuário
    assert db.rec_delete(ana, rid) == p["id"]
    with db.connection() as c:
        assert c.execute("select count(*) from recording_audio where rec_id = %s", (rid,)).fetchone()[0] == 0
    assert db.rec_audio(ana, rid, 0) is None
    assert db.delete_patient(ana, p["id"]) == "ok"


def test_audio_sessao_da_parte_e_teto_da_parte(novo_usuario):
    """Correções da revisão (docs/audio-contrato.md): o n = 0 grava o sess; outra sessão na mesma parte é "ocupada" (n = 0
    ou n > 0), "repetido" só com o mesmo sess; o teto por parte; o GET junta só os contíguos; rec_list pela PK (uuid[])."""
    ana = novo_usuario("Ana")["id"]
    p = db.create_patient(ana, "Paciente da Ana")
    rid = str(uuid.uuid4())
    assert db.rec_open(ana, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    assert _add(ana, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, 10 ** 9) == "ok"
    assert _add(ana, p["id"], rid, 0, 0, 0.0, 5.0, "audio/ogg", b"OggS x", 10 ** 9, sess=OUTRA) == "ocupada"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"de-b", 10 ** 9, sess=OUTRA) == "ocupada"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"meio-1", 10 ** 9) == "ok"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"meio-1", 10 ** 9) == "repetido"
    assert _add(ana, p["id"], rid, 0, 1, 0.0, 10.0, None, b"de-b", 10 ** 9, sess=OUTRA) == "ocupada"
    with db.connection() as c:
        linhas = c.execute("select n, sess, data from recording_audio where rec_id = %s and part = 0 order by n",
                           (rid,)).fetchall()
    assert [(n, sess, bytes(d)) for n, sess, d in linhas] == [(0, SESS, WEBM), (1, SESS, b"meio-1")]
    teto = len(WEBM) + len(b"meio-1") + 10                          # a parte 0 já tem quase tudo
    assert _add(ana, p["id"], rid, 0, 2, 0.0, 15.0, None, b"x" * 11, 10 ** 9, max_part_bytes=teto) == "teto_parte"
    assert _add(ana, p["id"], rid, 0, 2, 0.0, 15.0, None, b"x" * 10, 10 ** 9, max_part_bytes=teto) == "ok"
    assert _add(ana, p["id"], rid, 1, 0, 20.0, 25.0, "audio/webm", WEBM, 10 ** 9, max_part_bytes=10) == "teto_parte"
    assert _add(ana, p["id"], rid, 1, 0, 20.0, 25.0, "audio/ogg", b"OggS" + bytes(8), 10 ** 9, sess=OUTRA) == "ok"
    assert _add(ana, p["id"], rid, 1, 2, 20.0, 35.0, None, b"depois-do-buraco", 10 ** 9, sess=OUTRA) == "ok"
    assert db.rec_audio(ana, rid, 0)["data"] == WEBM + b"meio-1" + b"x" * 10
    assert db.rec_audio(ana, rid, 1)["data"] == b"OggS" + bytes(8)          # para no buraco (n = 1 não chegou)
    (r,) = db.rec_list(ana, p["id"], rec_ids=[rid])
    assert r["audio"] == [{"part": 0, "at": 0.0, "upto": 15.0}, {"part": 1, "at": 20.0, "upto": 25.0}]


def test_audio_migracao_0022_tem_a_coluna_sess_e_e_idempotente(novo_usuario):
    """A 0022 cria a tabela já com sess e, no banco que já tinha a tabela, acrescenta a coluna; rodar de novo não muda
    nada (o setup_test_db aplica todas as migrações a cada vez)."""
    sql = open(os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations", "0022_gravacao_audio.sql")).read()
    assert "add column if not exists sess text" in sql
    with db.connection() as c:
        c.execute(sql)
        c.commit()
        tipo = c.execute("""select data_type from information_schema.columns
                            where table_schema = 'public' and table_name = 'recording_audio' and column_name = 'sess'""").fetchone()
    assert tipo == ("text",)


def test_limpeza_apaga_o_audio_de_mais_de_um_ano_e_nunca_a_transcricao(novo_usuario):
    uid = novo_usuario()["id"]
    p = db.create_patient(uid, "Paciente Teste")
    rid = str(uuid.uuid4())
    assert db.rec_open(uid, p["id"], rid, "ev1", None, "2025-10-15T10:00:00Z")
    with db.connection() as c:
        c.execute("""insert into recording_segments (rec_id, seq, at_s, dur_s, text, created_at)
                     values (%s, 1, 0, 30, 'trecho antigo', now() - interval '13 months')""", (rid,))
        c.execute("""insert into recording_audio (rec_id, part, n, user_id, at_s, upto_s, mime, size, data, created_at) values
                     (%s, 0, 0, %s, 0, 5, 'audio/webm', 4, %s, now() - interval '13 months'),
                     (%s, 1, 0, %s, 60, 65, 'audio/webm', 4, %s, now() - interval '11 months')""",
                  (rid, uid, WEBM[:4], rid, uid, WEBM[:4]))
        c.commit()
    db.cleanup_old_records()
    with db.connection() as c:
        partes = [x[0] for x in c.execute("select part from recording_audio where rec_id = %s", (rid,)).fetchall()]
        trechos = c.execute("select count(*) from recording_segments where rec_id = %s", (rid,)).fetchone()[0]
        gravacoes = c.execute("select count(*) from recordings where id = %s", (rid,)).fetchone()[0]
    assert partes == [1] and trechos == 1 and gravacoes == 1     # só o áudio de 13 meses saiu


def test_excluir_conta_apaga_o_audio_e_deixa_a_transcricao(novo_usuario):
    u = novo_usuario("Ana Souza")
    uid = u["id"]
    p = db.create_patient(uid, "Paciente Fictícia")
    rid = str(uuid.uuid4())
    assert db.rec_open(uid, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    db.rec_add_segment(uid, rid, 1, 0.0, 20.0, "Pressão 128 por 82.", [])
    assert _add(uid, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, 10 ** 9) == "ok"
    assert db.excluir_conta(uid, u["email"])
    with db.connection() as c:
        audio = c.execute("select count(*) from recording_audio where user_id = %s", (uid,)).fetchone()[0]
        grav = c.execute("select count(*) from recordings where user_id = %s", (uid,)).fetchone()[0]
        trechos = c.execute("select count(*) from recording_segments where rec_id = %s", (rid,)).fetchone()[0]
    assert (audio, grav, trechos) == (0, 1, 1)


def test_sem_a_migracao_0022_a_gravacao_segue(novo_usuario, monkeypatch):
    """Sem a 0022 (db.tem_audio falso): o áudio espera (MigracaoPendente), ninguém ouve, a lista vem sem áudio, e a
    limpeza, a exclusão do paciente e a da conta não citam a tabela nova."""
    u = novo_usuario()
    uid = u["id"]
    p = db.create_patient(uid, "Paciente Teste")
    rid = str(uuid.uuid4())
    assert db.rec_open(uid, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    monkeypatch.setattr(db, "tem_audio", lambda conn: False)
    vistos, real = [], db.connection

    class _Grava:
        def __init__(self, c):
            self.c = c

        def execute(self, sql, *a, **k):
            vistos.append(str(sql))
            return self.c.execute(sql, *a, **k)

        def __getattr__(self, nome):
            return getattr(self.c, nome)

    @contextlib.contextmanager
    def grava():
        with real() as c:
            yield _Grava(c)
    monkeypatch.setattr(db, "connection", grava)
    with pytest.raises(db.MigracaoPendente):
        _add(uid, p["id"], rid, 0, 0, 0.0, 5.0, "audio/webm", WEBM, 10 ** 9)
    assert db.rec_audio(uid, rid, 0) is None
    assert db.rec_list(uid, p["id"], event_id="ev1")[0]["audio"] == []
    db.cleanup_old_records()
    assert db.delete_patient(uid, p["id"]) == "ok"                 # gravação vazia sai junto, como antes
    assert db.excluir_conta(uid, u["email"])
    citam = [q for q in vistos if "recording_audio" in q]
    assert vistos and not citam, citam


FALAS_T = [{"q": "m", "t": "Bom dia. Como passou?", "at": 0.0}, {"q": "p", "t": "Bem, doutora.", "at": 4.1}]


def test_falas_da_gravacao(novo_usuario):
    """Migração 0023: as falas entram com o trecho e voltam no reenvio, no trecho anterior e no estado; a troca do
    rótulo à mão marca manual e só vale para o médico dono, o paciente da gravação e uma fala que existe."""
    ana, beto = novo_usuario("Ana")["id"], novo_usuario("Beto")["id"]
    p, outro = db.create_patient(ana, "Paciente da Ana"), db.create_patient(ana, "Outro da Ana")
    rid = str(uuid.uuid4())
    assert db.rec_open(ana, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "Bom dia. Como passou? Bem, doutora.", [], FALAS_T)
    db.rec_add_segment(ana, rid, 2, 20.0, 20.0, "Sem rótulo.", [])                     # o rotulador falhou
    assert db.rec_segment(ana, rid, 1)["falas"] == FALAS_T
    assert db.rec_segment(ana, rid, 2)["falas"] == []
    assert db.rec_prev_segment(ana, rid, 2) == {"text": "Bom dia. Como passou? Bem, doutora.", "falas": FALAS_T}
    assert db.rec_prev_segment(ana, rid, 1) == {"text": "", "falas": []}
    assert db.rec_prev_segment(beto, rid, 2) == {"text": "", "falas": []}
    (r,) = db.rec_list(ana, p["id"], event_id="ev1")
    assert [s["falas"] for s in r["segments"]] == [FALAS_T, []]
    assert db.rec_set_fala(beto, p["id"], rid, 1, 0, "p") is None                     # outro médico
    assert db.rec_set_fala(ana, outro["id"], rid, 1, 0, "p") is None                  # outro paciente
    assert db.rec_set_fala(ana, p["id"], rid, 1, 2, "p") is None                      # fala que não existe
    assert db.rec_set_fala(ana, p["id"], rid, 2, 0, "p") is None                      # trecho sem rótulo
    assert db.rec_set_fala(ana, p["id"], rid, 3, 0, "p") is None                      # trecho que não existe
    with pytest.raises(ValueError):
        db.rec_set_fala(ana, p["id"], rid, 1, 0, "x")
    assert db.rec_segment(ana, rid, 1)["falas"] == FALAS_T
    novas = db.rec_set_fala(ana, p["id"], rid, 1, 1, "a")
    assert novas == [FALAS_T[0], dict(FALAS_T[1], q="a", manual=True)]
    assert db.rec_segment(ana, rid, 1)["falas"] == novas
    db.rec_add_segment(ana, rid, 1, 0.0, 20.0, "outro texto", [], [])                 # reenvio não sobrescreve
    assert db.rec_segment(ana, rid, 1)["falas"] == novas


def test_falas_migracao_0023_idempotente(novo_usuario):
    sql = open(os.path.join(os.path.dirname(__file__), "..", "supabase", "migrations", "0023_falantes.sql")).read()
    with db.connection() as c:
        c.execute(sql)
        c.execute(sql)
        c.commit()
        col = c.execute("""select data_type, is_nullable, column_default from information_schema.columns
                           where table_schema = 'public' and table_name = 'recording_segments' and column_name = 'falas'""").fetchone()
        rls = c.execute("select relrowsecurity from pg_class where relname = 'recording_segments'").fetchone()[0]
    assert col[0] == "jsonb" and col[1] == "NO" and "'[]'" in col[2] and rls


def test_sem_a_migracao_0023_falas_ficam_de_fora(novo_usuario, monkeypatch):
    """Sem a 0023 (db.tem_falas falso): o trecho entra sem rótulo, tudo volta com falas = [], a troca dá
    MigracaoPendente e nenhuma consulta cita a coluna."""
    uid = novo_usuario()["id"]
    p = db.create_patient(uid, "Paciente Teste")
    rid = str(uuid.uuid4())
    assert db.rec_open(uid, p["id"], rid, "ev1", None, "2026-10-15T10:00:00Z")
    monkeypatch.setattr(db, "tem_falas", lambda conn: False)
    vistos, real = [], db.connection

    class _Grava:
        def __init__(self, c):
            self.c = c

        def execute(self, sql, *a, **k):
            vistos.append(str(sql))
            return self.c.execute(sql, *a, **k)

        def __getattr__(self, nome):
            return getattr(self.c, nome)

    @contextlib.contextmanager
    def grava():
        with real() as c:
            yield _Grava(c)
    monkeypatch.setattr(db, "connection", grava)
    db.rec_add_segment(uid, rid, 1, 0.0, 20.0, "Bom dia. Como passou? Bem, doutora.", [], FALAS_T)
    assert db.rec_segment(uid, rid, 1) == {"text": "Bom dia. Como passou? Bem, doutora.", "duvidas": [], "falas": []}
    assert db.rec_prev_segment(uid, rid, 2)["falas"] == []
    assert db.rec_list(uid, p["id"], event_id="ev1")[0]["segments"][0]["falas"] == []
    with pytest.raises(db.MigracaoPendente):
        db.rec_set_fala(uid, p["id"], rid, 1, 0, "p")
    citam = [q for q in vistos if re.search(r"\bs\.falas\b|duvidas, falas\)", q)]
    assert vistos and not citam, citam
    monkeypatch.setattr(db, "connection", real)
    with db.connection() as c:                                     # com a coluna no banco: entrou vazia (o padrão)
        assert c.execute("select falas from recording_segments where rec_id = %s", (rid,)).fetchone()[0] == []
