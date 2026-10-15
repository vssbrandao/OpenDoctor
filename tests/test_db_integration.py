"""Testes contra um banco de verdade — o de TESTES (fixture test_db, ver conftest.py). Sem
TEST_DATABASE_URL eles são pulados; nunca tocam produção. Cada teste cria os próprios usuários e
apaga tudo no fim."""
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
