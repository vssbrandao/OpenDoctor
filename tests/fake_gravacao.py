"""Banco da gravação em memória, com os MESMOS contratos de app/db.py (rec_*). Uma cópia só, usada pelos testes das
rotas (tests/test_scribe_routes.py) e pelo preview local (scripts/preview_gravacao.py): mudou uma regra no db.py,
muda aqui. Nada toca banco de verdade.

A regra de ligar gravação e evolução é a do db._ligar: só evolução deste médico e paciente (nota_ok); sem trocar,
só a gravação que ainda não tem evolução ganha esta; trocar=True é a evolução que a gravação gerou.

Limpeza no meio de um envio (preview): cada pedido carrega a "época" em que começou (EPOCA, posta por um middleware);
escrita de uma época anterior à última limpeza é descartada — um trecho atrasado não ressuscita a gravação.

O áudio guardado (migração 0022, db.rec_add_audio / rec_audio) fica em `audio`, por (rec_id, part, n); sem_migracao=True
faz de conta que a 0022 não foi aplicada (como db.tem_audio falso).

Quem fala em cada fala (migração 0023, docs/falante-contrato.md): cada trecho guarda `falas`; db.rec_set_fala troca o
rótulo de uma fala à mão; sem_falas=True faz de conta que a 0023 não foi aplicada (como db.tem_falas falso).

Gravação sem paciente (migração 0024, tela Nova consulta): pid None + sem_paciente True; com a semântica do SQL — um
pid None NUNCA casa numa consulta por paciente (patient_id = NULL é falso), só nos caminhos sem paciente (rec_open com
None, rec_add_audio com None, rec_list(sem_paciente=True), rec_pendentes, rec_set_patient). sem_0024=True faz de conta
que a 0024 não foi aplicada (como db.tem_sem_paciente falso: MigracaoPendente). paciente_ok(uid, pid): o paciente é
deste médico? (o db confere na tabela patients, na mesma transação do rec_set_patient).
"""
import contextvars
import datetime as dt
import time

EPOCA = contextvars.ContextVar("epoca_gravacao", default=None)
NOMES = ("rec_open", "rec_segment", "rec_prev_text", "rec_add_segment", "rec_seconds_today", "rec_list", "rec_generated",
         "rec_link_note", "rec_link_orphans", "rec_delete", "rec_add_audio", "rec_audio", "rec_prev_segment", "rec_set_fala",
         "rec_info", "sem_paciente_pronto", "rec_pendentes", "rec_set_patient")


