"""Camada de banco (Supabase/Postgres + pgvector)."""
import psycopg
from pgvector.psycopg import register_vector

from . import config

# config de full-text por idioma do documento
_TS = {"english": "english", "portuguese": "portuguese"}


def connect():
    """Conexão avulsa (usada por scripts one-shot, ex.: ingestão)."""
    conn = psycopg.connect(config.require_db())
    register_vector(conn)
    return conn


# --- pool para o servidor (evita reconectar ~3s por request) ---
_pool = None


def get_pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            config.require_db(), min_size=1, max_size=5, open=True,
            kwargs={"connect_timeout": 15},
            configure=register_vector,
        )
    return _pool


def connection():
    """Context manager que empresta uma conexão do pool."""
    return get_pool().connection()


def upsert_document(conn, *, source, source_type, title, url, language,
                    publication_date, license, raw_path, content_hash):
    """Insere o documento; se já existir (source+content_hash), devolve (id, created=False)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into documents
              (source, source_type, title, url, language, publication_date, license, raw_path, content_hash)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (source, content_hash) do nothing
            returning id
            """,
            (source, source_type, title, url, language, publication_date, license, raw_path, content_hash),
        )
        row = cur.fetchone()
        if row:
            return row[0], True
        cur.execute(
            "select id from documents where source=%s and content_hash=%s",
            (source, content_hash),
        )
        return cur.fetchone()[0], False


def insert_chunks(conn, document_id, language, chunks, embeddings):
    """chunks: [(section_title, text)]; embeddings: list[list[float]] alinhado a chunks."""
    ts = _TS.get((language or "").lower(), "simple")
    with conn.cursor() as cur:
        for idx, ((section, text), emb) in enumerate(zip(chunks, embeddings)):
            cur.execute(
                f"""
                insert into chunks (document_id, section_title, chunk_index, text, embedding, tsv)
                values (%s,%s,%s,%s,%s, to_tsvector('{ts}', %s))
                on conflict (document_id, chunk_index) do nothing
                """,
                (document_id, section, idx, text, emb, text),
            )
    conn.commit()


def upsert_documents_bulk(conn, rows):
    """rows: tuplas (source, source_type, title, url, language, publication_date,
    license, raw_path, content_hash). 1 round-trip. Devolve {content_hash: id} dos NOVOS."""
    if not rows:
        return {}
    ph = ",".join(["(%s,%s,%s,%s,%s,%s,%s,%s,%s)"] * len(rows))
    sql = ("insert into documents (source, source_type, title, url, language, "
           "publication_date, license, raw_path, content_hash) values " + ph +
           " on conflict (source, content_hash) do nothing returning content_hash, id")
    flat = [v for r in rows for v in r]
    with conn.cursor() as cur:
        cur.execute(sql, flat)
        return {h: i for (h, i) in cur.fetchall()}


def insert_chunks_bulk(conn, rows, language="english"):
    """rows: (document_id, section_title, chunk_index, text, embedding). 1 round-trip."""
    if not rows:
        return
    ts = _TS.get((language or "").lower(), "simple")
    unit = "(%s,%s,%s,%s,%s, to_tsvector('" + ts + "', %s))"
    ph = ",".join([unit] * len(rows))
    sql = ("insert into chunks (document_id, section_title, chunk_index, text, embedding, tsv) "
           "values " + ph + " on conflict (document_id, chunk_index) do nothing")
    flat = []
    for (doc_id, section, idx, text, emb) in rows:
        flat += [doc_id, section, idx, text, emb, text]
    with conn.cursor() as cur:
        cur.execute(sql, flat)
    conn.commit()


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from documents")
        d = cur.fetchone()[0]
        cur.execute("select count(*) from chunks")
        c = cur.fetchone()[0]
    return d, c


# ===== usuários + tokens de calendário (Fase B, multiusuário) =====

_USER_COLS = "id, email, name, picture, session_version"


def _row_to_user(row):
    """sv = versão da sessão (muda ao trocar a senha; o cookie guarda a versão com que foi criado)."""
    if not row:
        return None
    return {"id": str(row[0]), "email": row[1], "name": row[2], "picture": row[3],
            "sv": row[4] if len(row) > 4 else 0}


