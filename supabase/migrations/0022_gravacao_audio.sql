-- Áudio original da gravação da consulta (decisão de 13/11/2026: o player do prontuário toca o som real). Isto muda o
-- que a 0013 dizia ("o áudio nunca é guardado"): a partir daqui o áudio de cada consulta gravada fica guardado por
-- 1 ANO (db.RETENTION, limpeza diária por created_at) e depois some; a transcrição continua no prontuário (20 anos).
-- Cada linha é um pedaço do MediaRecorder (timeslice de 5 s) de uma parte (uma sessão do microfone); os pedaços de uma
-- parte, juntos em ordem a partir de n = 0, formam o arquivo que toca. O áudio sai também com "Apagar transcrição"
-- (cascata de recordings) e com a exclusão da conta (db.excluir_conta). O app funciona sem esta migração
-- (db.tem_audio): a gravação segue só com o texto e o envio do áudio espera por ela.

create table if not exists recording_audio (
  rec_id      uuid not null references recordings(id) on delete cascade,
  part        integer not null check (part >= 0 and part < 1000),    -- uma por sessão do microfone (início, continuar, troca)
  n           integer not null check (n >= 0 and n < 10000),         -- pedaço da parte, em ordem (timeslice de 5 s)
  user_id     uuid not null references users(id) on delete cascade,
  at_s        real not null,                                         -- início da parte no relógio da gravação (s)
  upto_s      real not null,                                         -- até onde vai este pedaço no mesmo relógio (s)
  mime        text not null check (mime in ('audio/webm', 'audio/ogg', 'audio/mp4')),
  size        integer not null,
  data        bytea not null,
  sess        text,                                                  -- sessão do MediaRecorder que gravou a parte (X-Sess)
  created_at  timestamptz not null default now(),
  primary key (rec_id, part, n)                                      -- reenvio do mesmo pedaço não duplica
);
-- o banco de testes já tinha a tabela sem a coluna (a 0022 ainda não foi aplicada em produção): a migração segue
-- idempotente. A sessão separa duas abas que escolheram o mesmo número de parte (docs/audio-contrato.md).
alter table recording_audio add column if not exists sess text;
create index if not exists recording_audio_user_idx on recording_audio (user_id, created_at);
create index if not exists recording_audio_day_idx on recording_audio (created_at);

-- mesma regra das outras tabelas: RLS ligado e sem políticas (só o servidor acessa)
alter table recording_audio enable row level security;
