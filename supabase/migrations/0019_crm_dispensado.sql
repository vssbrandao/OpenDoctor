-- Conta aprovada à mão (crm_fonte = 'manual') que um administrador liberou sem a confirmação no CFM (docs/cadastro-crm.md).
-- Com a chave do CFM, a conta aprovada à mão confirma o CPF e o nascimento no próximo login; se o Validar insiste em
-- "false" (dado digitado errado na aprovação, cadastro do CFM divergente), o médico fica preso nesse passo. Na página de
-- cadastros, "Liberar sem confirmar" grava aqui quando foi liberada: a conta nunca mais é pedida a confirmar e as
-- sessões abertas deixam de ser barradas. NULL = não liberada (o caso de todas as outras contas).
alter table users add column if not exists crm_dispensado_em timestamptz;
