-- Exames anexados ao prontuário (PDF ou imagem do laudo). Fazem parte do prontuário: nunca entram na
-- limpeza de retenção. O arquivo fica no próprio banco (bytea, até 10 MB); só o servidor acessa.

create table if not exists patient_files (
  id          bigserial primary key,
  user_id     uuid not null references users(id) on delete cascade,
  patient_id  bigint not null references patients(id) on delete cascade,
  name        text not null,                  -- nome do arquivo como veio
  mime        text not null,                  -- conferido pelo conteúdo: pdf | jpeg | png | webp
  size        integer not null,
  data        bytea not null,
  created_at  timestamptz not null default now()
);

create index if not exists patient_files_patient_idx on patient_files (user_id, patient_id, created_at desc);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table patient_files enable row level security;
