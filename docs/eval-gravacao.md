# Histórico da avaliação da gravação

Uma linha por rodada de `python -m app.scribe_eval` (31 consultas fictícias, voz sintética). Gasto = o que a rodada pagou à OpenAI (repontuar do cache não paga). Relatórios em `evals/scribe/relatorios/`.

| Data | Transcritor | Evolução | Prompt | Palavras-chave | Dúvida | Critérios | Remédio errado sem aviso / inventado / faltando | Fatos | Sinais | CID | Geração média/máx (s) | Gasto (US$) | Relatório |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.3 | producao | 0.6 | 4/6 | 0 / 2 / 7 | 127/183 | 66/68 | 9/33 | None/None | 0.000 | 2026-10-15-gpt-transcribe-gpt-5.4 |
| 2026-10-15 | gpt-4o-mini-transcribe | gpt-5.4 | 2026-10-15.4 | producao | 0.6 | 5/6 | 0 / 0 / 11 | 157/183 | 61/68 | 26/33 | 12.4/29.0 | 0.000 | 2026-10-15-openai-gpt-4o-mini-transcribe-gpt-5.4 |
| 2026-10-15 | gpt-4o-mini-transcribe | gpt-5.4-mini | 2026-10-15.4 | producao | 0.6 | 5/6 | 0 / 0 / 9 | 163/183 | 65/68 | 24/33 | 3.7/5.3 | 0.000 | 2026-10-15-openai-gpt-4o-mini-transcribe-gpt-5.4-mini |
| 2026-10-15 | gpt-4o-transcribe | gpt-5.4 | 2026-10-15.4 | producao | 0.6 | 5/6 | 0 / 0 / 7 | 144/183 | 46/68 | 24/33 | 10.5/18.9 | 0.000 | 2026-10-15-openai-gpt-4o-transcribe-gpt-5.4 |
| 2026-10-15 | gpt-4o-transcribe | gpt-5.4-mini | 2026-10-15.4 | producao | 0.6 | 5/6 | 0 / 0 / 3 | 138/183 | 47/68 | 25/33 | 3.4/5.0 | 0.000 | 2026-10-15-openai-gpt-4o-transcribe-gpt-5.4-mini |
| 2026-10-15 | gpt-transcribe | gpt-5.4-mini | 2026-10-15.4 | producao | 0.6 | 4/6 | 0 / 1 / 2 | 166/183 | 63/68 | 22/33 | 3.4/5.4 | 0.000 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-mini |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.5 | producao | 0.6 | 5/6 | 0 / 0 / 0 | 173/183 | 68/68 | 24/33 | 10.0/17.3 | 0.440 | 2026-10-15-openai-gpt-transcribe-gpt-5.4 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.6 | exame | 0.6 | 5/6 | 0 / 1 / 2 | 178/183 | 68/68 | 29/33 | 10.5/19.9 | 0.153 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-kw-app-d0.6-p6 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.6 | exame | 0.95 | 5/6 | 0 / 0 / 1 | 173/183 | 68/68 | 26/33 | 13.1/23.3 | 0.442 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-kw-app-d0.95-p6 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.6 | exame | 0.6 | 6/6 | 0 / 0 / 0 | 177/183 | 68/68 | 28/33 | 9.7/16.9 | 0.522 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-kw-app-p6 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.6 | producao | 0.6 | 5/6 | 0 / 1 / 1 | 177/183 | 68/68 | 26/33 | 11.4/23.3 | 0.463 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-p6 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.7 | producao | 0.6 | 5/6 | 0 / 0 / 2 | 173/183 | 68/68 | 28/33 | 9.8/20.5 | 0.449 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-d0.6-p7 |
| 2026-10-15 | gpt-transcribe | gpt-5.4 | 2026-10-15.7 | producao | 0.8 | 6/6 | 0 / 0 / 1 | 176/183 | 68/68 | 26/33 | 10.5/23.6 | 0.466 | 2026-10-15-openai-gpt-transcribe-gpt-5.4-d0.8-p7 |
