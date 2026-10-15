"""Paciente de exemplo criada em toda conta nova — dados FICTÍCIOS (nenhuma pessoa real).

Mostra o prontuário preenchido: 11 consultas finalizadas com sinais vitais e CID-10, resultados de exames
e um laudo em PDF anexado. As datas acompanham o dia da criação da conta. Sem CPF e telefone (não usar
números que possam ser de alguém). O médico pode excluí-la a qualquer momento (db.delete_patient).
"""
import datetime as dt

from . import db

NAME = db.EXAMPLE_NAME
ALLERGIES = "Dipirona\nPenicilina"
PROBLEMS = "Hipertensão arterial\nDiabetes tipo 2\nObesidade grau I"
MEDICATIONS = "Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia\nAtorvastatina 20 mg à noite"

_HAS = ("I10", "Hipertensão essencial (primária)")
_DM2 = ("E11", "Diabetes mellitus não-insulino-dependente")
_OBES = ("E66", "Obesidade")
_IVAS = ("J06", "Infecções agudas das vias aéreas superiores")
# (meses atrás, PA s, PA d, FC, peso, glicemia, SpO2, temp, CIDs, título)
CONSULTAS = [
    (23, 158, 98, 84, "96,4", 182, 97, "36,4", [_HAS, _DM2], "Primeira consulta"),
    (21, 152, 96, 82, "95,8", 171, 98, "36,6", [_HAS], "Retorno"),
    (18, 148, 94, 80, "94,9", 160, 97, "36,5", [_HAS, _OBES], "Retorno"),
    (15, 146, 92, 79, "94,1", 152, 98, "36,7", [_DM2], "Retorno"),
    (12, 140, 90, 78, "92,8", 141, 98, "36,5", [_HAS], "Retorno anual"),
    (10, 142, 88, 80, "92,0", 138, 97, "37,9", [_IVAS], "Consulta de urgência"),
    (8, 136, 86, 76, "90,7", 129, 98, "36,6", [_HAS, _DM2], "Retorno"),
    (6, 134, 84, 75, "89,9", 124, 98, "36,4", [_DM2], "Retorno"),
    (4, 130, 84, 74, "88,6", 118, 99, "36,5", [_HAS], "Retorno"),
    (2, 128, 82, 72, "87,9", 112, 98, "36,6", [_HAS, _OBES], "Retorno"),
    (0.5, 132, 84, 76, "87,2", 116, 98, "36,5", [_HAS], "Retorno"),
]
# resultados de laboratório (coleta 5 dias antes da consulta do mesmo mês); RAC e ácido úrico atrasados de propósito
EXAMES = {
    23: {"hba1c": "8,4", "ct": "236", "ldl": "152", "hdl": "41", "tg": "215", "creat": "0,88", "pot": "4,3", "sod": "139",
         "rac": "46", "au": "6,4", "tsh": "2,1", "hb": "13,2", "alt": "52"},
    18: {"hba1c": "7,9", "ct": "210", "ldl": "131", "hdl": "43", "tg": "182", "creat": "0,92", "pot": "4,5", "alt": "45"},
    15: {"rac": "35", "au": "6,2"},
    12: {"hba1c": "7,4", "ct": "196", "ldl": "118", "hdl": "44", "tg": "165", "creat": "0,98", "pot": "4,6", "sod": "140",
         "tsh": "2,4", "hb": "13,0", "alt": "39"},
    6: {"hba1c": "7,1", "ct": "181", "ldl": "104", "hdl": "45", "tg": "150", "creat": "1,02", "pot": "4,7", "alt": "34"},
    0.5: {"hba1c": "6,9", "ct": "172", "ldl": "98", "hdl": "46", "tg": "142", "creat": "1,05", "pot": "4,8", "sod": "140", "alt": "31"},
}
_LABTXT = [("hba1c", "HbA1c", "%"), ("ct", "CT", "mg/dL"), ("ldl", "LDL", "mg/dL"), ("hdl", "HDL", "mg/dL"), ("tg", "TG", "mg/dL"),
           ("creat", "Creatinina", "mg/dL"), ("rac", "RAC", "mg/g"), ("pot", "K", "mEq/L"), ("sod", "Na", "mEq/L"),
           ("au", "Ácido úrico", "mg/dL"), ("tsh", "TSH", "mUI/L"), ("hb", "Hb", "g/dL"), ("alt", "TGP", "U/L")]


def _when(now, months):
    return (now - dt.timedelta(days=int(months * 30.4))).replace(hour=9, minute=30, second=0, microsecond=0)


def _br(d):
    return d.strftime("%d/%m/%Y")


def consultas(now):
    """Evoluções SOAP finalizadas (mesmo formato que a tela grava)."""
    out = []
    for m, s, d, fc, peso, gli, spo, tmp, cid, title in CONSULTAS:
        w = _when(now, m)
        urg = title == "Consulta de urgência"
        S = ("Coriza, odinofagia e febre há 2 dias. Nega dispneia." if urg else
             "Refere boa adesão ao tratamento. Nega dor torácica, dispneia ou edema.")
        P = ("Sintomáticos, hidratação. Retorno se piora." if urg else
             "Mantida a prescrição. Reforçadas orientações de dieta e atividade física. Retorno em 2 meses.")
        vit = {"pa_s": str(s), "pa_d": str(d), "fc": str(fc), "peso": peso, "altura": "162", "glicemia": str(gli),
               "spo2": str(spo), "temp": tmp}
        content = (f"S: {S}\n\nO: Sinais vitais: PA {s}x{d} mmHg · FC {fc} bpm · SpO₂ {spo}% · Temp. {tmp} °C · "
                   f"Peso {peso} kg · Altura 162 cm · Glicemia {gli} mg/dL\n\n"
                   "A: CID-10: " + "; ".join(f"{c} {t}" for c, t in cid) + f"\n\nP: {P}")
        data = {"mode": "soap", "s": S, "o": "", "a": "", "p": P, "vitals": vit, "cid": [{"code": c, "desc": t} for c, t in cid]}
        out.append({"title": title, "start": w, "content": content, "data": data, "signed_at": w + dt.timedelta(minutes=40)})
    return out