def upsert_user(email, name=None, picture=None, google_sub=None):
    """Cria ou atualiza o usuário pela conta Google; devolve o dict do usuário.
    E-mail sempre em minúsculas — o mesmo do login por código, para não duplicar a conta."""
    email = (email or "").strip().lower()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into users (email, name, picture, google_sub, terms_accepted_at, last_login)
                values (%s,%s,%s,%s, now(), now())
                on conflict (email) do update set
                  name = coalesce(excluded.name, users.name),
                  picture = coalesce(excluded.picture, users.picture),
                  google_sub = coalesce(excluded.google_sub, users.google_sub),
                  last_login = now()
                returning id, email, name, picture, session_version
                """,
                (email, name, picture, google_sub),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_user(row)


def get_user(user_id):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_USER_COLS} from users where id = %s", (user_id,))
            return _row_to_user(cur.fetchone())


# ===== login por e-mail: senha + código de confirmação (cadastro / redefinir senha) =====

CODE_TTL_S = 10 * 60          # o código vale 10 min
CODE_MAX_ATTEMPTS = 5         # tentativas por código
CODE_RESEND_S = 30            # intervalo mínimo entre envios para o mesmo e-mail
CODE_MAX_PER_HOUR = 5         # envios por e-mail por hora


def user_by_email(email):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_USER_COLS} from users where lower(email) = lower(%s)", (email,))
            return _row_to_user(cur.fetchone())


LOCK_AFTER = 5                # senhas erradas seguidas até bloquear
LOCK_MINUTES = 15


def create_email_user(email, name, password_hash):
    """Cadastro por e-mail, depois de confirmar o código: grava a senha e o aceite dos termos.
    Se o e-mail passou a existir no meio do caminho (entrou pelo Google), o dono do e-mail acabou de
    prová-lo com o código: só define a senha se a conta ainda não tinha uma."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                insert into users (email, name, password_hash, terms_accepted_at, last_login)
                values (%s, %s, %s, now(), now())
                on conflict (email) do update set
                  name = coalesce(users.name, excluded.name),
                  password_hash = coalesce(users.password_hash, excluded.password_hash),
                  terms_accepted_at = coalesce(users.terms_accepted_at, excluded.terms_accepted_at),
                  last_login = now()
                returning {_USER_COLS}
                """,
                (email, name, password_hash),
            )
            row = cur.fetchone()
        conn.commit()
    return _row_to_user(row)


def account(email):
    """O que a tela inicial precisa saber: a conta existe? tem senha? (None = não existe)"""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select password_hash is not null from users where lower(email) = lower(%s)", (email,))
            row = cur.fetchone()
    return None if row is None else {"password": bool(row[0])}


def password_login_info(email):
    """Dados para conferir a senha: dict com id, hash, sv e segundos restantes de bloqueio (ou None)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id, password_hash, session_version,
                          greatest(0, ceil(extract(epoch from locked_until - now())))::int
                   from users where lower(email) = lower(%s)""", (email,))
            row = cur.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "hash": row[1], "sv": row[2], "locked_s": row[3] or 0}


def login_failed(user_id):
    """Senha errada: conta o erro e bloqueia por LOCK_MINUTES após LOCK_AFTER seguidos.
    Devolve (tentativas restantes, segundos de bloqueio)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """update users set
                     failed_logins = case when failed_logins + 1 >= %s then 0 else failed_logins + 1 end,
                     locked_until  = case when failed_logins + 1 >= %s
                                          then now() + %s * interval '1 minute' else locked_until end
                   where id = %s returning failed_logins, locked_until > now()""",
                (LOCK_AFTER, LOCK_AFTER, LOCK_MINUTES, user_id))
            failed, locked = cur.fetchone()
        conn.commit()
    return (0, LOCK_MINUTES * 60) if locked else (LOCK_AFTER - failed, 0)


def login_succeeded(user_id):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("update users set failed_logins = 0, locked_until = null, last_login = now() where id = %s",
                        (user_id,))
        conn.commit()


def record_login(user_id, event, method, ip=None, user_agent=None, device=None):
    """Registra um acesso (tabela login_events). Numa entrada ("entrou"), devolve True se o aparelho é
    novo numa conta que já tinha entradas registradas — a primeira registrada não conta (não há com o
    que comparar: contas antigas e contas recém-criadas não recebem aviso)."""
    with connection() as conn:
        new_device = False
        if event == "entrou":
            before, known = conn.execute(
                """select exists(select 1 from login_events where user_id = %s and event = 'entrou'),
                          exists(select 1 from login_events where user_id = %s and event = 'entrou' and device = %s)""",
                (user_id, user_id, device)).fetchone()
            new_device = bool(before and not known)
        conn.execute("""insert into login_events (user_id, event, method, ip, user_agent, device)
                        values (%s,%s,%s,%s,%s,%s)""",
                     (user_id, event, method, (ip or "")[:64] or None, (user_agent or "")[:400] or None, device))
        conn.commit()
    return new_device


# ----- limpeza (LGPD: não guardar além do necessário) -----
# Códigos de e-mail: 1 dia. Registro de acessos: 1 ano (o Marco Civil exige pelo menos 6 meses).
# O registro de acesso ao PRONTUÁRIO (access_log) não entra aqui: faz parte do prontuário.
RETENTION = {"login_codes": "1 day", "login_events": "1 year"}


def cleanup_old_records():
    """Apaga o que passou do prazo. Devolve {tabela: linhas apagadas}."""
    out = {}
    with connection() as conn:
        for table, keep in RETENTION.items():
            cur = conn.execute(f"delete from {table} where created_at < now() - interval '{keep}'")
            out[table] = cur.rowcount
        conn.commit()
    return out


def set_password(user_id, password_hash):
    """Nova senha (redefinição): zera bloqueio e muda a versão da sessão — as sessões abertas em
    outros aparelhos deixam de valer. Devolve o usuário atualizado."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""update users set password_hash = %s, session_version = session_version + 1,
                                     failed_logins = 0, locked_until = null, last_login = now()
                    where id = %s returning {_USER_COLS}""", (password_hash, user_id))
            row = cur.fetchone()
        conn.commit()
    return _row_to_user(row)


