"""Preview LOCAL da gravação da consulta: as rotas de verdade do servidor, com banco em memória e transcritor e
modelo simulados. Só pacientes fictícios; nada toca o banco, a OpenAI nem o Resend.

    .venv/bin/uvicorn scripts.preview_gravacao:app --port 8770
    abrir http://localhost:8770/_preview/pr?pid=9003&tab=atual&ev=evnext

O áudio é capturado, cortado e enviado de verdade; a "transcrição" devolve falas de uma consulta fictícia e o
"modelo" devolve uma evolução pronta, conferida pelas conferências reais (app/scribe.check). O botão "Internet"
(canto inferior esquerdo) faz as rotas da gravação falharem, para testar a fila; "IA" faz a geração falhar.
O teste ponta a ponta (tests/e2e/gravacao.mjs) roda contra este servidor.
"""
import os

os.environ["DATABASE_URL"] = ""        # antes de importar o app: nenhum acesso ao banco, à OpenAI ou ao Resend
os.environ["OPENAI_API_KEY"] = ""
os.environ["RESEND_API_KEY"] = ""

import asyncio  # noqa: E402
import datetime as dt  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import re  # noqa: E402
import struct  # noqa: E402
import time  # noqa: E402
from urllib.parse import quote  # noqa: E402

from fastapi import APIRouter, Request  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse, Response  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

from app import auth, config, db, scribe, server, stt  # noqa: E402

UID = "00000000-0000-0000-0000-000000000000"
auth.current_user = lambda request: {"id": UID, "email": "teste@example.invalid", "name": "Dra. Teste", "sv": 0}
config.SCRIBE_ALL = True
config.OPENAI_API_KEY = "preview-sem-chave"         # só para passar a porta: transcrição e modelo abaixo são simulados
WEB = pathlib.Path(server.WEB_DIR)
NOW = dt.datetime.now().replace(second=0, microsecond=0)

# ----- pacientes e evoluções FICTÍCIOS -----
BASE = {"cpf": None, "phone": None, "sex": "F", "birth_date": "1968-03-14", "allergies": "", "problems": "", "medications": ""}
PATS = {9001: dict(BASE, id=9001, name="Maria Silva", key=" exemplo", example=True, allergies="Dipirona\nPenicilina",
                   problems="Hipertensão arterial\nDiabetes tipo 2", medications="Losartana 50 mg 12/12h\nMetformina 850 mg 2x/dia\nAtorvastatina 20 mg à noite"),
        9003: dict(BASE, id=9003, name="Ana Clara Ribeiro", key="ana clara ribeiro", example=False, birth_date="1990-07-02", problems="Asma",
                   medications="Salbutamol spray SOS"),
        9004: dict(BASE, id=9004, name="Carlos Eduardo Nunes", key="carlos eduardo nunes", example=False, sex="M", birth_date="1955-01-20",
                   allergies="Dipirona", problems="Hipertensão arterial", medications="Losartana 50 mg 12/12h")}
NOTES = {}                                           # id → evolução (em memória)


def _note_out(n):
    return {k: n[k] for k in ("id", "event_id", "event_title", "event_start", "content", "updated_at", "data", "signed_at", "addenda")}


mock = APIRouter()


@mock.post("/prontuario/list")
async def _list(request: Request):
    pid = (await request.json()).get("patient_id")
    p = PATS.get(pid) or PATS[9001]
    ns = sorted([_note_out(n) for n in NOTES.values() if n["pid"] == p["id"]], key=lambda n: n["updated_at"], reverse=True)
    return {"patient": {k: v for k, v in p.items() if k != "key"}, "notes": ns}


@mock.post("/prontuario/visits")
async def _visits(request: Request):
    return {"connected": True, "visits": []}


@mock.post("/prontuario/access")
async def _access(request: Request):
    return {"access": []}


@mock.post("/prontuario/files/list")
async def _files(request: Request):
    return {"files": []}


