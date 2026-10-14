-- RLS das tabelas da base de conhecimento. Em produção já estava ligado (pelo painel do Supabase);
-- esta migração só registra isso no repositório, para um banco recriado do zero nascer igual.
alter table documents enable row level security;
alter table chunks    enable row level security;
