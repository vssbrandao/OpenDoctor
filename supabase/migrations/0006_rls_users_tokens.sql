-- RLS nas tabelas de login e tokens do calendário (as demais já tinham).
-- O servidor conecta direto como "postgres" (dono, BYPASSRLS) e continua acessando normalmente;
-- RLS ligado e sem políticas bloqueia a API REST pública do Supabase (chave anon/authenticated)
-- para e-mails dos médicos e tokens OAuth do Google/Microsoft.
alter table users enable row level security;
alter table oauth_tokens enable row level security;