class FakeGravacao:
    def __init__(self, nota_ok=lambda uid, pid, nid: True, extra_trecho=dict, paciente_ok=lambda uid, pid: True):
        self.nota_ok = nota_ok                # a evolução é deste médico e paciente?
        self.paciente_ok = paciente_ok        # o paciente é deste médico?
        self.extra_trecho = extra_trecho      # campos a mais no trecho guardado (o preview guarda amostras e volume)
        self.recs, self.segs, self.audio, self.epoca = {}, {}, {}, 0
        self.sem_migracao = False             # como db.tem_audio falso: a 0022 ainda não foi aplicada
        self.sem_falas = False                # como db.tem_falas falso: a 0023 ainda não foi aplicada
        self.sem_0024 = False                 # como db.tem_sem_paciente falso: a 0024 ainda não foi aplicada

    def install(self, setattr_):
        """setattr_(db, nome, função): monkeypatch.setattr nos testes, setattr no preview."""
        from app import db
        for nome in NOMES:
            setattr_(db, nome, getattr(self, nome))

    def reset(self):
        self.recs.clear(); self.segs.clear(); self.audio.clear(); self.epoca += 1

    def _vale(self):
        e = EPOCA.get()
        return e is None or e == self.epoca

    def _agora(self):
        return dt.datetime.now().astimezone().isoformat()

    @staticmethod
    def _do_paciente(r, pid):
        """patient_id = %s do SQL: None nunca casa."""
        return pid is not None and r["pid"] == pid

    def _sem_0024(self):
        from app import db
        if self.sem_0024:
            raise db.MigracaoPendente("0024_gravacao_sem_paciente.sql")

    def _ligar(self, uid, pid, rids, nid, trocar=False):
        if nid is None or pid is None or not self.nota_ok(uid, pid, nid):
            return
        for rid in [str(x) for x in rids or ()][:20]:
            r = self.recs.get(rid)
            if r and r["uid"] == uid and self._do_paciente(r, pid) and (trocar or r["note_id"] is None):
                r["note_id"] = nid

    # ----- os contratos de app/db.py -----
    def rec_open(self, uid, pid, rid, eid=None, nid=None, consent=None):
        if pid is None:
            self._sem_0024()
        if not self._vale():
            return False
        r = self.recs.setdefault(rid, {"uid": uid, "pid": pid, "event_id": eid if pid is not None else None, "note_id": None,
                                       "consent_at": consent or self._agora(), "status": "gravando", "seconds": 0,
                                       "scribe": None, "created": time.time(), "created_at": self._agora(),
                                       "updated_at": self._agora(), "sem_paciente": pid is None})
        info = {"patient_id": r["pid"], "sem_paciente": bool(r.get("sem_paciente")) and not self.sem_0024}
        if pid is None:                                    # sem paciente: vale a que começou sem ele (sem ou já ligada)
            return info if r["uid"] == uid and (r["pid"] is None or bool(r.get("sem_paciente"))) else False
        self._ligar(uid, pid, [rid], nid)
        return info if r["uid"] == uid and self._do_paciente(r, pid) else False

    def sem_paciente_pronto(self):
        return not self.sem_0024

    def rec_info(self, uid, rid):
        r = self.recs.get(rid)
        if not r or r["uid"] != uid:
            return None
        return {"patient_id": r["pid"], "sem_paciente": bool(r.get("sem_paciente")) and not self.sem_0024}

    def rec_pendentes(self, uid, limit=100):
        self._sem_0024()
        rs = sorted(((rid, r) for rid, r in self.recs.items() if r["uid"] == uid and r["pid"] is None),
                    key=lambda kv: kv[1].get("created", 0), reverse=True)[:limit]
        return [{"rec_id": rid, "created_at": r.get("created_at") or self._agora(), "updated_at": r.get("updated_at") or self._agora(),
                 "seconds": r["seconds"]} for rid, r in rs]

    def rec_set_patient(self, uid, rids, pid):
        """Como db.rec_set_patient: tudo ou nada; só de nenhum paciente para este (refazer com o mesmo vale)."""
        self._sem_0024()
        ids = sorted({str(x) for x in rids or ()})[:20]
        if not self.paciente_ok(uid, pid):
            return "paciente", 0
        rs = [self.recs.get(rid) for rid in ids]
        if not self._vale() or not ids or not all(r and r["uid"] == uid and r.get("sem_paciente") and r["pid"] in (None, pid) for r in rs):
            return "conflito", 0
        for r in rs:
            if r["pid"] is None:
                r.update(pid=pid, updated_at=self._agora())
        return "ok", len(ids)

    def rec_segment(self, uid, rid, seq):
        s, r = self.segs.get((rid, seq)), self.recs.get(rid)
        return {"text": s["text"], "duvidas": s["duvidas"], "falas": self._falas(s)} if s and r and r["uid"] == uid else None

    def _falas(self, s):
        return [] if self.sem_falas else [dict(f) for f in s.get("falas") or []]

    def rec_prev_text(self, uid, rid, seq):
        prev = [s for (q, n), s in sorted(self.segs.items()) if q == rid and n < seq]
        return prev[-1]["text"] if prev else ""

    def rec_prev_segment(self, uid, rid, seq):
        r = self.recs.get(rid)
        prev = [s for (q, n), s in sorted(self.segs.items()) if q == rid and n < seq] if r and r["uid"] == uid else []
        return {"text": prev[-1]["text"], "falas": self._falas(prev[-1])} if prev else {"text": "", "falas": []}

    def rec_add_segment(self, uid, rid, seq, at, dur, text, duvidas, falas=()):
        r = self.recs.get(rid)
        if not self._vale() or not r or r["uid"] != uid:
            return False
        novo = (rid, seq) not in self.segs
        if novo:
            self.segs[(rid, seq)] = dict({"seq": seq, "at": at, "dur": dur, "text": text, "duvidas": list(duvidas),
                                          "falas": [] if self.sem_falas else [dict(f) for f in falas or ()]}, **self.extra_trecho())
        r.update(seconds=max(r["seconds"], at + dur), status="gravando", updated_at=self._agora())
        return novo

    def rec_seconds_today(self, uid):
        return sum(s["dur"] for (q, _), s in self.segs.items() if self.recs.get(q, {}).get("uid") == uid)

    def rec_list(self, uid, pid, eid=None, nid=None, rec_ids=(), orphans=False, sem_paciente=False):
        if sem_paciente:
            self._sem_0024()
        ids = [str(x) for x in rec_ids or ()][:20]
        out, limite = [], time.time() - 12 * 3600
        for rid, r in sorted(self.recs.items(), key=lambda kv: kv[1].get("created", 0)):
            orfa = orphans and not r["event_id"] and not r["note_id"] and r.get("created", time.time()) > limite
            if sem_paciente:
                vale = r["uid"] == uid and r["pid"] is None and r.get("sem_paciente") and rid in ids
            else:
                vale = r["uid"] == uid and self._do_paciente(r, pid) and ((eid and r["event_id"] == eid) or (nid and r["note_id"] == nid)
                                                                         or rid in ids or orfa)
            if vale:
                segs = [dict({k: s[k] for k in ("seq", "at", "dur", "text", "duvidas")}, falas=self._falas(s))
                        for (q, _), s in sorted(self.segs.items()) if q == rid]
                out.append({"rec_id": rid, "status": r["status"], "consent_at": r["consent_at"], "seconds": r["seconds"],
                            "updated_at": r.get("updated_at") or self._agora(), "event_id": r["event_id"], "note_id": r["note_id"],
                            "scribe": r.get("scribe"), "segments": segs, "audio": self._partes(rid)})
        return out

    def rec_generated(self, uid, pid, rids, meta, nid=None):
        if not self._vale():
            return
        for rid in rids:
            r = self.recs.get(rid)
            if r and r["uid"] == uid and self._do_paciente(r, pid):
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
        for tab in (self.segs, self.audio):                 # o áudio sai junto (a cascata de recording_audio)
            for k in [k for k in tab if k[0] == rid]:
                tab.pop(k)
        return {"patient_id": r["pid"]}

    def rec_set_fala(self, uid, pid, rid, seq, i, q):
        """Como db.rec_set_fala: só na gravação deste médico e paciente, numa fala que existe; marca manual."""
        from app import db
        if q not in db.FALA_Q:
            raise ValueError("q")
        if self.sem_falas:
            raise db.MigracaoPendente("0023_falantes.sql")
        r, s = self.recs.get(rid), self.segs.get((rid, seq))
        if not self._vale() or not r or r["uid"] != uid or not self._do_paciente(r, pid) or not s or not 0 <= i < len(s.get("falas") or []):
            return None
        s["falas"][i] = dict(s["falas"][i], q=q, manual=True)
        return self._falas(s)

    def rec_add_audio(self, uid, pid, rid, part, n, at, upto, mime, data, max_day_bytes, *, sess, max_part_bytes):
        """Como db.rec_add_audio: sem_gravacao, repetido (mesma sessão), ocupada (outra sessão), sem_inicio, teto,
        teto_parte, ok."""
        from app import db
        if self.sem_migracao:
            raise db.MigracaoPendente("0022_gravacao_audio.sql")
        if pid is None:
            self._sem_0024()
        r = self.recs.get(rid)
        dono = r and r["uid"] == uid and (r.get("sem_paciente") if pid is None else self._do_paciente(r, pid))
        if not self._vale() or not dono:
            return "sem_gravacao"                            # nunca cria a gravação
        ja = self.audio.get((rid, part, n))
        if ja:
            return "repetido" if ja["sess"] == sess else "ocupada"
        if n > 0:
            p0 = self.audio.get((rid, part, 0))
            if not p0:
                return "sem_inicio"
            if p0["sess"] != sess:
                return "ocupada"                             # a parte é de outra sessão (outra aba)
            mime = p0["mime"]
        dia = time.time() - 86400
        if sum(a["size"] for a in self.audio.values() if a["uid"] == uid and a["created"] > dia) + len(data) > max_day_bytes:
            return "teto"
        if sum(a["size"] for (q, p, _), a in self.audio.items() if q == rid and p == part) + len(data) > max_part_bytes:
            return "teto_parte"
        self.audio[(rid, part, n)] = {"uid": uid, "at": at, "upto": upto, "mime": mime, "size": len(data),
                                      "data": bytes(data), "sess": sess, "created": time.time()}
        return "ok"

    def rec_audio(self, uid, rid, part):
        r = self.recs.get(rid)
        if self.sem_migracao or not r or r["uid"] != uid or (rid, part, 0) not in self.audio:
            return None
        k = 0
        while (rid, part, k) in self.audio:                 # os contíguos a partir de n = 0
            k += 1
        return {"mime": self.audio[(rid, part, 0)]["mime"], "data": b"".join(self.audio[(rid, part, i)]["data"] for i in range(k)),
                "patient_id": r["pid"]}

    def _partes(self, rid):
        """Como db._audio_partes: só as partes com n = 0; upto = o maior dos pedaços contíguos."""
        if self.sem_migracao:
            return []
        out = []
        for part in sorted({p for (q, p, n) in self.audio if q == rid and n == 0}):
            a0, n, upto = self.audio[(rid, part, 0)], 0, 0.0
            while (rid, part, n) in self.audio:
                upto = max(upto, self.audio[(rid, part, n)]["upto"]); n += 1
            out.append({"part": part, "at": a0["at"], "upto": upto})
        return out
