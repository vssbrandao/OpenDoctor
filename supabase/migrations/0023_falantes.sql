-- Quem fala em cada fala da transcrição da gravação (decisão de 13/11/2026; docs/falante-contrato.md). Depois de cada
-- trecho transcrito, um modelo barato lê o texto JÁ MASCARADO (scribe.mask) e diz onde cada fala termina e quem fala;
-- o servidor corta o texto ORIGINAL nas mesmas frases (nunca reescreve). Cada item de falas:
--   {"q": "m"|"p"|"a", "t": "<texto exato da fala>", "at": <início estimado em s, no relógio da gravação>, "manual": true?}
-- Vazia = trecho sem rótulo (como antes; também quando o rotulador falha). Faz parte da transcrição (prontuário,
-- 20 anos): não entra na limpeza. O app funciona sem esta migração (db.tem_falas): os trechos seguem sem rótulo.
-- Aditiva e idempotente; recording_segments já tem o RLS ligado (0013) e continua ligado.
alter table recording_segments add column if not exists falas jsonb not null default '[]'::jsonb;
alter table recording_segments enable row level security;