def new_login_code(email, code_hash):
    """Guarda um código novo e invalida os anteriores. Devolve ("ok", 0), ("aguarde", segundos)
    ou ("limite", 0) quando o e-mail já recebeu códigos demais."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from login_codes where created_at < now() - interval '1 day'")
            cur.execute(
                """select count(*), extract(epoch from now() - max(created_at))
                   from login_codes where email = %s and created_at > now() - interval '1 hour'""",
                (email,))
            n, since = cur.fetchone()
            if since is not None and since < CODE_RESEND_S:
                conn.commit()
                return "aguarde", int(CODE_RESEND_S - since) + 1
            if n >= CODE_MAX_PER_HOUR:
                conn.commit()
                return "limite", 0
            cur.execute("update login_codes set used_at = now() where email = %s and used_at is null", (email,))
            cur.execute(
                "insert into login_codes (email, code_hash, expires_at) values (%s, %s, now() + %s * interval '1 second')",
                (email, code_hash, CODE_TTL_S))
        conn.commit()
    return "ok", 0


def discard_login_code(email):
    """O envio falhou: apaga o código que acabou de ser criado (não conta para reenvio/limite)."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """delete from login_codes where id = (select id from login_codes
                   where email = %s and used_at is null order by created_at desc limit 1)""", (email,))
        conn.commit()


def check_login_code(email, code_hash):
    """Confere o código mais recente do e-mail. Devolve ("ok", 0), ("errado", tentativas restantes),
    ("expirado", 0) ou ("bloqueado", 0). O código só serve uma vez."""
    import hmac
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select id, code_hash, attempts, expires_at > now() from login_codes
                   where email = %s and used_at is null order by created_at desc limit 1 for update""",
                (email,))
            row = cur.fetchone()
            if not row or not row[3]:
                conn.commit()
                return "expirado", 0
            cid, h, attempts, _ = row
            if attempts >= CODE_MAX_ATTEMPTS:
                conn.commit()
                return "bloqueado", 0
            if hmac.compare_digest(h, code_hash):
                cur.execute("update login_codes set used_at = now() where id = %s", (cid,))
                conn.commit()
                return "ok", 0
            cur.execute("update login_codes set attempts = attempts + 1 where id = %s", (cid,))
            conn.commit()
    left = CODE_MAX_ATTEMPTS - attempts - 1
    return ("errado", left) if left > 0 else ("bloqueado", 0)


def set_token(user_id, provider, *, access_token, refresh_token, expires_at, scope, account_email):
    """Grava/atualiza o token de calendário do usuário. Não apaga o refresh_token
    existente se o provedor não mandar um novo nesta troca."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into oauth_tokens
                  (user_id, provider, access_token, refresh_token, expires_at, scope, account_email, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s, now())
                on conflict (user_id, provider) do update set
                  access_token = excluded.access_token,
                  refresh_token = coalesce(excluded.refresh_token, oauth_tokens.refresh_token),
                  expires_at = excluded.expires_at,
                  scope = excluded.scope,
                  account_email = coalesce(excluded.account_email, oauth_tokens.account_email),
                  updated_at = now()
                """,
                (user_id, provider, access_token, refresh_token, expires_at, scope, account_email),
            )
        conn.commit()


def get_token(user_id, provider):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select access_token, refresh_token, expires_at, scope, account_email
                   from oauth_tokens where user_id = %s and provider = %s""",
                (user_id, provider),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {"access_token": row[0], "refresh_token": row[1], "expires_at": row[2],
            "scope": row[3], "account_email": row[4]}


def update_access_token(user_id, provider, access_token, expires_at, refresh_token=None):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """update oauth_tokens set access_token=%s, expires_at=%s,
                   refresh_token=coalesce(%s, refresh_token), updated_at=now()
                   where user_id=%s and provider=%s""",
                (access_token, expires_at, refresh_token, user_id, provider),
            )
        conn.commit()


def delete_token(user_id, provider):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("delete from oauth_tokens where user_id=%s and provider=%s",
                        (user_id, provider))
        conn.commit()


def connected_providers(user_id):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select provider, account_email from oauth_tokens where user_id=%s",
                (user_id,))
            return {p: email for (p, email) in cur.fetchall()}


# --- prontuário (anotações clínicas por paciente) ---
def patient_key(name):
    """Chave estável do paciente a partir do nome: minúsculas, sem acento, espaços únicos.
    Tira só os acentos (marcas combinantes): letras de outros alfabetos e ł/ø/ß continuam,
    então "李雷" ou "Łukasz" têm chave própria (antes viravam "" e "ukasz")."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "")
    n = "".join(c for c in n if not unicodedata.combining(c))
    return " ".join(n.casefold().split())


class NoteLocked(Exception):
    """Evolução finalizada: não pode mais ser alterada (só adendos)."""


_PCOLS = "id, name, patient_key, birth_date, sex, cpf, phone, allergies, problems, medications"


