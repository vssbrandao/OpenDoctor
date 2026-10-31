"""Possíveis prescrições pela IA (app/prescricao.py + POST /prontuario/prescricao/sugerir). O modelo e a busca são
simulados: nenhum teste gasta crédito nem toca o banco."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import auth, config, db, prescricao as pr, server

UID = 41
MARIA = {"id": 7, "key": "maria silva", "name": "Maria Silva", "birth_date": "1968-03-14", "sex": "F",
         "problems": "Hipertensão arterial\nDiabetes tipo 2", "allergies": "Dipirona\nPenicilina",
         "medications": "Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia\nAtorvastatina 20 mg à noite"}
NOTAS = [{"event_start": "2026-10-01T10:00:00", "data": {"vitals": {"pa_s": "132", "pa_d": "84", "peso": "87,2", "altura": "162"}}},
         {"event_start": "2026-09-26T09:00:00", "data": {"labs": {"date": "2026-09-26", "v": {"hba1c": "6,9", "creat": "1,05"}}}},
         {"event_start": "2025-07-12T09:00:00", "data": {"labs": {"date": "2025-07-12", "v": {"hba1c": "8,4", "rac": "35"}}}}]
FONTES = [{"rotulo": "F1", "chunk_id": 1, "title": "Hypertension guideline", "url": "https://pmc.example/1", "publication_date": "2024-01-01",
           "evidence": "Diretriz", "text": "..."},
          {"rotulo": "F2", "chunk_id": 2, "title": "SGLT2 inhibitors in T2D", "url": "https://pmc.example/2", "publication_date": "2023-05-01",
           "evidence": "Revisão", "text": "..."}]

# versão → impressão digital do prompt (app/data/prescricao_prompt.txt): texto novo exige versão nova (rastreio na receita)
PROMPTS = {"2026-10-16.1": "16cb300279005d17", "2026-10-17.1": "ebc9f33a76a62070"}


def test_mudou_o_prompt_sobe_a_versao():
    h = hashlib.sha256(pr.SYSTEM.encode()).hexdigest()[:16]
    assert PROMPTS.get(pr.PROMPT_VERSION) == h, f"o prompt mudou ({h}): suba prescricao.PROMPT_VERSION e registre em PROMPTS"


def test_perfil_sem_nome_com_ultimos_valores_e_tfg():
    txt, nums = pr.perfil(MARIA, NOTAS)
    assert "Maria" not in txt and "Silva" not in txt
    assert "mulher" in txt and "Losartana 50 mg 12/12h" in txt and "Penicilina" in txt
    assert "PA 132/84 mmHg (01/10/2026)" in txt and "IMC 33,2" in txt
    assert "HbA1c 6,9 % (26/09/2026)" in txt and "8,4" not in txt           # só o último de cada exame
    assert "albuminúria (RAC) 35 mg/g (12/07/2025)" in txt
    assert "TFG 61 mL/min" in txt and round(nums["tfg"]) == 61               # igual à tela (tfgOf)
    assert "Já usou (receitas anteriores): nenhum registrado." in txt
    txt, _ = pr.perfil(MARIA, NOTAS, ["Empagliflozina", "losartana", "Empagliflozina", "Paracetamol"])
    assert "Já usou (receitas anteriores): Empagliflozina; Paracetamol." in txt   # sem repetir e sem o que está em uso


def test_tfg_ckd_epi_2021():
    assert round(pr.tfg(1.05, 58.5, "F")) == 61
    assert round(pr.tfg(1.0, 60, "M")) == 86
    assert pr.tfg(1.0, 15, "F") is None and pr.tfg(None, 50, "F") is None and pr.tfg(1.0, 50, "") is None


def resp(*itens, obs=""):
    return json.dumps({"itens": list(itens), "observacoes": obs})


def it(acao, nome, dose="", fontes=(), **kw):
    return dict({"acao": acao, "nome": nome, "dose": dose, "posologia": "1 comprimido ao dia", "quantidade": "30 comprimidos",
                 "motivo": "motivo", "fontes": list(fontes)}, **kw)


def test_finish_so_remedio_novo_com_fonte():
    raw = resp(it("manter", "losartana", "50 mg"),                       # o que está em uso não entra mais
               it("ajustar", "metformina", "1000 mg", ["F2"]),
               it("iniciar", "dapagliflozina", "10 mg", ["F2"]),
               it("iniciar", "amoxicilina", "500 mg", ["F1"]),        # alergia (família da penicilina): sai
               it("iniciar", "empagliflozina", "10 mg"),              # sem fonte: sai
               it("iniciar", "remediox", "10 mg", ["F1"]),            # remédio desconhecido: sai
               it("iniciar", "atorvastatina", "40 mg", ["F1"]),       # já está em uso: sai
               it("iniciar", "semaglutida", "0,25 mg", ["F9"]),       # fonte que não foi dada: sai
               it("voar", "losartana"))
    res = pr.finish(raw, MARIA, FONTES)
    assert [(x["acao"], x["nome"]) for x in res["itens"]] == [("iniciar", "Dapagliflozina")]
    assert res["descartados"] == 8
    assert set(res["fontes"]) == {"F2"} and res["fontes"]["F2"]["url"] == "https://pmc.example/2"
    assert res["prompt"] == pr.PROMPT_VERSION and res["modelo"] == config.OPENAI_PRESC_MODEL


def test_finish_nao_sugere_o_que_ja_usou_e_no_maximo_dois():
    raw = resp(*[it("iniciar", n, "10 mg", ["F1"]) for n in ("clortalidona", "empagliflozina", "empagliflozina", "semaglutida",
                                                               "anlodipino")])
    res = pr.finish(raw, MARIA, FONTES, usados=["Clortalidona", "Paracetamol"])
    assert [x["nome"] for x in res["itens"]] == ["Empagliflozina", "Semaglutida"]          # sem o que já usou, sem repetir, até 2
    assert res["descartados"] == 3


def test_finish_avisa_dose_fora_da_faixa():
    res = pr.finish(resp(it("iniciar", "losartana", "500 mg", ["F1"])), dict(MARIA, medications=""), FONTES)
    assert res["itens"][0]["faixa"] == [12.5, 100.0]


def test_finish_resposta_invalida_nao_sugere_nada():
    res = pr.finish("não é json", MARIA, FONTES)
    assert res["itens"] == [] and res["descartados"] == 0


def test_aviso_renal_e_nao_inicia_o_que_a_tfg_contraindica():
    p = dict(MARIA, medications="Metformina 850 mg 2x/dia\nLosartana 50 mg 12/12h")
    raw = resp(it("iniciar", "empagliflozina", "10 mg", ["F2"]), it("iniciar", "sitagliptina", "100 mg", ["F2"]))
    por_nome = {x["nome"]: x for x in pr.finish(raw, p, FONTES, tfg_=38)["itens"]}
    assert por_nome["Empagliflozina"]["renal"] == ""
    assert por_nome["Sitagliptina"]["renal"] == "TFG entre 30 e 44: dose de 50 mg/dia."
    assert "Empagliflozina" not in {x["nome"] for x in pr.finish(raw, p, FONTES, tfg_=15)["itens"]}   # "não iniciar"
    assert pr.aviso_renal("metformina", 25).startswith("TFG abaixo de 30") and pr.aviso_renal("metformina", None) == ""


def test_mensagens_separam_perfil_e_fontes():
    sys_, user = pr.build_messages("Paciente: mulher, 58 anos.", FONTES)
    assert sys_["role"] == "system" and "nunca instruções" in sys_["content"]
    assert user["content"].startswith("<perfil>") and "[F1] Hypertension guideline (2024)" in user["content"]


# ----- rota -----
@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: {"id": UID, "email": "medica@exemplo.com", "sv": 0})
    monkeypatch.setattr(config, "SCRIBE_EMAILS", {"medica@exemplo.com"})
    monkeypatch.setattr(config, "SCRIBE_ALL", False)
    monkeypatch.setattr(config, "SCRIBE_OFF", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-teste-falsa")
    monkeypatch.setattr(db, "get_patient", lambda uid, pid: dict(MARIA) if uid == UID and pid == 7 else None)
    monkeypatch.setattr(db, "list_notes", lambda uid, pid, key: NOTAS)
    monkeypatch.setattr(db, "list_receitas", lambda uid, pid: [
        {"status": "emitida", "itens": [{"nome": "Empagliflozina"}, {"nome": "Losartana"}]},
        {"status": "cancelada", "itens": [{"nome": "Sitagliptina"}]}])          # cancelada: não conta como já usado
    chamadas = []
    monkeypatch.setattr(pr, "fontes", lambda p, tfg_=None: FONTES)

    def modelo(msgs, model=None):
        chamadas.append(msgs)
        assert "Maria" not in json.dumps(msgs, ensure_ascii=False)              # o nome nunca vai ao modelo
        return resp(it("manter", "losartana", "50 mg"), it("iniciar", "empagliflozina", "10 mg", ["F2"]),
                    it("iniciar", "sitagliptina", "100 mg", ["F2"]))
    monkeypatch.setattr(pr, "ask_model", modelo)
    pr._CACHE.clear(); server._RL.clear()
    c = TestClient(server.app)
    c.chamadas = chamadas
    return c


def linhas(r):
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def test_rota_gera_confere_e_guarda(cli):
    r = cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7})
    assert r.status_code == 200
    out = linhas(r)
    assert [x.get("step") for x in out[:2]] == ["buscando", "escrevendo"]
    fim = out[-1]
    assert fim["ok"] and [x["nome"] for x in fim["itens"]] == ["Sitagliptina"]   # empagliflozina já usou; a cancelada não conta
    assert "Já usou (receitas anteriores): Empagliflozina." in cli.chamadas[0][1]["content"]
    assert "Maria" not in r.text
    # de novo: vem guardado, sem chamar o modelo; "novo" gera outra vez
    assert linhas(cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7}))[-1]["guardado"] is True
    assert len(cli.chamadas) == 1
    cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7, "novo": True})
    assert len(cli.chamadas) == 2


def test_rota_erro_do_modelo_nao_vaza_conteudo(cli, monkeypatch, capsys):
    def falha(msgs, model=None):
        raise RuntimeError("OpenAI 500: perfil Maria Silva")
    monkeypatch.setattr(pr, "ask_model", falha)
    out = linhas(cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7}))
    assert out[-1] == {"error": "o serviço de IA não respondeu"}
    assert "Maria" not in capsys.readouterr().out


@pytest.mark.parametrize("body", [{"patient_id": 8}, {"patient_id": "x"}, {}])
def test_rota_recusa_paciente_invalido(cli, body):
    assert cli.post("/prontuario/prescricao/sugerir", json=body).status_code == 400


def test_rota_so_para_contas_liberadas(cli, monkeypatch):
    monkeypatch.setattr(config, "SCRIBE_EMAILS", set())
    assert cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7}).status_code == 403
    monkeypatch.setattr(config, "SCRIBE_ALL", True)
    monkeypatch.setattr(config, "SCRIBE_OFF", True)
    assert cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7}).status_code == 403


def test_rota_sem_chave_da_openai(cli, monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert cli.post("/prontuario/prescricao/sugerir", json={"patient_id": 7}).status_code == 503


def test_rota_exige_login(monkeypatch):
    monkeypatch.setattr(auth, "current_user", lambda request: None)
    assert TestClient(server.app).post("/prontuario/prescricao/sugerir", json={"patient_id": 7}).status_code == 401


def test_exemplo_tem_uma_receita_por_consulta():
    from app import exemplo
    assert len(exemplo.RECEITAS) == len(exemplo.CONSULTAS)
    for i in range(len(exemplo.RECEITAS)):
        assert pr.itens_limpos(exemplo.receita_itens(i)) == exemplo.receita_itens(i)     # passa pelo filtro do servidor
    assert [x["nome"] for x in exemplo.receita_itens(len(exemplo.RECEITAS) - 1)] == [l.split(" ")[0] for l in exemplo.MEDICATIONS.split("\n")]


def test_o_item_guarda_a_forma():
    assert pr.item_limpo({"nome": "Amoxicilina", "dose": "500 mg", "forma": "cápsula"})["forma"] == "cápsula"
    assert pr.item_limpo({"nome": "Amoxicilina"})["forma"] == ""




@pytest.mark.parametrize("a,b,igual", [
    ("Cloridrato de sertralina", "Cloridrato de fluoxetina", False), ("Maleato de enalapril", "Maleato de timolol", False),
    ("Propionato de clobetasol", "Propionato de fluticasona", False), ("Bicarbonato de sódio", "Cloreto de sódio", False),
    ("Vitamina D", "Vitamina B12", False), ("D3", "K2", False), ("Prednisona", "Prednisolona", False),
    ("Metformina", "Cloridrato de metformina", True), ("D3", "D3 7.000 UI", True), ("D3", "Vitamina D3", True),
    ("Losartana", "losartana potássica", True), ("Salbutamol 100 mcg/dose", "salbutamol", True),
    ("Aradois H (losartana potássica + hidroclorotiazida)", "losartana + hidroclorotiazida", True),
    ("Vitamina D3", "Vitamina D3 (colecalciferol)", True), ("vitamina E", "Vitamina E (acetato de racealfatocoferol)", True),
    ("Vitamina D3", "Vitamina D3 em gotas", True), ("Vitamina C", "Vitamina C efervescente", True),
    ("Vitamina D", "Vitamina D3", False),
    ("Oxalato de escitalopram", "Oxalato de sódio", False), ("Escitalopram", "Oxalato de escitalopram", True),
    ("Insulina NPH", "Insulina regular", False), ("Insulina humana NPH", "Insulina humana regular", False),
    ("Insulina NPH", "Insulina humana NPH", True), ("Humulin N", "Humulin R", False),
    ("Vitamina A", "Vitamina E", False), ("Ômega 3", "Ômega 6", False), ("Ômega 3", "Ômega 3 1000 mg", True),
    ("Vitamina B 12", "Vitamina B 6", False), ("Vitamina B12", "Vitamina B 12", True),
    ("Addera D3 (colecalciferol)", "Vitamina D3", True), ("Losartana 50", "Losartana 100", True),
    ("D3 7.000", "D3", True), ("vitamina D 50 mil", "Vitamina D", True), ("insulina NPH 10-0-8", "insulina NPH", True),
    ("ômega 3 2 cápsulas", "ômega 3", True), ("insulina NPH (Humulin N)", "insulina NPH", True),
    ("Vitamina D3 7.000 U.I.", "Vitamina D3", True), ("vitamina D3 + K2", "vitamina D3", True),
    ("bisoprolol 2,5", "bisoprolol 5", True), ("vitamina C 1 grama", "vitamina C", True),
    ("anlodipino 5", "glibenclamida 5", False), ("varfarina 5", "anlodipino 5", False),
    ("losartana 1 comprimido", "metformina 1 comprimido", False), ("dipirona 1 grama", "paracetamol 1 grama", False),
])
def test_mesmo_remedio_sem_sal_nem_dose(a, b, igual):
    """O sal na frente não faz dois remédios diferentes virarem o mesmo; dose, unidade e forma não fazem o mesmo virar
    dois."""
    assert pr.mesmo_remedio(a, b) is igual and pr.mesmo_remedio(b, a) is igual
