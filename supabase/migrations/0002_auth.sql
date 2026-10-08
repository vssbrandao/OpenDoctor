-- Fase B: login por usuário (Google) + tokens de calendário por usuário.
-- Substitui o store único em arquivo (.integrations.json), que é efêmero no Render.

create extension if not exists pgcrypto;

-- usuários do app (identidade = conta Google usada no login)
create table if not exists users (
  id          uuid primary key default gen_random_uuid(),
  email       text unique not null,
  name        text,
  picture     text,
  google_sub  text unique,
  created_at  timestamptz not null default now(),
  last_login  timestamptz not null default now()
);

-- tokens OAuth de calendário, um por (usuário, provedor)
create table if not exists oauth_tokens (
  user_id        uuid not null references users(id) on delete cascade,
  provider       text not null,                 -- 'google' | 'microsoft'
  access_token   text not null,
  refresh_token  text,
  expires_at     timestamptz,
  scope          text,
  account_email  text,
  updated_at     timestamptz not null default now(),
  primary key (user_id, provider)
);

create index if not exists oauth_tokens_user_idx on oauth_tokens (user_id);
