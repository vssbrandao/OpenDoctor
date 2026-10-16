"""Banco da gravação em memória, com os MESMOS contratos de app/db.py (rec_*). Uma cópia só, usada pelos testes das
rotas (tests/test_scribe_routes.py) e pelo preview local (scripts/preview_gravacao.py): mudou uma regra no db.py,
muda aqui. Nada toca banco de verdade.

A regra de ligar gravação e evolução é a do db._ligar: só evolução deste médico e paciente (nota_ok); sem trocar,
só a gravação que ainda não tem evolução ganha esta; trocar=True é a evolução que a gravação gerou.

Limpeza no meio de um envio (preview): cada pedido carrega a "época" em que começou (EPOCA, posta por um middleware);
escrita de uma época anterior à última limpeza é descartada — um trecho atrasado não ressuscita a gravação.
"""
import contextvars
import datetime as dt
import time

EPOCA = contextvars.ContextVar("epoca_gravacao", default=None)
NOMES = ("rec_open", "rec_segment", "rec_prev_text", "rec_add_segment", "rec_seconds_today", "rec_list", "rec_generated",
         "rec_link_note", "rec_link_orphans", "rec_delete")


class FakeGravacao:
    def __init__(self, nota_ok=lambda uid, pid, nid: True, extra_trecho=dict):
        self.nota_ok = nota_ok                # a evolução é deste médico e paciente?
        self.extra_trecho = extra_trecho      # campos a mais no trecho guardado (o preview guarda amostras e volume)
        self.recs, self.segs, self.epoca = {}, {}, 0

    def install(self, setattr_):
        """setattr_(db, nome, função): monkeypatch.setattr nos testes, setattr no preview."""
        from app import db
        for nome in NOMES:
            setattr_(db, nome, getattr(self, nome))

    def reset(self):
        self.recs.clear(); self.segs.clear(); self.epoca += 1

    def _vale(self):
        e = EPOCA.get()
        return e is None or e == self.epoca

    def _agora(self):
        return dt.datetime.now().astimezone().isoformat()

    def _ligar(self, uid, pid, rids, nid, trocar=False):
        if nid is None or not self.nota_ok(uid, pid, nid):
            return
        for rid in [str(x) for x in rids or ()][:20]:
            r = self.recs.get(rid)
            if r and r["uid"] == uid and r["pid"] == pid and (trocar or r["note_id"] is None):
                r["note_id"] = nid

    # ----- os contratos de app/db.py -----
    def rec_open(self, uid, pid, rid, eid=None, nid=None, consent=None):
        if not self._vale():
            return False
        r = self.recs.setdefault(rid, {"uid": uid, "pid": pid, "event_id": eid, "note_id": None, "consent_at": consent or self._agora(),
                                       "status": "gravando", "seconds": 0, "scribe": None, "created": time.time(),
                                       "updated_at": self._agora()})
        self._ligar(uid, pid, [rid], nid)
        return r["uid"] == uid and r["pid"] == pid

    def rec_segment(self, uid, rid, seq):
        s, r = self.segs.get((rid, seq)), self.recs.get(rid)
        return {"text": s["text"], "duvidas": s["duvidas"]} if s and r and r["uid"] == uid else None

    def rec_prev_text(self, uid, rid, seq):
        prev = [s for (q, n), s in sorted(self.segs.items()) if q == rid and n < seq]
        return prev[-1]["text"] if prev else ""

    def rec_add_segment(self, uid, rid, seq, at, dur, text, duvidas):
        r = self.recs.get(rid)
        if not self._vale() or not r or r["uid"] != uid:
            return
        if (rid, seq) not in self.segs:
            self.segs[(rid, seq)] = dict({"seq": seq, "at": at, "dur": dur, "text": text, "duvidas": list(duvidas)}, **self.extra_trecho())
        r.update(seconds=max(r["seconds"], at + dur), status="gravando", updated_at=self._agora())

    def rec_seconds_today(self, uid):
        return sum(s["dur"] for (q, _), s in self.segs.items() if self.recs.get(q, {}).get("uid") == uid)

    def rec_list(self, uid, pid, eid=None, nid=None, ids=(), orphans=False):
        out, limite = [], time.time() - 12 * 3600
        for rid, r in sorted(self.recs.items(), key=lambda kv: kv[1].get("created", 0)):
            orfa = orphans and not r["event_id"] and not r["note_id"] and r.get("created", time.time()) > limite
            if r["uid"] == uid and r["pid"] == pid and ((eid and r["event_id"] == eid) or (nid and r["note_id"] == nid)
                                                       or rid in ids or orfa):
                segs = [{k: s[k] for k in ("seq", "at", "dur", "text", "duvidas")} for (q, _), s in sorted(self.segs.items()) if q == rid]
                out.append({"rec_id": rid, "status": r["status"], "consent_at": r["consent_at"], "seconds": r["seconds"],
                            "updated_at": r.get("updated_at") or self._agora(), "event_id": r["event_id"], "note_id": r["note_id"],
                            "scribe": r.get("scribe"), "segments": segs})
        return out

    def rec_generated(self, uid, pid, rids, meta, nid=None):
        if not self._vale():
            return
        for rid in rids:
            r = self.recs.get(rid)
            if r and r["uid"] == uid and r["pid"] == pid:
                r.update(status="gerada", scribe=meta, updated_at=self._agora())
        self._ligar(uid, pid, rids, nid)

    def rec_link_note(self, uid, pid, rids, nid):
        if self._vale():
            self._ligar(uid, pid, rids, nid, trocar=True)

    def rec_link_orphans(self, uid, pid, rids, nid):
        if self._vale():
            self._ligar(uid, pid, rids, nid)

    def rec_delete(self, uid, rid):
        r = self.recs.get(rid)
        if not r or r["uid"] != uid:
            return None
        self.recs.pop(rid)
        for k in [k for k in self.segs if k[0] == rid]:
            self.segs.pop(k)
        return r["pid"]
