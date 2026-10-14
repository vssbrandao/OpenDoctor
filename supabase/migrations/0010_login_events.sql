-- Registro de acessos à conta: cada entrada (e cada senha errada) com data, IP e aparelho.
-- Serve para avisar por e-mail quando a conta entra de um aparelho novo e para investigar acessos.
-- Guardar por pelo menos 6 meses (Marco Civil da Internet, art. 15: registros de acesso a aplicações).

create table if not exists login_events (
  id          bigserial primary key,
  user_id     uuid not null references users(id) on delete cascade,
  event       text not null,                  -- entrou | senha_incorreta | bloqueado
  method      text not null,                  -- senha | google | cadastro | nova_senha
  ip          text,
  user_agent  text,
  device      text,                           -- hash do cookie od_dev (nunca o cookie em si)
  created_at  timestamptz not null default now()
);

create index if not exists login_events_user_idx on login_events (user_id, created_at desc);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table login_events enable row level security;