def _patient(r):
    return {"id": r[0], "name": r[1], "key": r[2], "example": r[2] == EXAMPLE_KEY,
            "birth_date": r[3].isoformat() if r[3] else None, "sex": r[4], "cpf": r[5], "phone": r[6],
            "allergies": r[7] or "", "problems": r[8] or "", "medications": r[9] or ""}


def list_patients(user_id, limit=1000):
    """Pacientes do médico (os usados mais recentemente primeiro), com nascimento/sexo (para
    diferenciar homônimos) e o resumo do prontuário: nº de anotações e data da última."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """select p.id, p.name, p.birth_date, p.sex, p.patient_key = %s,
                          count(n.id) filter (where n.content <> ''),
                          max(coalesce(n.event_start, n.created_at)) filter (where n.content <> '')
                   from patients p
                   left join clinical_notes n on n.user_id = p.user_id and n.patient_id = p.id
                   where p.user_id = %s
                   group by p.id
                   order by p.updated_at desc limit %s""",
                (EXAMPLE_KEY, user_id, limit))
            return [{"id": r[0], "name": r[1], "birth_date": r[2].isoformat() if r[2] else None, "sex": r[3],
                     "example": r[4], "notes": r[5], "last": r[6].isoformat() if r[6] else None} for r in cur.fetchall()]


def find_patients(user_id, name):
    """Pacientes com o mesmo nome normalizado (homônimos)."""
    with connection() as conn:
        rows = conn.execute(f"select {_PCOLS} from patients where user_id = %s and patient_key = %s order by id",
                            (user_id, patient_key(name))).fetchall()
    return [_patient(r) for r in rows]


def find_by_cpf(user_id, cpf, exclude_id=None):
    """Outro paciente do médico com o mesmo CPF (o CPF identifica a pessoa)."""
    if not cpf:
        return None
    with connection() as conn:
        r = conn.execute(f"""select {_PCOLS} from patients where user_id = %s and cpf = %s
                             and (%s::bigint is null or id <> %s) limit 1""",
                         (user_id, cpf, exclude_id, exclude_id)).fetchone()
    return _patient(r) if r else None


# paciente fictícia criada em toda conta nova (app/exemplo.py); pode ser excluída mesmo com prontuário.
# É reconhecida pela CHAVE, nunca pelo nome ("Maria Silva" é comum): patient_key() jamais devolve texto
# começando com espaço, então nenhum paciente real — nem consulta antiga só com o nome — cai nela.
EXAMPLE_NAME = "Maria Silva"
EXAMPLE_KEY = " exemplo"


def create_patient(user_id, name, birth_date=None, sex=None, cpf=None, phone=None, key=None):
    with connection() as conn:
        r = conn.execute(
            f"""insert into patients (user_id, patient_key, name, birth_date, sex, cpf, phone)
                values (%s,%s,%s,%s,%s,%s,%s) returning {_PCOLS}""",
            (user_id, key or patient_key(name), name, birth_date, sex, cpf, phone)).fetchone()
        conn.commit()
    return _patient(r)


class AmbiguousPatient(Exception):
    """Há mais de um paciente com esse nome: não dá para adivinhar qual (homônimos)."""


def ensure_patient(user_id, name):
    """Paciente pelo nome (eventos antigos, só com o nome): o único cadastrado com esse nome, ou um
    novo. Com homônimos levanta AmbiguousPatient (nunca escolhe um ao acaso). Retorna ({...}, created)."""
    same = find_patients(user_id, name)
    if len(same) > 1:
        raise AmbiguousPatient()
    if same:
        return same[0], False
    return create_patient(user_id, name), True


def get_patient(user_id, patient_id):
    """Paciente do médico pelo id (cadastro completo) ou None (inclusive se for de outro médico)."""
    with connection() as conn:
        r = conn.execute(f"select {_PCOLS} from patients where user_id = %s and id = %s",
                         (user_id, patient_id)).fetchone()
    return _patient(r) if r else None


_PATIENT_FIELDS = ("name", "birth_date", "sex", "cpf", "phone", "allergies", "problems", "medications")


def update_patient(user_id, patient_id, fields):
    """Atualiza campos do cadastro/resumo clínico. Mudou o nome → atualiza também as anotações.
    Retorna o paciente atualizado ou None se não existir."""
    if "name" in fields:                                  # mesmo nome de novo (formulário inteiro): não mexe na chave
        cur_p = get_patient(user_id, patient_id)
        if cur_p and cur_p["name"] == fields["name"]:
            fields = {k: v for k, v in fields.items() if k != "name"}
    sets, vals = [], []
    for k in _PATIENT_FIELDS:
        if k in fields:
            sets.append(f"{k} = %s"); vals.append(fields[k])
    if "name" in fields:
        sets.append("patient_key = %s"); vals.append(patient_key(fields["name"]))
    if not sets:
        return get_patient(user_id, patient_id)
    with connection() as conn:
        r = conn.execute(f"update patients set {', '.join(sets)}, updated_at = now() "
                         f"where user_id = %s and id = %s returning {_PCOLS}",
                         (*vals, user_id, patient_id)).fetchone()
        if r and "name" in fields:
            conn.execute("""update clinical_notes set patient_name = %s, patient_key = %s
                            where user_id = %s and patient_id = %s""",
                         (fields["name"], patient_key(fields["name"]), user_id, patient_id))
        conn.commit()
    return _patient(r) if r else None


def touch_patient(user_id, patient_id):
    """Marca o paciente como usado agora ("Pacientes recentes" na agenda)."""
    with connection() as conn:
        conn.execute("update patients set updated_at = now() where user_id = %s and id = %s",
                     (user_id, patient_id))
        conn.commit()


def delete_patient(user_id, patient_id):
    """Exclui o cadastro só se não houver prontuário (anotações são registro de saúde e ficam).
    A paciente de exemplo (fictícia) sai com tudo. Retorna 'ok', 'has_notes' ou 'not_found'."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select patient_key from patients where user_id = %s and id = %s", (user_id, patient_id))
            r = cur.fetchone()
            if not r:
                return "not_found"
            if r[0] == EXAMPLE_KEY:
                cur.execute("delete from patient_files where user_id = %s and patient_id = %s", (user_id, patient_id))
                cur.execute("""delete from note_addenda where note_id in
                               (select id from clinical_notes where user_id = %s and patient_id = %s)""", (user_id, patient_id))
                cur.execute("delete from clinical_notes where user_id = %s and patient_id = %s", (user_id, patient_id))
                cur.execute("delete from patients where user_id = %s and id = %s", (user_id, patient_id))
                conn.commit()
                return "ok"
            cur.execute("""select 1 from clinical_notes where user_id = %s and (content <> '' or signed_at is not null)
                           and (patient_id = %s or (patient_id is null and patient_key = %s)) limit 1""",
                        (user_id, patient_id, r[0]))
            if cur.fetchone():
                return "has_notes"
            cur.execute("select 1 from patient_files where user_id = %s and patient_id = %s limit 1", (user_id, patient_id))
            if cur.fetchone():                          # exame anexado também é prontuário
                return "has_notes"
            cur.execute("""select 1 from recording_segments s join recordings r on r.id = s.rec_id
                           where r.user_id = %s and r.patient_id = %s limit 1""", (user_id, patient_id))
            if cur.fetchone():                          # transcrição de consulta também (gravação vazia sai junto)
                return "has_notes"
            cur.execute("delete from clinical_notes where user_id = %s and patient_id = %s", (user_id, patient_id))
            cur.execute("delete from patients where user_id = %s and id = %s", (user_id, patient_id))
        conn.commit()
    return "ok"


