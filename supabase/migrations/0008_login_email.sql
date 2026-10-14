-- Login por e-mail com código de 6 dígitos (sem senha) + registro do aceite dos termos.
-- O código nunca é guardado: só o HMAC (email + código) com o SESSION_SECRET do servidor.

create table if not exists login_codes (
  id          bigserial primary key,
  email       text not null,                  -- minúsculas
  code_hash   text not null,
  expires_at  timestamptz not null,
  attempts    int not null default 0,
  used_at     timestamptz,                    -- usado ou substituído por um código novo
  created_at  timestamptz not null default now()
);

create index if not exists login_codes_email_idx on login_codes (email, created_at desc);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table login_codes enable row level security;

-- cadastro por e-mail: quando o médico aceitou os Termos e a Política de Privacidade
alter table users add column if not exists terms_accepted_at timestamptz;
