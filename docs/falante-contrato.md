# Quem fala em cada fala da transcrição: contrato (13/11/2026)

Decisão do usuário (13/11/2026): a transcrição real mostra **Médico**, **Paciente** ou **Acompanhante** em cada fala.
Caminho escolhido: **pelo texto**. O transcritor (`gpt-transcribe`) não muda. Depois de cada trecho transcrito, um modelo
barato (`config.OPENAI_FALANTE_MODEL`, padrão `gpt-5.4-mini`) lê o texto **já mascarado** (`scribe.mask`) e diz onde cada
fala termina e quem fala. Ele nunca reescreve o texto. Descartados: o `gpt-4o-transcribe-diarize` (desliga em
26/02/2027, perde as dúvidas e o contexto, manda amostra de voz) e os dois juntos. A evolução **continua lendo o texto
sem rótulo** nesta fase; usar os rótulos na evolução só depois da avaliação mostrar que acertam.

## Banco — `supabase/migrations/0023_falantes.sql`

`alter table recording_segments add column if not exists falas jsonb not null default '[]'::jsonb;` (RLS já ligado na 0013).
`falas` = lista de `{"q": "m"|"p"|"a", "t": "<texto exato da fala>", "at": <início estimado em s, no relógio da gravação>, "manual": true?}`.
Vazia = sem rótulo (como hoje). Código tolera banco sem a 0023 (`db.tem_falas`, igual a `tem_audio`).

## Rotulador — `app/falante.py` + `app/data/falante_prompt.txt`

- Entrada: o texto do trecho **mascarado** (`scribe.mask(texto, nome)`), dividido pelo servidor em frases numeradas, e
  o fim do trecho anterior com os rótulos dele (mascarado), para manter a continuidade.
- Saída do modelo (JSON): `[{"ate": <índice da última frase da fala>, "q": "m"|"p"|"a"}, ...]`, cobrindo todas as frases.
- O servidor monta as falas cortando o **texto original** (não o mascarado) nas mesmas frases e confere que juntar as
  falas dá exatamente o texto. Qualquer erro (JSON ruim, índices fora, cobertura incompleta, falha de rede, sem chave)
  → `falas = []` e o trecho segue sem rótulo. Nunca derruba a transcrição.
- O minuto de cada fala: o `at` do trecho + a proporção de caracteres antes dela × `dur` do trecho.
- Log só com números. Mesmo provedor (OpenAI), só texto mascarado: o mesmo tipo de dado que a evolução já manda.

## Rotas

- `/prontuario/transcribe`: depois do `stt`, chama o rotulador (com `asyncio.wait_for`, teto de 8 s) e grava `falas`
  junto do trecho. A resposta ganha `"falas": [...]` (também no "repetido").
- `/prontuario/recordings/state`: cada trecho ganha `falas`.
- `POST /prontuario/recordings/fala` (nova): `{patient_id, rec_id, seq, i, q}` troca o rótulo da fala `i` à mão
  (`manual: true`); filtra por `user_id` e paciente; `q` em `m|p|a`; registra em `access_log` como edição da gravação.

## Tela (`web/opendoctor-agenda.html`)

- Transcrição ao vivo (`rrTx`), a do cartão da lista (`histTx`) e a do histórico: uma linha por fala, com o rótulo
  ("Médico", "Paciente", "Acompanhante") e o minuto, como a demonstração (`recU`). Trecho sem `falas`: como hoje.
- Clicar no rótulo abre as três opções e chama a rota nova.
- As palavras ouvidas com dúvida continuam marcadas dentro de cada fala.

## Avaliação (gasta crédito, aprovada pelo usuário até ~US$ 2)

`python -m scripts.falante_eval`: roda o rotulador sobre o texto de referência dos casos em `evals/scribe/casos/` (sem
transcrição, só texto), compara com o falante de referência e escreve o relatório em `evals/scribe/relatorios/`.