_NOTE_COLS = """n.id, n.event_id, n.event_title, n.event_start, n.content, n.updated_at, n.data, n.signed_at,
                coalesce((select json_agg(json_build_object('id', a.id, 'content', a.content, 'created_at', a.created_at)
                                          order by a.created_at)
                          from note_addenda a where a.note_id = n.id), '[]'::json)"""


def _note(r):
    return {"id": r[0], "event_id": r[1], "event_title": r[2],
            "event_start": r[3].isoformat() if r[3] else None, "content": r[4],
            "updated_at": r[5].isoformat() if r[5] else None, "data": r[6],
            "signed_at": r[7].isoformat() if r[7] else None, "addenda": r[8] or []}


def list_notes(user_id, patient_id, pkey):
    """Prontuário do paciente: evoluções ligadas a ele (e antigas, só com o nome, sem vínculo),
    com dados estruturados, finalização e adendos."""
    with connection() as conn:
        rows = conn.execute(
            f"""select {_NOTE_COLS} from clinical_notes n
                where n.user_id = %s and (n.patient_id = %s or (n.patient_id is null and n.patient_key = %s))
                order by coalesce(n.event_start, n.created_at) desc limit 300""",
            (user_id, patient_id, pkey)).fetchall()
    return [_note(r) for r in rows]


def upsert_note(user_id, patient_id, pkey, patient_name, event_id, event_title, event_start, content,
                note_id=None, data=None):
    """Uma evolução por consulta (event_id); sem consulta, cria uma nova (ou atualiza a avulsa
    note_id que está sendo escrita). Evolução finalizada não muda: levanta NoteLocked."""
    from psycopg.types.json import Jsonb
    jd = Jsonb(data) if data is not None else None
    with connection() as conn:
        with conn.cursor() as cur:
            if not event_id and note_id:
                cur.execute("select signed_at from clinical_notes where user_id = %s and id = %s and patient_id = %s",
                            (user_id, note_id, patient_id))
                r = cur.fetchone()
                if r and r[0]:
                    raise NoteLocked()
                if r:
                    cur.execute("""update clinical_notes set content = %s, data = %s, updated_at = now()
                                   where user_id = %s and id = %s returning id""", (content, jd, user_id, note_id))
                    nid = cur.fetchone()[0]
                    conn.commit()
                    return nid
            if event_id:
                cur.execute("select signed_at from clinical_notes where user_id = %s and event_id = %s",
                            (user_id, event_id))
                r = cur.fetchone()
                if r and r[0]:
                    raise NoteLocked()
                cur.execute(
                    """insert into clinical_notes
                         (user_id, patient_id, patient_key, patient_name, event_id, event_title, event_start, content, data)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (user_id, event_id) where event_id is not null do update set
                         content = excluded.content, data = excluded.data, patient_id = excluded.patient_id,
                         patient_key = excluded.patient_key, patient_name = excluded.patient_name,
                         event_title = excluded.event_title, event_start = excluded.event_start,
                         updated_at = now()
                       where clinical_notes.signed_at is null
                       returning id""",
                    (user_id, patient_id, pkey, patient_name, event_id, event_title, event_start, content, jd))
            else:
                cur.execute(
                    """insert into clinical_notes (user_id, patient_id, patient_key, patient_name, content, data)
                       values (%s,%s,%s,%s,%s,%s) returning id""",
                    (user_id, patient_id, pkey, patient_name, content, jd))
            r = cur.fetchone()
            if not r:                                   # finalizada entre a checagem e o update
                conn.rollback()
                raise NoteLocked()
            nid = r[0]
        conn.commit()
    return nid


