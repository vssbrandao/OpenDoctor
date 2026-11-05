-- Conta excluída pelo médico (Perfil → Excluir conta, confirmando o e-mail; docs/cadastro-crm.md). A linha não é apagada:
-- as tabelas do prontuário apontam para users com on delete cascade, e prontuários, pacientes, receitas, gravações, exames
-- e o registro de acessos ficam pelo prazo legal (Lei 13.787/2018, 20 anos), sem acesso pelo app. O e-mail e a conta
-- Google saem da linha (vão para as colunas abaixo; no lugar do e-mail fica 'excluida:<id>'), e o mesmo médico pode criar
-- uma conta nova, vazia. NULL em excluida_em = conta ativa (todas as outras). Só colunas novas em users, que já tem RLS
-- (0006). O app funciona sem esta migração (db.tem_exclusao): só a exclusão espera por ela.
alter table users add column if not exists excluida_em timestamptz;
alter table users add column if not exists email_excluido text;
alter table users add column if not exists google_sub_excluido text;
