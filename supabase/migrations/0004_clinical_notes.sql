-- Prontuário: anotações clínicas (evolução) por paciente, ligadas à consulta do calendário.
-- Dado de saúde (LGPD, dado sensível): só o servidor acessa (conexão direta); RLS ligado e
-- sem políticas bloqueia a API REST pública do Supabase para esta tabela.
create table if not exists clinical_notes (
  id            bigserial primary key,
  user_id       uuid not null references users(id) on delete cascade,
  patient_key   text not null,                 -- nome normalizado (minúsculas, sem acento)
  patient_name  text not null,
  event_id      text,                          -- id do evento no calendário (uma nota por consulta)
  event_title   text,
  event_start   timestamptz,
  content       text not null default '',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create unique index if not exists clinical_notes_event_uq
  on clinical_notes (user_id, event_id) where event_id is not null;
create index if not exists clinical_notes_patient_idx
  on clinical_notes (user_id, patient_key, event_start desc);

alter table clinical_notes enable row level security;