def exames(now):
    """Resultados de exames (registros "Resultado de exames", um por coleta)."""
    out = []
    for m, v in EXAMES.items():
        d = (_when(now, m) - dt.timedelta(days=5)).date()
        itens = " · ".join(f"{lbl} {v[k]}" + ("%" if u == "%" else f" {u}") for k, lbl, u in _LABTXT if k in v)
        out.append({"date": d, "content": f"Resultado de exames (coleta {_br(d)}): {itens}",
                    "data": {"mode": "soap", "kind": "labs", "s": "", "o": "", "a": "", "p": "", "vitals": {}, "cid": [],
                             "labs": {"date": d.isoformat(), "v": v}}})
    return out


def laudo_pdf(coleta, v):
    """Laudo FICTÍCIO em PDF (texto simples, fonte Helvetica) — o "Ler valores" consegue ler."""
    linhas = [("LABORATÓRIO DE EXEMPLO — LAUDO FICTÍCIO", 13), (f"Paciente: {NAME}", 10),
              (f"Data da coleta: {_br(coleta)}", 10), ("", 10)]
    exames_txt = [("HEMOGLOBINA GLICADA (HbA1c)", "hba1c", "%", "Normal: inferior a 5,7 %"),
                  ("COLESTEROL TOTAL", "ct", "mg/dL", "Desejável: inferior a 190 mg/dL"),
                  ("COLESTEROL HDL", "hdl", "mg/dL", "Desejável: superior a 50 mg/dL"),
                  ("COLESTEROL LDL", "ldl", "mg/dL", "Ótimo: inferior a 100 mg/dL"),
                  ("TRIGLICERÍDEOS", "tg", "mg/dL", "Desejável: inferior a 150 mg/dL"),
                  ("CREATININA", "creat", "mg/dL", "Referência: 0,50 a 1,10 mg/dL"),
                  ("POTÁSSIO", "pot", "mmol/L", "Referência: 3,5 a 5,1 mmol/L"),
                  ("SÓDIO", "sod", "mmol/L", "Referência: 136 a 145 mmol/L"),
                  ("TGP - ALANINA AMINOTRANSFERASE", "alt", "U/L", "Referência: até 33 U/L")]
    for nome, k, u, ref in exames_txt:
        if k in v:
            linhas += [(nome, 11), (f"Resultado: {v[k]} {u}        {ref}", 10), ("", 6)]
    linhas += [("", 10), ("Documento de exemplo do OpenDoctor. Não corresponde a nenhuma pessoa real.", 8)]

    def esc(t):
        return t.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    y, ops = 790, [b"BT"]
    for t, size in linhas:
        if t:
            ops.append(b"/F1 %d Tf 1 0 0 1 56 %d Tm (" % (size, y) + esc(t) + b") Tj")
        y -= size + 8
    ops.append(b"ET")
    stream = b"\n".join(ops)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Title (Laudo de exemplo - OpenDoctor) /Producer (OpenDoctor) >>"]
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % x for x in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, len(objs), xref)
    return bytes(out)


def seed(user_id, now=None):
    """Cria a paciente de exemplo (se a conta ainda não tem). Devolve o id ou None."""
    if any(p["name"] == NAME for p in db.list_patients(user_id)):
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    p = db.create_patient(user_id, NAME, birth_date="1968-03-14", sex="F")
    db.update_patient(user_id, p["id"], {"allergies": ALLERGIES, "problems": PROBLEMS, "medications": MEDICATIONS})
    rows = [(c["title"], c["start"], c["content"], c["data"], c["signed_at"], c["signed_at"]) for c in consultas(now)]
    rows += [(None, None, e["content"], e["data"], None,
              dt.datetime.combine(e["date"], dt.time(18, 0), tzinfo=dt.timezone.utc)) for e in exames(now)]
    db.add_example_notes(user_id, p["id"], p["key"], NAME, rows)
    recente = min(EXAMES)                             # laudo da coleta mais recente
    coleta = (_when(now, recente) - dt.timedelta(days=5)).date()
    db.add_file(user_id, p["id"], "laudo-exemplo.pdf", "application/pdf", laudo_pdf(coleta, EXAMES[recente]))
    return p["id"]


def seed_safe(user_id):
    """Para o cadastro: nunca derruba a criação da conta."""
    try:
        return seed(user_id)
    except Exception as e:  # noqa: BLE001
        print("[exemplo] não criou a paciente de exemplo:", str(e)[:200], flush=True)
        return None


if __name__ == "__main__":       # python -m app.exemplo > /tmp/laudo.pdf (só para conferir o PDF)
    import sys
    now = dt.datetime.now(dt.timezone.utc)
    sys.stdout.buffer.write(laudo_pdf((_when(now, 0.5) - dt.timedelta(days=5)).date(), EXAMES[0.5]))
