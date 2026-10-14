-- Login com e-mail e senha (o código por e-mail fica só para confirmar o cadastro e redefinir a senha).
alter table users add column if not exists password_hash   text;                       -- pbkdf2_sha256$iter$salt$hash; null = conta só Google
alter table users add column if not exists session_version int not null default 0;     -- muda ao trocar a senha: derruba as outras sessões
alter table users add column if not exists failed_logins   int not null default 0;     -- senhas erradas seguidas
alter table users add column if not exists locked_until    timestamptz;                 -- bloqueio temporário após erros demais
