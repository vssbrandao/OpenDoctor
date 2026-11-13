# Áudio guardado da consulta: contrato entre página, servidor e banco (13/11/2026)

Decisão do usuário (13/11/2026): o áudio original de cada consulta gravada passa a ser guardado por **1 ano**
(limpeza diária apaga depois), para o player do prontuário tocar o som real. O texto (transcrição) continua junto do
prontuário (20 anos). Consultas gravadas antes da mudança não têm áudio: o player lê a transcrição com a voz instalada
no computador (`speechSynthesis`, só `localService`; nada sai da máquina). A tela continua sem marca de autorização: o
médico avisa o paciente; muda o texto do aviso e a Política de Privacidade.
A leitura pela OpenAI TTS (testada antes no mesmo dia) foi descartada e não existe no código.

## Banco — `supabase/migrations/0022_gravacao_audio.sql`

```sql
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
  created_at  timestamptz not null default now(),
  primary key (rec_id, part, n)
);
create index if not exists recording_audio_user_idx on recording_audio (user_id, created_at);
create index if not exists recording_audio_day_idx on recording_audio (created_at);
alter table recording_audio enable row level security;
```

- `db.RETENTION["recording_audio"] = "1 year"` (por `created_at`). `recordings`/`recording_segments` nunca entram.
- Apagar a gravação (`rec_delete`, "Apagar transcrição") leva o áudio pela cascata.
- Excluir a conta apaga `recording_audio` do médico (o texto fica pelo prazo legal, como hoje).
- Excluir paciente: gravação com áudio conta como prontuário (bloqueia como `recording_segments`).

## `POST /prontuario/recordings/audio` — um pedaço

- Corpo: os bytes do pedaço (`Content-Type: application/octet-stream`, nunca JSON: força o pre-flight).
- Cabeçalhos: `X-Patient-Id`, `X-Rec-Id` (uuid), `X-Part`, `X-N`, `X-At` (início da parte, s), `X-Upto` (s),
  `X-Event-Id` (opcional). Nunca o nome.
- Ordem: `_auth_or_401` → porteiro da gravação **sem exigir a chave da OpenAI** (`SCRIBE_OFF` → 503, conta sem
  gravação → 403) → paciente do médico (`_outro_paciente` como no transcribe) → `_rate_limited(request, "audio")`
  (480 em 600 s) → tamanho ≤ `MAX_AUDIO_BYTES` (512 KB) pelo `content-length` e pelo stream → teto de 300 MB de áudio
  em 24 h por médico (429).
- **Nunca cria a gravação.** Sem a linha em `recordings` do médico/paciente → 409 `{"error": "gravação ainda não
  começou"}` (a página tenta de novo depois). Para `n > 0`, sem o pedaço `n = 0` da parte → 409 também.
- Tipo: só pelos bytes do pedaço `n = 0` (`1A45DFA3` → `audio/webm`, `OggS` → `audio/ogg`, `ftyp` em `[4:8]` →
  `audio/mp4`; outro → 415). Os `n > 0` herdam o tipo da parte. Nunca do `Content-Type` do navegador.
- Reenvio do mesmo `(rec_id, part, n)` → `{"ok": true, "repetido": true}` (on conflict do nothing).
- Log só com números (`[audio] pedaço p/n: N bytes`).

### Correções da revisão (13/11/2026)

- **Sessão da parte:** coluna `sess text` (na própria 0022, que ainda não foi aplicada em produção). A página gera um
  id aleatório por sessão do MediaRecorder (`[A-Za-z0-9-]{8,64}`) e manda em `X-Sess` (obrigatório; sem ele → 400).
  O `n = 0` grava o `sess`. Se a parte já tem `n = 0` de **outra** sessão, ou se `n > 0` chega com `sess` diferente do
  `n = 0` → 409 `{"error": "parte ocupada", "parte_ocupada": true}`: a página renumera a sessão para uma parte livre.
  "repetido" só quando a linha existente tem o mesmo `sess`.
- **Teto por parte:** 32 MB (`MAX_PART_BYTES`), além do de 24 h; passou → 429 `{"error": …, "teto_parte": true}`. A
  página também troca de parte sozinha a cada 30 min de gravação.
- **Limite de pedidos:** `_rate_limited(request, "audio", key=u["id"])` (por conta, não por IP: clínica atrás de NAT).
- **409 com outro paciente** já traz `other_patient: true` (a página para de mandar aquela gravação).
- `rec_list` filtra `rec_id = any(%s::uuid[])` (usa a PK). `rec_audio` junta com `b"".join` só os contíguos.

## `GET /prontuario/recordings/audio?rec_id=…&part=…` — tocar uma parte

- Só ids na URL. Dono por `user_id`. Junta os pedaços contíguos a partir de `n = 0` (para no primeiro buraco).
- Resposta: os bytes, `media_type` = o `mime` guardado (lista fechada), `Cache-Control: private, no-store`,
  `Content-Disposition: inline`, `Cross-Origin-Resource-Policy: same-origin`. 404 sem áudio.
- `db.log_access(u, "recording_listen", patient_id, dedupe_minutes=10)`.

## `POST /prontuario/recordings/state` — passa a trazer o áudio (metadados)

Cada gravação ganha `"audio": [{"part": 0, "at": 0.0, "upto": 312.4}]` — só as partes com `n = 0`, `upto` = maior
`upto_s` dos pedaços contíguos.

## CSP

`_CSP` ganha `media-src 'self' blob:` (o player busca a parte com `fetch` e toca por `blob:`). `_CSP_SITE` troca esse
`media-src` com `.replace` para incluir `https://videos.pexels.com` (uma diretiva só).

## Página (`web/opendoctor-agenda.html`)

- Um `MediaRecorder` (opus 24 kbps; `audio/webm;codecs=opus`, senão `audio/mp4`, senão `audio/ogg;codecs=opus`) por
  sessão do microfone, ligado quando a gravação fica `live` e parado na pausa/troca de microfone/encerrar.
  `timeslice` de 5 s. Cada pedaço vai ao IndexedDB (store `aud`, banco versão 2) e sobe por uma fila própria; 409 →
  tenta de novo mais tarde; o `idbPurge` de 48 h e o `Clear-Site-Data` do logout valem para o áudio também.
- O áudio não segura a geração da evolução (`rrPending` não conta o áudio).
- Player do cartão da lista: com áudio, busca as partes e toca em sequência (botão de som = mudo); sem áudio, a voz
  do computador lê a transcrição.
- "Apagar transcrição" passa a dizer que o áudio também sai, e limpa o IndexedDB daquele `rec_id`.
