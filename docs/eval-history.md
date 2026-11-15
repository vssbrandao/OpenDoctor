# Histórico de eval

| data | modelo | prompt | recall@6 | 1º acerto | recusa_acc | recusa_indevida | fidelidade | cobertura | lat_p50(s) | lat_p95(s) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-07 13:35 | gpt-4o-mini | clinical_answer.v1 | 1.0 | 0.667 | 1.0 | 0.0 | 0.917 | 0.917 | 5.88 | 8.8 |
| 2026-10-07 13:39 | gpt-4o-mini | clinical_answer.v1 | 1.0 | 0.667 | 1.0 | 0.0 | 0.917 | 0.917 | 2.44 | 5.72 |

## A partir de 10/10/2026 — eval sobre o pipeline de produção (/ask)

Mudanças de método: o eval passou a rodar o mesmo `_ask_stream` do /ask (planejamento, busca em inglês, PubMed ao vivo, corte de relevância, checagem de fidelidade). Perguntas clínicas devem SEMPRE ser respondidas; a coluna antes chamada recusa_acc agora é a acurácia em fora-de-escopo. A 1ª linha abaixo ainda tinha um falso positivo da checagem de fidelidade (corrigido na 2ª).

| data | modelo | prompt | recall@6 | 1º acerto | fora_de_escopo | recusa_indevida | fidelidade | cobertura | lat_total_p50(s) | lat_total_p95(s) | extras |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-10 17:17 | gpt-4o | clinical_answer.v3 | 1.0 | 0.833 | 1.0 | 0.0 | 0.9 | 1.0 | 7.56 | 10.84 | calc=1.0 sem_fonte=2.8 |
| 2026-10-10 17:19 | gpt-4o | clinical_answer.v3 | 1.0 | 1.0 | 1.0 | 0.0 | 0.9 | 1.0 | 7.67 | 10.54 | calc=1.0 sem_fonte=2 |
| 2026-10-10 18:20 | gpt-5.5 | clinical_answer.v3 | 1.0 | 1.0 | 1.0 | 0.0 | 0.91 | 0.995 | 27.39 | 38.07 | calc=1.0 sem_fonte=8.52 rec_prec=0.82 rec_n=4.26 |
| 2026-10-10 18:44 | gpt-5.5 | clinical_answer.v3 | 1.0 | 1.0 | 1.0 | 0.167 | 0.929 | 1.0 | 23.14 | 32.65 | calc=1.0 sem_fonte=6.57 rec_prec=0.73 rec_n=4.66 |

Notas das rodadas amplas (44 perguntas, 20 especialidades, gpt-5.5):
- penúltima linha: juiz via só 1.500 caracteres de cada trecho → fidelidade SUBESTIMADA (reavaliados com texto completo, 4 de 6 casos 'infiéis' eram fiéis).
- última linha: INVÁLIDA para recusa_indevida — as 7 últimas perguntas falharam por 'no credits remaining' na OpenAI (429), não por recusa do assistente. Demais métricas calculadas sobre as 35 respostas obtidas.

## 15/11/2026 — comparação com o ChatGPT (`scripts/compara_respostas.py`)

10 perguntas de prontuário (dados fictícios, sem nome; a 1ª é a do teste com o ChatGPT), fluxo real do /ask. Notas de 0 a 10
dadas por revisores clínicos (agentes Claude), com a resposta do ChatGPT como padrão; variam ~0,5 entre rodadas.

| versão | o que mudou | nota | 1ª frase | total |
|---|---|---|---|---|
| v3 (antes) | esforço low, verbosidade low, 2000 tokens | 6,1 | ~14 s | ~38 s |
| v4 | estrutura do ChatGPT; esforço/verbosidade medium, 5000 tokens | 7,2–7,5 | ~73 s | ~122 s |
| v5 | + diretrizes brasileiras na busca (em português), valores de referência brasileiros conferidos nos PDFs, o que não pode faltar, "DADOS CALCULADOS" (IMC, KDIGO, potássio, INR, estatina/LDL basal, sulfonilureia, betabloqueador), citações enxutas; esforço/verbosidade low, 4500 tokens | 8,0 (GPT 7,9) | ~21 s | ~58 s |

- Esforço medium com o prompt v5 e 3500 tokens: o raciocínio gastou o limite (respostas vazias ou cortadas) e a 1ª frase
  seguiu em ~85 s — descartado.
- Diretrizes no corpus (`scripts/ingest_diretrizes.py`): SBC Hipertensão 2025, SBC Dislipidemias 2025, PCDT HAS, DM2 e DRC
  (903 trechos). Na busca principal (pergunta em inglês) elas quase nunca venciam: entraram em 3 de 10 respostas; com a
  busca própria em português (`search.br_guidelines`), em 10 de 10.
- Os valores de referência do prompt (regras 2d–2g) foram conferidos nos PDFs por três revisores; dois "erros" apontados
  por juízes estavam certos na SBC 2025 (idoso frágil: "até o menor valor tolerado"; ICFEr com HA: meta <130/80).