def get_note(user_id, note_id):
    with connection() as conn:
        r = conn.execute(f"select {_NOTE_COLS}, n.patient_id from clinical_notes n where n.user_id = %s and n.id = %s",
                         (user_id, note_id)).fetchone()
    if not r:
        return None
    n = _note(r); n["patient_id"] = r[9]
    return n


def update_note(user_id, note_id, content, data=None):
    """Edita uma evolução ainda não finalizada (pelo id). False se finalizada, None se não existe."""
    from psycopg.types.json import Jsonb
    with connection() as conn:
        r = conn.execute("select signed_at from clinical_notes where user_id = %s and id = %s",
                         (user_id, note_id)).fetchone()
        if not r:
            return None
        if r[0]:
            return False
        conn.execute("""update clinical_notes set content = %s, data = %s, updated_at = now()
                        where user_id = %s and id = %s and signed_at is null""",
                     (content, Jsonb(data) if data is not None else None, user_id, note_id))
        conn.commit()
    return True


def finalize_note(user_id, note_id, timing=None):
    """Finaliza (assina) a evolução: a partir daí só adendos. Devolve signed_at (ISO) ou None.
    timing: só números do tempo de documentação (sem conteúdo), gravados na primeira finalização."""
    from psycopg.types.json import Jsonb
    with connection() as conn:
        r = conn.execute("""update clinical_notes set signed_at = coalesce(signed_at, now()),
                                   data = case when signed_at is null and %s::jsonb is not null
                                               then coalesce(data, '{}'::jsonb) || jsonb_build_object('timing', %s::jsonb)
                                               else data end
                            where user_id = %s and id = %s and (content ~ '\\S' or signed_at is not null)   -- algo visível (não só espaços/quebras)
                            returning signed_at""",
                         (Jsonb(timing) if timing else None, Jsonb(timing) if timing else None, user_id, note_id)).fetchone()
        conn.commit()
    return r[0].isoformat() if r else None


def add_addendum(user_id, note_id, content):
    """Adendo a uma evolução finalizada. Devolve o adendo ou None (nota inexistente/não finalizada)."""
    with connection() as conn:
        ok = conn.execute("select 1 from clinical_notes where user_id = %s and id = %s and signed_at is not null",
                          (user_id, note_id)).fetchone()
        if not ok:
            return None
        r = conn.execute("""insert into note_addenda (note_id, user_id, content) values (%s,%s,%s)
                            returning id, content, created_at""", (note_id, user_id, content)).fetchone()
        conn.commit()
    return {"id": r[0], "content": r[1], "created_at": r[2].isoformat()}


def notes_by_event(user_id, event_ids):
    """Situação da evolução de cada consulta: {event_id: {note_id, signed_at, has_content}}."""
    if not event_ids:
        return {}
    with connection() as conn:
        rows = conn.execute("""select event_id, id, signed_at, content <> '' from clinical_notes
                               where user_id = %s and event_id = any(%s)""", (user_id, list(event_ids))).fetchall()
    return {r[0]: {"note_id": r[1], "signed_at": r[2].isoformat() if r[2] else None, "has_content": r[3]}
            for r in rows}


