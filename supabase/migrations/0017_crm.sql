-- Só médicos criam conta: o CRM é conferido no cadastro (docs/cadastro-crm.md).
-- crm_status: NULL = conta anterior a esta regra (continua como sempre); 'pendente' = esperando a aprovação à mão
-- (sem a chave do CFM, ou o CFM fora do ar); 'verificado'; 'recusado'. Enquanto não é 'verificado', a conta entra mas
-- não usa o app. crm_fonte: quem decidiu — 'cfm' (web service oficial) ou 'manual' (aprovação na página de cadastros).
-- O CPF e a data de nascimento vão só ao CFM e não ficam guardados em lugar nenhum.
-- users.crm, crm_uf e especialidade já existem (0014).
alter table users add column if not exists crm_status        text check (crm_status in ('pendente', 'verificado', 'recusado'));
alter table users add column if not exists crm_fonte         text check (crm_fonte in ('cfm', 'manual'));
alter table users add column if not exists crm_situacao      text;           -- situação no CFM (1 letra; 'A' = regular)
alter table users add column if not exists crm_verificado_em timestamptz;    -- quando foi conferido (CFM ou à mão)
alter table users add column if not exists crm_pedido_em     timestamptz;    -- quando o cadastro pediu a conferência

-- a lista de cadastros pendentes e a conferência de CRM repetido
create index if not exists users_crm_pendente_idx on users (crm_pedido_em) where crm_status = 'pendente';
create index if not exists users_crm_idx on users (crm, crm_uf) where crm is not null;
