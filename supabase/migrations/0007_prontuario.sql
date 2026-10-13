-- Prontuário completo: cadastro do paciente, resumo clínico, evolução estruturada,
-- finalização com adendos e registro de acessos (LGPD / CFM).
-- Tudo acessado só pelo servidor (conexão direta); RLS ligado e sem políticas.

-- 1) Cadastro: identificação (separa homônimos) e resumo clínico fixo do paciente
alter table patients add column if not exists birth_date  date;
alter table patients add column if not exists sex         text check (sex in ('F', 'M', 'O'));
alter table patients add column if not exists cpf         text;            -- só dígitos (opcional)
alter table patients add column if not exists phone       text;
alter table patients add column if not exists allergies   text not null default '';   -- um item por linha
alter table patients add column if not exists problems    text not null default '';
alter table patients add column if not exists medications text not null default '';

-- homônimos passam a ser permitidos: o paciente é identificado pelo id (nome + nascimento na tela)
alter table patients drop constraint if exists patients_user_id_patient_key_key;
create index if not exists patients_user_key_idx on patients (user_id, patient_key);

-- 2) Evolução estruturada (SOAP, sinais vitais, CID-10) e finalização (registro imutável)
alter table clinical_notes add column if not exists data       jsonb;
alter table clinical_notes add column if not exists signed_at  timestamptz;

-- adendos: correções/complementos de uma evolução finalizada (nunca editados)
create table if not exists note_addenda (
  id          bigserial primary key,
  note_id     bigint not null references clinical_notes(id) on delete restrict,
  user_id     uuid not null references users(id) on delete cascade,
  content     text not null,
  created_at  timestamptz not null default now()
);
create index if not exists note_addenda_note_idx on note_addenda (note_id, created_at);
alter table note_addenda enable row level security;

-- 3) Registro de acessos ao prontuário (quem viu/alterou o quê e quando)
create table if not exists access_log (
  id          bigserial primary key,
  user_id     uuid not null references users(id) on delete cascade,
  patient_id  bigint references patients(id) on delete set null,
  note_id     bigint references clinical_notes(id) on delete set null,
  action      text not null,     -- view, note_edit, note_finalize, addendum, patient_create, patient_update, export...
  created_at  timestamptz not null default now()
);
create index if not exists access_log_patient_idx on access_log (user_id, patient_id, created_at desc);
alter table access_log enable row level security;
