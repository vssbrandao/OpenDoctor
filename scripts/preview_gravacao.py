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

from app import auth, config, db, prescricao, scribe, server, stt  # noqa: E402
from tests.fake_gravacao import EPOCA, FakeGravacao  # noqa: E402
from tests.fake_receitas import FakeReceitas  # noqa: E402

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
_PATS0 = {k: dict(v) for k, v in PATS.items()}       # o reset volta o cadastro (a aba Prescrições muda as medicações)
NOTES = {}                                           # id → evolução (em memória)


def _note_out(n):
    return {k: n[k] for k in ("id", "event_id", "event_title", "event_start", "content", "updated_at", "data", "signed_at", "addenda")}


mock = APIRouter()


@mock.post("/prontuario/list")
async def _list(request: Request):
    b = await request.json()
    pid = b.get("patient_id")          # evento só com o nome (sem o paciente ligado): acha pelo nome, como o servidor
    p = PATS.get(pid) or next((x for x in PATS.values() if x["name"] == b.get("patient")), PATS[9001])
    ns = sorted([_note_out(n) for n in NOTES.values() if n["pid"] == p["id"]], key=lambda n: n["updated_at"], reverse=True)
    return {"patient": {k: v for k, v in p.items() if k != "key"}, "notes": ns}


@mock.post("/prontuario/visits")
async def _visits(request: Request):
    return {"connected": True, "visits": []}


@mock.post("/prontuario/access")
async def _access(request: Request):
    return {"access": []}


FILES = {}                                           # id → anexo (o laudo da paciente de exemplo)


@mock.post("/prontuario/files/list")
async def _files(request: Request):
    pid = (await request.json()).get("patient_id")
    return {"files": [{k: f[k] for k in ("id", "name", "mime", "size", "created_at")} for f in FILES.values() if f["pid"] == pid]}


@mock.get("/prontuario/files/{fid}")
def _file(fid: int):
    f = FILES.get(fid)
    if not f:
        return JSONResponse({"error": "anexo não encontrado"}, status_code=404)
    return Response(f["data"], media_type=f["mime"], headers={"Content-Disposition": f'inline; filename="{f["name"]}"'})


@mock.get("/_preview/exemplo")
def _exemplo():
    """Maria Silva (9001) com TODO o histórico da paciente de exemplo de app/exemplo.py: cadastro, 11 consultas
    finalizadas com sinais vitais e CID, os resultados de exames e o laudo em PDF. Só sob pedido (&exemplo=1): o teste
    ponta a ponta continua com ela vazia."""
    from app import exemplo
    now = dt.datetime.now(dt.timezone.utc)
    PATS[9001].update(allergies=exemplo.ALLERGIES, problems=exemplo.PROBLEMS, medications=exemplo.MEDICATIONS)
    for k in [k for k, n in NOTES.items() if n.get("exemplo")]:
        del NOTES[k]
    rows = [(c["title"], c["start"], c["content"], c["data"], c["signed_at"], c["signed_at"]) for c in exemplo.consultas(now)]
    rows += [(None, None, e["content"], e["data"], None, dt.datetime.combine(e["date"], dt.time(18, 0), tzinfo=dt.timezone.utc))
             for e in exemplo.exames(now)]
    for title, start, content, data, signed, upd in rows:
        i = 8000 + len(NOTES)
        NOTES[i] = {"id": i, "pid": 9001, "event_id": None, "event_title": title, "event_start": start and start.isoformat(),
                    "content": content, "updated_at": upd.isoformat(), "data": server._note_data(data),
                    "signed_at": signed and signed.isoformat(), "addenda": [], "exemplo": True}
    RX.rx = {k: r for k, r in RX.rx.items() if r["patient_id"] != 9001}      # as receitas emitidas de cada consulta
    ids = sorted(k for k, n in NOTES.items() if n.get("exemplo") and n["event_title"])
    cs = exemplo.consultas(now)
    RX.add_example_receitas(UID, 9001, [(ids[i], c["signed_at"], exemplo.receita_itens(i)) for i, c in enumerate(cs)])
    recente = min(exemplo.EXAMES)                    # o laudo da coleta mais recente, como na conta nova
    coleta = (exemplo._when(now, recente) - dt.timedelta(days=5)).date()
    pdf = exemplo.laudo_pdf(coleta, exemplo.EXAMES[recente])
    FILES.clear()
    FILES[7001] = {"id": 7001, "pid": 9001, "name": "laudo-exemplo.pdf", "mime": "application/pdf", "size": len(pdf),
                   "created_at": now.isoformat(), "data": pdf}
    return {"ok": True, "notas": len(rows), "anexos": len(FILES)}