@mock.post("/prontuario/notes")
async def _save(request: Request):
    b = await request.json()
    pid, ev, nid = b.get("patient_id"), b.get("event_id") or None, b.get("note_id")
    n = next((x for x in NOTES.values() if x["pid"] == pid and ((ev and x["event_id"] == ev) or (nid and x["id"] == nid))), None)
    if n and n["signed_at"]:
        return JSONResponse({"error": "evolução finalizada: use um adendo"}, status_code=409)
    if not n:
        i = 8500 + len(NOTES)
        n = NOTES[i] = {"id": i, "pid": pid, "event_id": ev, "event_title": b.get("event_title") or "Retorno",
                        "event_start": b.get("event_start") or NOW.isoformat(), "signed_at": None, "addenda": []}
    n.update(content=b.get("content") or "", updated_at=dt.datetime.now().isoformat(),
             data=server._note_data(b.get("data")) if b.get("data") is not None else None)
    if n["data"] and n["data"].get("scribe"):
        db.rec_link_note(UID, pid, n["data"]["scribe"]["rec_ids"], n["id"])
    db.rec_link_orphans(UID, pid, server._rec_ids({"rec_ids": b.get("rec_ids")}), n["id"])
    return {"ok": True, "id": n["id"]}


@mock.post("/prontuario/notes/{nid}/finalize")
async def _finalize(nid: int, request: Request):
    at = dt.datetime.now().isoformat()
    if nid in NOTES:
        NOTES[nid]["signed_at"] = at
        NOTES[nid]["timing"] = server._timing((await request.json()).get("timing"))
    return {"ok": True, "signed_at": at}


@mock.get("/patients")
def _patients():
    return {"patients": [dict({k: v for k, v in p.items() if k != "key"}, notes=0, last=None) for p in PATS.values()]}


@mock.get("/calendar/events")
def _events():
    return {"connected": False, "events": []}


# ----- abrir o prontuário de um paciente fictício (script externo: a CSP não roda script inline injetado) -----
@mock.get("/_preview/pr")
def _pr(pid: int = 9003, tab: str = "atual", ev: str = ""):
    return HTMLResponse(f'<!doctype html><script src="/_preview/pr.js?pid={pid}&tab={quote(tab)}&ev={quote(ev)}"></script>')


@mock.get("/_preview/pr.js")
def _pr_js(pid: int = 9003, tab: str = "atual", ev: str = ""):
    c = {"patient_id": pid, "patient": PATS.get(pid, PATS[9001])["name"], "from": "pacientes"}
    if ev:
        c.update(event_id=ev, title="Retorno", start=NOW.isoformat())
    js = (f"sessionStorage.setItem('od_prontuario_ctx', {json.dumps(json.dumps(c))});"
          f"sessionStorage.setItem('od_preview_tab', {json.dumps(re.sub(r'[^a-z]', '', tab))});"
          "location.replace('/opendoctor-agenda.html#prontuario');")
    return Response(js, media_type="application/javascript")


