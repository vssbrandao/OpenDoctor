-- Receitas (aba Prescrições). Rascunho até o médico emitir; emitida não muda mais (é documento do prontuário, guarda
-- de 20 anos, Lei 13.787/2018 — nunca entra na limpeza de retenção). Cancelar não apaga: fica com o motivo e a hora.
-- Uma consulta pode ter várias receitas (simples, controle especial, antimicrobiano); renovação sem consulta não tem
-- evolução (note_id nulo).

create table if not exists receitas (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references users(id) on delete cascade,
  patient_id          bigint not null references patients(id) on delete cascade,
  note_id             bigint references clinical_notes(id) on delete set null,   -- evolução da consulta (se houver)
  event_id            text,                                                      -- consulta da agenda (se houver)
  tipo                text not null default 'simples' check (tipo in ('simples', 'especial', 'antimicrobiano')),
  status              text not null default 'rascunho' check (status in ('rascunho', 'emitida', 'cancelada')),
  itens               jsonb not null default '[]'::jsonb,   -- [{nome, dose, posologia, quantidade, via, continuo, origem, fonte, ia}]
  emitida_em          timestamptz,
  cancelada_em        timestamptz,
  motivo_cancelamento text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create index if not exists receitas_paciente_idx on receitas (user_id, patient_id, created_at desc);
create index if not exists receitas_nota_idx on receitas (user_id, note_id);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table receitas enable row level security;

-- identificação do médico no cabeçalho da receita (Configurações)
alter table users add column if not exists crm                  text;
alter table users add column if not exists crm_uf               text;
alter table users add column if not exists especialidade        text;
alter table users add column if not exists consultorio_endereco text;
alter table users add column if not exists consultorio_telefone text;
