-- Gravação da consulta. O ÁUDIO NUNCA É GUARDADO: cada trecho vai da página para a transcrição e só o texto
-- fica aqui. A transcrição faz parte do prontuário (guarda de 20 anos, Lei 13.787/2018): nunca entra na limpeza
-- de retenção. Apagar uma transcrição fica no registro de acessos.

create table if not exists recordings (
  id          uuid primary key,                       -- criado na página (rec_id): o mesmo em todas as tentativas de envio
  user_id     uuid not null references users(id) on delete cascade,
  patient_id  bigint not null references patients(id) on delete cascade,
  event_id    text,                                   -- consulta da agenda (se houver)
  note_id     bigint references clinical_notes(id) on delete set null,   -- evolução gerada a partir dela
  status      text not null default 'gravando' check (status in ('gravando', 'gerada')),
  consent_at  timestamptz not null,                   -- quando o médico marcou "o paciente autorizou a gravação"
  seconds     real not null default 0,                -- até onde já foi transcrito (s)
  scribe      jsonb,                                  -- última geração: versão do prompt, modelo, contagem dos pontos (sem texto)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists recordings_event_idx on recordings (user_id, patient_id, event_id);
create index if not exists recordings_note_idx on recordings (user_id, note_id);

create table if not exists recording_segments (
  rec_id      uuid not null references recordings(id) on delete cascade,
  seq         integer not null check (seq > 0),
  at_s        real not null,                          -- início do trecho na gravação (s)
  dur_s       real not null,
  text        text not null,
  duvidas     jsonb not null default '[]'::jsonb,     -- palavras ouvidas com pouca certeza
  created_at  timestamptz not null default now(),
  primary key (rec_id, seq)                           -- reenvio do mesmo trecho não duplica (nem cobra de novo)
);

create index if not exists recording_segments_day_idx on recording_segments (created_at);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table recordings enable row level security;
alter table recording_segments enable row level security;