@mock.get("/opendoctor-agenda.html")
def _agenda():
    html = (WEB / "opendoctor-agenda.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("</body>", '<script src="/_preview/tab.js"></script><script src="/_preview/ctl.js"></script></body>'))


@mock.get("/_preview/tab.js")
def _tab_js():
    js = """(function(){var t=null;try{t=sessionStorage.getItem('od_preview_tab')}catch(e){}if(!t)return;
      setTimeout(function(){var b=document.querySelector('#prTabs [data-tab='+t+']');if(b)b.click();},900);})();"""
    return Response(js, media_type="application/javascript")


@mock.get("/_preview/ctl.js")
def _ctl_js():
    js = """(function(){var b=document.createElement('div');
      b.style.cssText='position:fixed;left:16px;bottom:16px;z-index:99;display:flex;gap:8px;align-items:center;padding:8px 12px;border-radius:12px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.2);font:13px/18px system-ui;color:#3C4043';
      b.innerHTML='<b style="font-weight:600">Preview</b><span>transcrição simulada</span>';
      function t(k,lab){var x=document.createElement('button');x.type='button';x.style.cssText='height:28px;padding:0 10px;border-radius:14px;border:1px solid #DADCE0;background:#fff;cursor:pointer;font:inherit';
        function paint(on){x.textContent=lab+(on?': ligada':': caiu');x.style.color=on?'#137333':'#C5221F';x._on=on;}
        x.addEventListener('click',function(){fetch('/_preview/sim?'+k+'='+(x._on?'off':'on')).then(function(r){return r.json()}).then(function(j){paint(j[k]==='on')})});
        fetch('/_preview/sim').then(function(r){return r.json()}).then(function(j){paint(j[k]==='on')});b.appendChild(x);}
      t('rede','Internet');t('ia','IA');document.body.appendChild(b);})();"""
    return Response(js, media_type="application/javascript")


# ----- banco em memória para a gravação (mesmos contratos de app/db.py) -----
REC, SEG, _LAST = {}, {}, {}


def _rec_open(uid, pid, rid, eid=None, nid=None, consent=None):
    if nid is not None and not (nid in NOTES and NOTES[nid]["pid"] == pid):
        nid = None
    r = REC.setdefault(rid, {"uid": uid, "pid": pid, "event_id": eid, "note_id": nid, "consent_at": consent or dt.datetime.now().isoformat(),
                             "status": "gravando", "seconds": 0.0, "scribe": None, "created": time.time(),
                             "updated_at": dt.datetime.now().astimezone().isoformat()})
    if nid is not None and r["note_id"] is None and r["pid"] == pid:
        r["note_id"] = nid
    return r["uid"] == uid and r["pid"] == pid


def _rec_add(uid, rid, seq, at, dur, text, duvidas):
    if rid not in REC:                       # o /_preview/reset limpou no meio de um envio: descarta
        return
    if (rid, seq) not in SEG:
        SEG[(rid, seq)] = dict({"seq": seq, "at": at, "dur": dur, "text": text, "duvidas": list(duvidas)}, **_LAST.pop("x", {}))
    REC[rid].update(seconds=max(REC[rid]["seconds"], at + dur), status="gravando", updated_at=dt.datetime.now().astimezone().isoformat())


def _rec_list(uid, pid, eid=None, nid=None, ids=(), orphans=False):
    out = []
    for rid, r in sorted(REC.items(), key=lambda kv: kv[1]["created"]):
        if r["uid"] == uid and r["pid"] == pid and ((eid and r["event_id"] == eid) or (nid and r["note_id"] == nid) or rid in ids
                                                   or (orphans and not r["event_id"] and not r["note_id"])):
            segs = [{k: s[k] for k in ("seq", "at", "dur", "text", "duvidas")} for (q, _), s in sorted(SEG.items()) if q == rid]
            out.append({"rec_id": rid, "status": r["status"], "consent_at": r["consent_at"], "seconds": r["seconds"],
                        "updated_at": r["updated_at"], "event_id": r["event_id"], "note_id": r["note_id"], "scribe": r["scribe"],
                        "segments": segs})
    return out


def _rec_generated(uid, rids, meta, nid=None):
    for rid in rids:
        if rid in REC:
            REC[rid].update(status="gerada", scribe=meta)
            if REC[rid]["note_id"] is None and nid in NOTES:
                REC[rid]["note_id"] = nid


db.get_patient = lambda uid, pid: dict(PATS[pid]) if pid in PATS else None
db.rec_open = _rec_open
db.rec_segment = lambda uid, rid, seq: ({"text": SEG[(rid, seq)]["text"], "duvidas": SEG[(rid, seq)]["duvidas"]} if (rid, seq) in SEG else None)
db.rec_prev_text = lambda uid, rid, seq: next((s["text"] for (q, n), s in sorted(SEG.items(), reverse=True) if q == rid and n < seq), "")
db.rec_add_segment = _rec_add
db.rec_seconds_today = lambda uid: sum(s["dur"] for s in SEG.values())
db.rec_list = _rec_list
db.rec_generated = _rec_generated
db.rec_link_note = lambda uid, pid, rids, nid: [REC[r].update(note_id=nid) for r in rids if r in REC and REC[r]["pid"] == pid]
db.rec_link_orphans = lambda uid, pid, rids, nid: [REC[r].update(note_id=nid) for r in rids
                                                   if r in REC and REC[r]["pid"] == pid and REC[r]["note_id"] is None]
db.rec_delete = lambda uid, rid: (REC.pop(rid)["pid"] if rid in REC else None)
db.recent_notes = lambda uid, limit=30: [{"content": n["content"], "data": n["data"]} for n in NOTES.values()][:limit]
db.list_notes = lambda uid, pid, key: [_note_out(n) for n in NOTES.values() if n["pid"] == pid]
db.last_note_content = lambda uid, pid, nid=None, eid=None: next(
    (n["content"] for n in sorted(NOTES.values(), key=lambda n: n["updated_at"], reverse=True)
     if n["pid"] == pid and n["content"].strip() and n["id"] != nid and (eid is None or n["event_id"] != eid)), "")
db.log_access = lambda *a, **k: None

# ----- transcritor e modelo simulados: consulta FICTÍCIA -----
SIM = {"rede": False, "ia": False, "lento": 1.2, "erro_seq": set(), "recusar_seq": set()}
FALAS = [("Bom dia. Como passou desde a última consulta? Bem, graças a Deus. Estou tomando os remédios certinho: a losartana, a metformina e o do colesterol. E a caminhada, conseguiu manter?", []),
         ("Quatro vezes por semana, uns trinta minutos. Só que essa semana, duas vezes, eu levantei da cama e fiquei tonta. Essa tontura passa rápido? Chegou a desmaiar, teve falta de ar ou dor no peito?", []),
         ("Passa em menos de um minuto, sentada. Não desmaiei e não tive dor nem falta de ar. E as glicemias em casa, como estão? Em jejum, entre 110 e 130. Não tive nenhuma baixa de açúcar.", ["110"]),
         ("Vou examinar agora. A pressão está 128 por 82, e a frequência, 74. Peso 86 quilos e 800 gramas, glicemia agora de 108. Coração e pulmões sem alterações.", []),
         ("Os pés estão bem: pulsos presentes e a sensibilidade preservada no monofilamento. A hemoglobina glicada veio 6,9: o diabetes está na meta.", ["monofilamento"]),
         ("Vamos manter os três remédios. Levante devagar: sente na cama um minuto antes de ficar em pé. Vou pedir o exame de urina para os rins e o ácido úrico. Retorno em três meses, com os exames.", [])]
FRASES = [("s", "Refere boa adesão aos medicamentos (losartana, metformina e estatina).", [0], "dito"),
          ("s", "Caminhada 4 vezes por semana, cerca de 30 minutos.", [1], "dito"),
          ("s", "Tontura ao levantar da cama em 2 episódios nesta semana, com melhora em menos de 1 minuto sentada.", [1, 2], "dito"),
          ("s", "Nega síncope, dispneia e dor torácica.", [1, 2], "dito"),
          ("s", "Glicemias de jejum em casa entre 110 e 130 mg/dL, sem hipoglicemias.", [2], "dito"),
          ("o", "Ausculta cardíaca e pulmonar sem alterações.", [3], "dito"),
          ("o", "Pés: pulsos presentes e sensibilidade preservada ao monofilamento.", [4], "dito"),
          ("a", "Diabetes tipo 2 na meta (HbA1c 6,9%).", [4], "dito"),
          ("a", "Tontura postural a esclarecer.", [1], "inferido"),
          ("p", "Mantidos losartana, metformina e atorvastatina.", [5], "dito"),
          ("p", "Retorno em 3 meses com os exames.", [5], "dito")]
_KEYS = [t[20:45] for t, _ in FALAS]                # pedaço do meio de cada fala: reconhece o trecho no texto mascarado


async def _fake_stt(audio, mime="audio/wav", prompt="", keywords=None, model=None, confidence=True):
    await asyncio.sleep(SIM["lento"])
    n = (len(audio) - 44) // 2
    pcm = struct.unpack("<%dh" % n, audio[44:44 + 2 * n])
    k = len(SEG) % len(FALAS)
    _LAST["x"] = {"samples": n, "rms": round((sum(x * x for x in pcm[::4]) / max(1, len(pcm[::4]))) ** 0.5 / 32768, 4), "k": k}
    return {"text": FALAS[k][0], "raw": "", "usage": {}, "duvidas": FALAS[k][1], "confianca": 0.9}


def _fake_model(msgs, model=None):
    time.sleep(2.0)
    if SIM["ia"]:
        raise RuntimeError("IA simulada fora")
    by_k = {}
    for m in re.finditer(r"^\[(\d+)\] \(\d+:\d\d\) (.*)$", msgs[1]["content"], re.M):
        k = next((i for i, key in enumerate(_KEYS) if key in m.group(2)), None)
        if k is not None:
            by_k.setdefault(k, []).append(int(m.group(1)))
    src = lambda ks: sorted({q for k in ks for q in by_k.get(k, [])})
    soap = "Escreva a evolução no modo SOAP" in msgs[1]["content"]
    sent = [(f, {"t": t, "src": src(ks), "tipo": tp}) for f, t, ks, tp in FRASES if src(ks)]
    out = {"soap": {f: [x for g, x in sent if g == f] for f in "soap"} if soap else {},
           "livre": [dict(x, par=(i == 0 or sent[i - 1][0] != f)) for i, (f, x) in enumerate(sent)] if not soap else [],
           "vitals": {k: {"v": v, "src": src([3])} for k, v in (("pa_s", "128"), ("pa_d", "82"), ("fc", "74"))} if 3 in by_k else {},
           "cid": [{"code": "E11", "src": src([4])}] if 4 in by_k else [],
           "meds": [{"nome": n, "dose": d, "posologia": q, "acao": "mantido", "src": src([5])} for n, d, q in
                    (("losartana", "50 mg", "12/12h"), ("metformina", "850 mg", "2x/dia"))] if 5 in by_k else [],
           "exames": [], "pendencias": ["confirmar a glicemia de jejum ouvida com dúvida: 110 mg/dL"] if 2 in by_k else []}
    return json.dumps(out, ensure_ascii=False)


stt.atranscribe = _fake_stt
scribe.ask_model = _fake_model


class _Rede(BaseHTTPMiddleware):
    """'Internet caiu' só para as rotas da gravação (o preview roda no próprio computador)."""
    async def dispatch(self, request, call_next):
        if SIM["rede"] and request.url.path.startswith(("/prontuario/transcribe", "/prontuario/recordings", "/prontuario/scribe")):
            return JSONResponse({"error": "internet simulada fora"}, status_code=503)
        if request.url.path == "/prontuario/transcribe":            # para o teste: um trecho que o servidor sempre erra / recusa
            seq = str(request.headers.get("x-seq") or "")
            if seq in SIM["erro_seq"]:
                return JSONResponse({"error": "falha simulada do servidor"}, status_code=500)
            if seq in SIM["recusar_seq"]:
                return JSONResponse({"error": "trecho recusado (simulado)"}, status_code=400)
        return await call_next(request)


server.app.add_middleware(_Rede)


@mock.get("/_preview/sim")
def _sim(rede: str = "", ia: str = "", lento: str = "", erro_seq: str = None, recusar_seq: str = None):
    if rede:
        SIM["rede"] = rede == "off"
    if ia:
        SIM["ia"] = ia == "off"
    if lento:
        SIM["lento"] = float(lento)
    if erro_seq is not None:
        SIM["erro_seq"] = {x for x in erro_seq.split(",") if x}
    if recusar_seq is not None:
        SIM["recusar_seq"] = {x for x in recusar_seq.split(",") if x}
    return {"rede": "off" if SIM["rede"] else "on", "ia": "off" if SIM["ia"] else "on", "lento": SIM["lento"],
            "erro_seq": sorted(SIM["erro_seq"]), "recusar_seq": sorted(SIM["recusar_seq"])}


@mock.get("/_preview/estado")
def _estado():
    """Para o teste: gravações (com paciente, consulta e trechos) e evoluções salvas."""
    return {"gravacoes": {rid: {"pid": r["pid"], "event_id": r["event_id"], "note_id": r["note_id"], "status": r["status"],
                                "trechos": [{k: s.get(k) for k in ("seq", "at", "dur", "samples")} for (q, _), s in sorted(SEG.items()) if q == rid]}
                          for rid, r in REC.items()},
            "evolucoes": {i: {"pid": n["pid"], "event_id": n["event_id"], "content": n["content"],
                              "scribe": (n["data"] or {}).get("scribe"), "timing": n.get("timing")} for i, n in NOTES.items()}}


@mock.get("/_preview/reset")
def _reset():
    REC.clear(); SEG.clear(); NOTES.clear(); SIM.update(rede=False, ia=False, lento=1.2, erro_seq=set(), recusar_seq=set())
    return {"ok": True}


server.app.router.routes[0:0] = mock.routes
app = server.app
