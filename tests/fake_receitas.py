"""Receitas e dados do médico em memória, com os MESMOS contratos de app/db.py (list/get/create/update/delete/emit/
cancel_receita, add_example_receitas, get/update_medico). Uma cópia só, usada pelos testes das rotas
(tests/test_receitas.py) e pelo preview local (scripts/preview_gravacao.py): mudou uma regra no db.py, muda aqui."""
import datetime as dt
import uuid

NOMES = ("list_receitas", "get_receita", "create_receita", "update_receita", "delete_receita", "emit_receita",
         "cancel_receita", "add_example_receitas", "get_medico", "update_medico")
CAMPOS = ("name", "crm", "crm_uf", "especialidade", "consultorio_endereco", "consultorio_telefone", "receita_papel")


class FakeReceitas:
    def __init__(self, medicos=None):
        self.rx = {}                                     # id → receita (com "user_id")
        self.medicos = dict(medicos or {})               # user_id → {campos}

    def install(self, setattr_):
        from app import db
        for nome in NOMES:
            setattr_(db, nome, getattr(self, nome))

    def reset(self):
        self.rx.clear()

    @staticmethod
    def _agora():
        return dt.datetime.now(dt.timezone.utc).isoformat()

    @staticmethod
    def _pub(r):
        return {k: v for k, v in r.items() if k != "user_id"}

    def _nova(self, user_id, patient_id, itens, tipo="simples", note_id=None, event_id=None, status="rascunho", emitida_em=None):
        r = {"id": str(uuid.uuid4()), "user_id": user_id, "patient_id": patient_id, "note_id": note_id, "event_id": event_id,
             "tipo": tipo, "status": status, "itens": [dict(i) for i in itens], "emitida_em": emitida_em, "cancelada_em": None,
             "motivo_cancelamento": None, "created_at": emitida_em or self._agora(), "updated_at": emitida_em or self._agora()}
        self.rx[r["id"]] = r
        return r

    # ----- os contratos de app/db.py -----
    def list_receitas(self, user_id, patient_id):
        rs = [r for r in self.rx.values() if r["user_id"] == user_id and r["patient_id"] == patient_id]
        return [self._pub(r) for r in sorted(rs, key=lambda r: r["emitida_em"] or r["created_at"], reverse=True)]

    def get_receita(self, user_id, receita_id):
        r = self.rx.get(receita_id)
        return self._pub(r) if r and r["user_id"] == user_id else None

    def create_receita(self, user_id, patient_id, itens, tipo="simples", note_id=None, event_id=None):
        return self._pub(self._nova(user_id, patient_id, itens, tipo, note_id, event_id))

    def update_receita(self, user_id, receita_id, itens):
        r = self.rx.get(receita_id)
        if not r or r["user_id"] != user_id or r["status"] != "rascunho":
            return None
        r.update(itens=[dict(i) for i in itens], updated_at=self._agora())
        return self._pub(r)

    def delete_receita(self, user_id, receita_id):
        r = self.rx.get(receita_id)
        if not r or r["user_id"] != user_id or r["status"] != "rascunho":
            return None
        return self.rx.pop(receita_id)["patient_id"]

    def emit_receita(self, user_id, receita_id, grupos):
        r = self.rx.get(receita_id)
        if not r or r["user_id"] != user_id or r["status"] != "rascunho":
            return None
        agora = self._agora()
        r.update(tipo=grupos[0][0], itens=[dict(i) for i in grupos[0][1]], status="emitida", emitida_em=agora, updated_at=agora)
        out = [self._pub(r)]
        for tipo, itens in grupos[1:]:
            out.append(self._pub(self._nova(user_id, r["patient_id"], itens, tipo, r["note_id"], r["event_id"], "emitida", agora)))
        return out

    def cancel_receita(self, user_id, receita_id, motivo):
        r = self.rx.get(receita_id)
        if not r or r["user_id"] != user_id or r["status"] != "emitida":
            return None
        r.update(status="cancelada", cancelada_em=self._agora(), motivo_cancelamento=motivo, updated_at=self._agora())
        return self._pub(r)

    def add_example_receitas(self, user_id, patient_id, rows):
        for note_id, emitida_em, itens in rows:
            quando = emitida_em.isoformat() if hasattr(emitida_em, "isoformat") else emitida_em
            self._nova(user_id, patient_id, itens, "simples", note_id, None, "emitida", quando)

    def get_medico(self, user_id):
        return {k: self.medicos.get(user_id, {}).get(k) for k in CAMPOS}

    def update_medico(self, user_id, campos):
        self.medicos.setdefault(user_id, {}).update({k: v for k, v in campos.items() if k in CAMPOS})
        return self.get_medico(user_id)
