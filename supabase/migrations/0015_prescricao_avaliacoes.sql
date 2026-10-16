-- Prescrições, fase 3.
-- 1) "Útil / não útil" nas possíveis prescrições da IA: para o médico revisor medir a qualidade das sugestões por
--    versão do prompt e do modelo. Uma avaliação por sugestão (mesma versão da IA, ação e remédio); desmarcar apaga.
--    Guarda só a sugestão (sem o perfil): o resumo para o revisor sai sem médico e sem paciente.
-- 2) O papel da receita do médico (A4 ou A5), em Configurações.

create table if not exists prescricao_avaliacoes (
  id          bigserial primary key,
  user_id     uuid not null references users(id) on delete cascade,
  patient_id  bigint not null references patients(id) on delete cascade,
  ia          text not null,                    -- versão do prompt / modelo que fez a sugestão
  acao        text not null check (acao in ('manter', 'ajustar', 'iniciar', 'suspender')),
  nome        text not null,
  dose        text,
  posologia   text,
  motivo      text,
  fonte       text,
  util        boolean not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (user_id, patient_id, ia, acao, nome)
);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table prescricao_avaliacoes enable row level security;

alter table users add column if not exists receita_papel text check (receita_papel in ('A4', 'A5'));
