-- Limite de conferências no CFM que vale entre processos e para qualquer IP (docs/cadastro-crm.md).
-- O Validar diz se um CPF e uma data de nascimento são do médico de um CRM: sem limite por CRM, o cadastro (público)
-- viraria um jeito de descobrir a data de nascimento de um médico trocando de IP. Cada linha é uma conferência:
--   chave 'crm:UF:NUMERO'  conferência de um cadastro com esse CRM (no máximo algumas por dia; passou, fica pendente)
--   chave 'conf:<id>'      CPF/nascimento que não bateram na confirmação de uma conta aprovada à mão
-- Nada de CPF, nascimento ou nome. Limpeza diária: 2 dias (db.RETENTION).
create table if not exists cfm_tentativas (
  id         bigserial primary key,
  chave      text not null,
  created_at timestamptz not null default now()
);
alter table cfm_tentativas enable row level security;

create index if not exists cfm_tentativas_chave_idx on cfm_tentativas (chave, created_at);