@mock.post("/prontuario/notes")
async def _save(request: Request):
    b = await request.json()
    pid, ev, nid = b.get("patient_id"), b.get("event_id") or None, b.get("note_id")
    if ev and db.event_note_other_patient(UID, ev, pid, None):      # como o db.upsert_note: NoteOtherPatient
        return server._outro_paciente()
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
def _pr(pid: int = 9003, tab: str = "atual", ev: str = "", exemplo: int = 0):
    if exemplo:                                      # &exemplo=1: Maria (9001) com o histórico de exemplo inteiro
        _exemplo()
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
      var n=0,ok=0;function tenta(){var b=document.querySelector('#prTabs [data-tab='+t+']');   // até ficar 1 s na aba (o prontuário pode abrir depois)
        if(b&&b.offsetParent){if(b.classList.contains('on')){if(++ok>=4)return;}else{ok=0;b.click();}}if(++n<40)setTimeout(tenta,250);}
      setTimeout(tenta,900);})();"""
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


# ----- banco em memória para a gravação: o mesmo dos testes das rotas (tests/fake_gravacao.py) -----
_LAST = {}                                  # amostras e volume do último trecho transcrito (o teste confere que nada se perde)
GRAV = FakeGravacao(nota_ok=lambda uid, pid, nid: nid in NOTES and NOTES[nid]["pid"] == pid,
                    extra_trecho=lambda: _LAST.pop("x", {}))
GRAV.install(setattr)
db.get_patient = lambda uid, pid: dict(PATS[pid]) if pid in PATS else None
db.recent_notes = lambda uid, limit=30: [{"content": n["content"], "data": n["data"]} for n in NOTES.values()][:limit]
db.list_notes = lambda uid, pid, key: [_note_out(n) for n in NOTES.values() if n["pid"] == pid]
db.last_note_content = lambda uid, pid, nid=None, eid=None: next(
    (n["content"] for n in sorted(NOTES.values(), key=lambda n: n["updated_at"], reverse=True)
     if n["pid"] == pid and n["content"].strip() and n["id"] != nid and (eid is None or n["event_id"] != eid)), "")
db.log_access = lambda *a, **k: None
# a consulta já tem evolução de outro paciente (como db.event_note_other_patient: escrita ou finalizada)
db.event_note_other_patient = lambda uid, eid, pid, key: bool(eid) and any(
    n["event_id"] == eid and n["pid"] != pid and (n["signed_at"] or n["content"]) for n in NOTES.values())
# resumo clínico (Suspender e "Atualizar as medicações em uso" na aba Prescrições): grava no paciente em memória
db.find_by_cpf = lambda uid, cpf, exclude_id=None: None
db.update_patient = lambda uid, pid, fields: (PATS[pid].update({k: v for k, v in fields.items() if k in db._PATIENT_FIELDS}) or dict(PATS[pid])) if pid in PATS else None
# receitas e dados do médico em memória (os mesmos contratos de app/db.py); o médico do preview começa sem CRM, para o
# "Emitir receita" mostrar o caminho de completar os dados em Configurações
RX = FakeReceitas({UID: {"name": "Dra. Teste"}})
RX.install(setattr)
db.get_note = lambda uid, nid: dict(_note_out(NOTES[nid]), patient_id=NOTES[nid]["pid"]) if nid in NOTES else None


def _add_addendum(uid, nid, content):            # adendo em memória (como db.add_addendum: só em evolução finalizada)
    n = NOTES.get(nid)
    if not n or not n["signed_at"]:
        return None
    a = {"id": len(n["addenda"]) + 1, "content": content, "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    n["addenda"].append(a)
    return a


db.add_addendum = _add_addendum

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
    k = len(GRAV.segs) % len(FALAS)
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

# possíveis prescrições (aba Prescrições): busca e modelo simulados com uma resposta real guardada da Maria
# (scripts/preview_prescricao.json). O botão "IA" também faz esta geração falhar.
_PRESC = json.loads(pathlib.Path(__file__).with_name("preview_prescricao.json").read_text(encoding="utf-8"))


def _fake_fontes(p, tfg_=None):
    time.sleep(1.0)
    return [dict(f) for f in _PRESC["fontes"]]


def _fake_presc(msgs, model=None):
    """A resposta real guardada só vale para o perfil da Maria; para as outras pacientes, nenhuma mudança (as conferências
    devolvem o que está em uso como "manter")."""
    time.sleep(2.5)
    if SIM["ia"]:
        raise RuntimeError("IA simulada fora")
    perfil = msgs[1]["content"]
    if "Diabetes tipo 2" in perfil and "Metformina 850 mg" in perfil:
        return json.dumps(_PRESC["resposta"], ensure_ascii=False)
    return json.dumps({"itens": [], "observacoes": "Resposta simulada do preview: só a Maria tem uma resposta real guardada."}, ensure_ascii=False)


prescricao.fontes = _fake_fontes
prescricao.ask_model = _fake_presc


class _Rede(BaseHTTPMiddleware):
    """'Internet caiu' só para as rotas da gravação (o preview roda no próprio computador)."""
    async def dispatch(self, request, call_next):
        EPOCA.set(GRAV.epoca)            # pedido que começou antes de um /_preview/reset não grava nada depois dele
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
def _sim(rede: str = "", ia: str = "", lento: str = "", erro_seq: str = None, recusar_seq: str = None, gravacao: str = ""):
    if rede:
        SIM["rede"] = rede == "off"
    if ia:
        SIM["ia"] = ia == "off"
    if gravacao:                                     # gravação desligada na conta (SCRIBE_OFF): /me devolve scribe falso
        config.SCRIBE_OFF = gravacao == "off"
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
                                "trechos": [{k: s.get(k) for k in ("seq", "at", "dur", "samples")} for (q, _), s in sorted(GRAV.segs.items()) if q == rid]}
                          for rid, r in GRAV.recs.items()},
            "evolucoes": {i: {"pid": n["pid"], "event_id": n["event_id"], "content": n["content"],
                              "scribe": (n["data"] or {}).get("scribe"), "timing": n.get("timing")} for i, n in NOTES.items()}}


@mock.get("/_preview/reset")
def _reset():
    GRAV.reset(); NOTES.clear(); FILES.clear(); RX.reset(); PATS.clear(); PATS.update({k: dict(v) for k, v in _PATS0.items()}); prescricao._CACHE.clear(); server._RL.clear(); SIM.update(rede=False, ia=False, lento=1.2, erro_seq=set(), recusar_seq=set())
    config.SCRIBE_OFF = False
    return {"ok": True}


server.app.router.routes[0:0] = mock.routes
app = server.app
