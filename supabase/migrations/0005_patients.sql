-- Cadastro de pacientes do médico, ligado ao prontuário.
-- O campo "Paciente" da agenda escolhe um existente ou cria um novo; o evento guarda o id do
-- paciente (Google: extendedProperties.private.od_patient_id) e as anotações do prontuário
-- apontam para o paciente (clinical_notes.patient_id).
-- Dado pessoal de saúde (LGPD): só o servidor acessa (conexão direta); RLS ligado e sem
-- políticas bloqueia a API REST pública do Supabase para esta tabela.
create table if not exists patients (
  id            bigserial primary key,
  user_id       uuid not null references users(id) on delete cascade,
  patient_key   text not null,                 -- nome normalizado (minúsculas, sem acento)
  name          text not null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (user_id, patient_key)
);

alter table patients enable row level security;

-- prontuário ligado ao paciente
alter table clinical_notes add column if not exists patient_id bigint references patients(id) on delete set null;
create index if not exists clinical_notes_patient_id_idx
  on clinical_notes (user_id, patient_id, event_start desc);

-- quem já tem prontuário vira paciente cadastrado, e as anotações passam a apontar para ele
insert into patients (user_id, patient_key, name)
select distinct on (user_id, patient_key) user_id, patient_key, patient_name
  from clinical_notes
 order by user_id, patient_key, updated_at desc
on conflict (user_id, patient_key) do nothing;

update clinical_notes n set patient_id = p.id
  from patients p
 where n.patient_id is null and p.user_id = n.user_id and p.patient_key = n.patient_key;