def add_example_notes(user_id, patient_id, pkey, patient_name, rows):
    """Histórico da paciente de exemplo: rows = (título, início, texto, dados, finalizada_em, atualizada_em)."""
    from psycopg.types.json import Jsonb
    with connection() as conn:
        with conn.cursor() as cur:
            for title, start, content, data, signed_at, updated_at in rows:
                cur.execute("""insert into clinical_notes (user_id, patient_id, patient_key, patient_name, event_title,
                                 event_start, content, data, signed_at, created_at, updated_at)
                               values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (user_id, patient_id, pkey, patient_name, title, start, content, Jsonb(data), signed_at,
                             updated_at, updated_at))
        conn.commit()


# --- exames anexados (PDF/imagem), sempre filtrados pelo médico ---
def add_file(user_id, patient_id, name, mime, data):
    with connection() as conn:
        r = conn.execute("""insert into patient_files (user_id, patient_id, name, mime, size, data)
                            values (%s,%s,%s,%s,%s,%s) returning id, created_at""",
                         (user_id, patient_id, name, mime, len(data), data)).fetchone()
        conn.commit()
    return {"id": r[0], "name": name, "mime": mime, "size": len(data), "created_at": r[1].isoformat()}


def list_files(user_id, patient_id):
    with connection() as conn:
        rows = conn.execute("""select id, name, mime, size, created_at from patient_files
                               where user_id = %s and patient_id = %s order by created_at desc""",
                            (user_id, patient_id)).fetchall()
    return [{"id": r[0], "name": r[1], "mime": r[2], "size": r[3], "created_at": r[4].isoformat()} for r in rows]


def get_file(user_id, file_id):
    with connection() as conn:
        r = conn.execute("select patient_id, name, mime, data from patient_files where user_id = %s and id = %s",
                         (user_id, file_id)).fetchone()
    return {"patient_id": r[0], "name": r[1], "mime": r[2], "data": bytes(r[3])} if r else None


def delete_file(user_id, file_id):
    """Apaga o anexo (ex.: arquivo errado ou de outro paciente). Devolve o patient_id ou None."""
    with connection() as conn:
        r = conn.execute("delete from patient_files where user_id = %s and id = %s returning patient_id",
                         (user_id, file_id)).fetchone()
        conn.commit()
    return r[0] if r else None


# --- gravação da consulta: só o texto de cada trecho (o áudio nunca chega aqui) ---
def rec_open(user_id, patient_id, rec_id, event_id=None, note_id=None, consent_at=None):
    """Garante a gravação rec_id deste médico e paciente. Devolve False se o id já é de outro médico ou
    paciente (não mistura), True se existe ou foi criada. A evolução só é ligada se for deste médico e paciente
    (id inexistente ou de outro não derruba o envio), e uma gravação ainda sem evolução ganha a que chegar."""
    with connection() as conn:
        if note_id is not None and not conn.execute(
                "select 1 from clinical_notes where id = %s and user_id = %s and patient_id = %s",
                (note_id, user_id, patient_id)).fetchone():
            note_id = None
        conn.execute("""insert into recordings (id, user_id, patient_id, event_id, note_id, consent_at)
                        values (%s,%s,%s,%s,%s,coalesce(%s::timestamptz, now())) on conflict (id) do nothing""",
                     (rec_id, user_id, patient_id, event_id, note_id, consent_at))
        if note_id is not None:
            conn.execute("""update recordings set note_id = %s where id = %s and user_id = %s and patient_id = %s
                            and note_id is null""", (note_id, rec_id, user_id, patient_id))
        r = conn.execute("select user_id::text, patient_id from recordings where id = %s", (rec_id,)).fetchone()
        conn.commit()
    return bool(r) and r[0] == str(user_id) and r[1] == patient_id


def rec_segment(user_id, rec_id, seq):
    """Trecho já transcrito (reenvio): {text, duvidas} ou None."""
    with connection() as conn:
        r = conn.execute("""select s.text, s.duvidas from recording_segments s join recordings r on r.id = s.rec_id
                            where r.user_id = %s and s.rec_id = %s and s.seq = %s""", (user_id, rec_id, seq)).fetchone()
    return {"text": r[0], "duvidas": r[1] or []} if r else None


def rec_prev_text(user_id, rec_id, seq):
    """Texto do trecho anterior (vai como contexto para a transcrição do próximo)."""
    with connection() as conn:
        r = conn.execute("""select s.text from recording_segments s join recordings r on r.id = s.rec_id
                            where r.user_id = %s and s.rec_id = %s and s.seq < %s order by s.seq desc limit 1""",
                         (user_id, rec_id, seq)).fetchone()
    return r[0] if r else ""


def rec_add_segment(user_id, rec_id, seq, at, dur, text, duvidas):
    """Guarda o texto do trecho (uma vez só por rec_id + seq) e avança a gravação."""
    from psycopg.types.json import Jsonb
    with connection() as conn:
        conn.execute("""insert into recording_segments (rec_id, seq, at_s, dur_s, text, duvidas)
                        select %s,%s,%s,%s,%s,%s where exists (select 1 from recordings where id = %s and user_id = %s)
                        on conflict (rec_id, seq) do nothing""",
                     (rec_id, seq, at, dur, text, Jsonb(list(duvidas or [])), rec_id, user_id))
        conn.execute("""update recordings set seconds = greatest(seconds, %s), status = 'gravando', updated_at = now()
                        where id = %s and user_id = %s""", (at + dur, rec_id, user_id))
        conn.commit()


def rec_seconds_today(user_id):
    """Segundos transcritos nas últimas 24 h (teto diário por médico)."""
    with connection() as conn:
        r = conn.execute("""select coalesce(sum(s.dur_s), 0) from recording_segments s join recordings r on r.id = s.rec_id
                            where r.user_id = %s and s.created_at > now() - interval '1 day'""", (user_id,)).fetchone()
    return float(r[0] or 0)


def rec_list(user_id, patient_id, event_id=None, note_id=None, rec_ids=(), orphans=False):
    """Gravações de uma consulta (pela consulta da agenda, pela evolução ou pelos ids que a página conhece),
    da mais antiga para a mais nova, com os trechos. orphans: também as gravações sem consulta e sem evolução
    deste paciente das últimas 12 h (consulta avulsa que ainda não foi salva)."""
    ids = [str(x) for x in rec_ids or ()][:20]
    if not (event_id or note_id or ids or orphans):
        return []
    with connection() as conn:
        rows = conn.execute(
            """select r.id::text, r.status, r.consent_at, r.seconds, r.updated_at, r.event_id, r.note_id, r.scribe,
                      coalesce((select json_agg(json_build_object('seq', s.seq, 'at', s.at_s, 'dur', s.dur_s, 'text', s.text,
                                                                  'duvidas', s.duvidas) order by s.seq)
                                from recording_segments s where s.rec_id = r.id), '[]'::json)
               from recordings r
               where r.user_id = %s and r.patient_id = %s
                 and ((%s::text is not null and r.event_id = %s) or (%s::bigint is not null and r.note_id = %s)
                      or r.id::text = any(%s::text[])
                      or (%s and r.event_id is null and r.note_id is null and r.updated_at > now() - interval '12 hours'))
               order by r.created_at""",
            (user_id, patient_id, event_id, event_id, note_id, note_id, ids, bool(orphans))).fetchall()
    return [{"rec_id": r[0], "status": r[1], "consent_at": r[2].isoformat(), "seconds": r[3],
             "updated_at": r[4].isoformat(), "event_id": r[5], "note_id": r[6], "scribe": r[7], "segments": r[8] or []}
            for r in rows]


def rec_generated(user_id, rec_ids, meta, note_id=None):
    """Marca as gravações como geradas. meta: versão do prompt, modelo, contagem dos pontos e a saída conferida
    ("saida": evolução e pontos para conferir), para a revisão continuar depois de recarregar ou noutro dia."""
    from psycopg.types.json import Jsonb
    with connection() as conn:
        if note_id is not None and not conn.execute("select 1 from clinical_notes where id = %s and user_id = %s",
                                                    (note_id, user_id)).fetchone():
            note_id = None
        conn.execute("""update recordings set status = 'gerada', scribe = %s, note_id = coalesce(note_id, %s), updated_at = now()
                        where user_id = %s and id::text = any(%s::text[])""", (Jsonb(meta), note_id, user_id, [str(x) for x in rec_ids]))
        conn.commit()


def rec_link_note(user_id, patient_id, rec_ids, note_id):
    """A evolução salva passa a apontar para as gravações que a geraram (consulta avulsa não tem event_id)."""
    if not rec_ids:
        return
    with connection() as conn:
        conn.execute("""update recordings set note_id = %s where user_id = %s and patient_id = %s and id::text = any(%s::text[])""",
                     (note_id, user_id, patient_id, [str(x) for x in rec_ids][:20]))
        conn.commit()


def rec_delete(user_id, rec_id):
    """Apaga a transcrição (gravação + trechos). Devolve o patient_id ou None."""
    with connection() as conn:
        r = conn.execute("delete from recordings where user_id = %s and id = %s returning patient_id", (user_id, rec_id)).fetchone()
        conn.commit()
    return r[0] if r else None


def last_note_content(user_id, patient_id, exclude_note_id=None, exclude_event_id=None):
    """Texto da evolução mais recente do paciente (para a continuidade da evolução gerada), fora a da consulta atual
    e os registros só de exames."""
    with connection() as conn:
        r = conn.execute("""select content from clinical_notes
                            where user_id = %s and patient_id = %s and content ~ '\\S' and coalesce(data->>'kind', '') <> 'labs'
                              and id is distinct from %s and (%s::text is null or event_id is distinct from %s)
                            order by coalesce(event_start, created_at) desc limit 1""",
                         (user_id, patient_id, exclude_note_id, exclude_event_id, exclude_event_id)).fetchone()
    return r[0] if r else ""


def recent_notes(user_id, limit=30):
    """Últimas evoluções do médico (para o perfil de escrita, calculado aqui no servidor: nenhum texto sai)."""
    with connection() as conn:
        rows = conn.execute("""select content, data from clinical_notes where user_id = %s and content <> ''
                               order by updated_at desc limit %s""", (user_id, limit)).fetchall()
    return [{"content": r[0], "data": r[1] or {}} for r in rows]


def log_access(user_id, action, patient_id=None, note_id=None, dedupe_minutes=0):
    """Registro de acesso ao prontuário. dedupe_minutes evita uma linha por salvamento automático."""
    with connection() as conn:
        if dedupe_minutes:
            r = conn.execute("""select 1 from access_log where user_id = %s and action = %s
                                and patient_id is not distinct from %s and note_id is not distinct from %s
                                and created_at > now() - make_interval(mins => %s) limit 1""",
                             (user_id, action, patient_id, note_id, dedupe_minutes)).fetchone()
            if r:
                return
        conn.execute("insert into access_log (user_id, patient_id, note_id, action) values (%s,%s,%s,%s)",
                     (user_id, patient_id, note_id, action))
        conn.commit()


def list_access(user_id, patient_id, limit=100):
    with connection() as conn:
        rows = conn.execute("""select action, note_id, created_at from access_log
                               where user_id = %s and patient_id = %s order by created_at desc limit %s""",
                            (user_id, patient_id, limit)).fetchall()
    return [{"action": r[0], "note_id": r[1], "at": r[2].isoformat()} for r in rows]
