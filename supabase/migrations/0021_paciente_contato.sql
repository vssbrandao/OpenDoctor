-- Cadastro do paciente: e-mail, particular ou convênio e o plano do convênio, que o médico preenche ao criar o paciente
-- (tela Pacientes → +). Tudo opcional (NULL = não informado); o plano só existe com coverage = 'convenio' (o servidor
-- apaga o plano quando o atendimento é particular). O telefone já existia (0005). Ficam só no cadastro: não vão ao modelo
-- (a gravação e as possíveis prescrições montam o perfil campo a campo, sem estes) nem a log. Só colunas novas em
-- patients, que já tem RLS (0005). O app funciona sem esta migração (db.tem_contato): só o paciente com estes campos
-- espera por ela.
alter table patients add column if not exists email text;
alter table patients add column if not exists coverage text check (coverage in ('particular', 'convenio'));
alter table patients add column if not exists health_plan text;
