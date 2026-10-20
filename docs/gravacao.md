# Gravação e transcrição da consulta

Como funciona a gravação da consulta, do microfone até a evolução revisada: onde está cada parte, os formatos
trocados entre página, servidor e banco, como testar e avaliar, e as decisões tomadas. Privacidade e LGPD estão em
[`ripd-gravacao.md`](ripd-gravacao.md) e na Política (`web/privacy.html`); as regras de segurança, no `CLAUDE.md`.

## O caminho

1. **Microfone → trechos.** Na página, `getUserMedia` alimenta o `AudioWorklet` (`web/rec-worklet.js`), que reduz
   o áudio para 16 kHz mono e manda blocos de 100 ms com o volume. A página junta os blocos em trechos de 15 a 30 s,
   cortados no silêncio e sempre entre blocos inteiros, sem perder amostra.
2. **Trecho → aparelho → servidor.** Cada trecho vira WAV e vai para o IndexedDB **antes** de subir. Se o armazenamento
   falhar, fica na memória (`RR.mem`). Uma fila sobe um trecho por vez para `POST /prontuario/transcribe` e só apaga o
   trecho quando o servidor devolve o texto. O trecho em andamento também é guardado a cada 2 s.
3. **Servidor → transcrição.** O servidor confere login, paciente, autorização e formato, e manda o áudio à OpenAI
   (`app/stt.py`) com o fim do trecho anterior como contexto. Guarda só o texto (`recording_segments`); o áudio é
   descartado.
4. **Finalizar → evolução.** O "Finalizar" do cartão encerra a gravação. `POST /prontuario/scribe` junta os trechos
   da consulta, mascara o texto (`scribe.mask`) e pede a evolução ao modelo (`app/scribe.py`). Confere a resposta sem
   IA (números, remédios, doses, alergias, sinais vitais, CID) e responde em linhas JSON, com progresso e depois o
   resultado.
   Os remédios extraídos (menos os suspensos) entram no rascunho da receita desta consulta como "Da gravação", sem
   repetir (detalhes em `docs/prescricao.md`); a última linha diz quantos (`receita`).
5. **Revisão.** A página preenche os campos vazios da evolução em SOAP, sem apagar o que o médico escreveu, e lista os
   pontos para conferir. O mesmo "Finalizar" do cartão, com a evolução pronta, finaliza (assina). Com pontos abertos,
   pede confirmação. A evolução guarda o rastreio (`data.scribe`) e, ao finalizar, os números da revisão
   (`data.timing.scribe`).

## Onde está cada parte

| Parte | Arquivo | O que tem |
|---|---|---|
| Captura | `web/rec-worklet.js` | 16 kHz, blocos de 100 ms, volume (RMS) |
| Tela e fila | `web/opendoctor-agenda.html`, seção "gravação da consulta" | cartão da aba Consulta (funções `cs*`), demonstração (paciente de exemplo) e gravação real |
| Rotas | `app/server.py` | `transcribe`, `recordings/state`, `scribe`, `DELETE recordings/{id}`, `_scribe_rastreio`, ligação ao salvar a evolução |
| Banco | `app/db.py` (`rec_*`, `_ligar`), `supabase/migrations/0013_scribe.sql` | `recordings`, `recording_segments` |
| Transcrição | `app/stt.py` | chamada, limpeza de frases-fantasma, confiança por palavra (`DUVIDA`) |
| Evolução | `app/scribe.py` | máscara, leitor de números, remédios e alergias, prompt, conferências (`_Conferencia`) |
| Tabelas clínicas | `app/data/` | `remedios.txt`, `doses.tsv`, `composicao.tsv`, `alergias.tsv`, `siglas.txt`, `termos_exame.txt`, `escriba_prompt.txt` |
| Avaliação | `app/scribe_eval.py`, `evals/scribe/` | 31 consultas fictícias, gabaritos, relatórios; histórico em [`eval-gravacao.md`](eval-gravacao.md) |
| Testes | `tests/test_scribe*.py`, `tests/fake_gravacao.py`, `tests/test_db_integration.py`, `tests/e2e/gravacao.mjs` | ver "Testes" |
| Preview local | `scripts/preview_gravacao.py` | rotas de verdade, banco em memória, transcritor e modelo simulados |

As tabelas de `app/data/` ficam fora do código para o médico revisor conferir sem ler Python. Mudou o texto do prompt
(`escriba_prompt.txt`): suba `scribe.PROMPT_VERSION`. Um teste falha até a versão nova ser registrada.

## A tela

A aba Consulta do prontuário é um cartão (`#csCard`, Figma "Consulta", nó 1089:32631) com as abas **Transcrição** e
**SOAP** e um pé (`#prRec`). O que o design não mostra fica abaixo do cartão: microfone, autorização, avisos, etapas,
resumo, pontos para conferir e a confirmação ao finalizar.

- **Abas.** A consulta abre em Transcrição quando dá para gravar (paciente de exemplo ou conta liberada). Nas contas
  sem a gravação, ou com a evolução finalizada, abre em SOAP. Quando a evolução gerada fica pronta, a aba SOAP ganha
  um ponto laranja até ser aberta.
- **Antes de gravar:**
  - o pé tem "Iniciar consulta";
  - abaixo do cartão ficam o microfone (escolher, medidor, "Testar microfone") e a autorização do paciente;
  - sem a autorização marcada, "Iniciar consulta" leva até ela, e a gravação começa ao marcar;
  - nas contas sem a gravação, fora da paciente de exemplo, o botão fica desativado, com um aviso.
- **Gravando:**
  - o pé mostra "Finalizar" acima da barra preta: ondas do volume, o tempo e o botão redondo que pausa e continua
    (também ⌘/Ctrl + Shift + Espaço);
  - as falas aparecem na aba Transcrição: na gravação real, a cada trecho; na demonstração, palavra por palavra;
  - pausada ou interrompida, o mesmo botão redondo continua a gravação;
  - "Finalizar" encerra e gera a evolução. A barra troca as ondas pelo andamento (enviando, gerando). Na gravação real,
    as etapas aparecem abaixo do cartão e, se a geração falhar, o pé mostra "Gerar de novo";
  - na gravação real, fora da aba Consulta, um aviso fixo ("Gravando", "Voltar à consulta") leva de volta a ela.
- **Depois da consulta:**
  - o player aparece em cima do cartão: a trilha, o tempo e o botão que percorre a transcrição. O cursor anda e a fala
    do momento fica em destaque. Tocar numa fala ou na trilha leva o player até ali;
  - na gravação real, o player não tem som: o áudio foi descartado. A demonstração mostra também o botão de som e os
    marcadores no começo de O, A e P;
  - o aviso da IA ("Evolução preenchida pela gravação: revise na aba SOAP", com "Desfazer") e o "Finalizar" flutuam no
    pé, por cima do texto, sem máscara;
  - na gravação real, abaixo do cartão: "Consulta gravada", com "Gravar mais um trecho", e os pontos "Para conferir na
    evolução" ("Ver na transcrição" abre a fala na aba Transcrição).
- **Evolução:**
  - só em SOAP. Um rascunho antigo em texto livre aparece no S;
  - salva sozinha ao parar de digitar. Não há Salvar, "Copiar da última" nem "Finalizar evolução" na tela;
  - abaixo do cartão fica só o status: falha ao salvar, limite de caracteres.
- **Finalizar a evolução:**
  - fora da gravação, o "Finalizar" do pé só aparece com texto na evolução, gerada ou escrita à mão;
  - finaliza (assina) com a confirmação de sempre;
  - com pontos não conferidos ou trechos fora da evolução, pergunta antes, abaixo do cartão ("Finalizar mesmo assim?").
- **Finalizada:**
  - a aba SOAP mostra a evolução assinada direto na tela, sem caixa cinza, com os adendos;
  - o pé some. "Adicionar adendo" flutua no canto direito e abre o campo na aba SOAP, abaixo da assinada;
  - a aba Transcrição mostra a transcrição ou o aviso "Esta consulta não foi gravada". A consulta gravada mantém o player.
- **Peças antigas escondidas.** O cabeçalho antigo (o relógio "Iniciar consulta", `#prVisit`, e Texto livre | SOAP) e os
  botões do pé (`#prSave`, `#prCopyLast`, `#prFinalize`, `#prAddBtn`) ficam num bloco `hidden`, porque o código ainda os
  usa. O "Finalizar" do cartão clica em `#prFinalize`; "Adicionar adendo", em `#prAddBtn`.

## Na página

A seção da gravação tem três partes:
- os **componentes** do cartão (abas, pé, barra com as ondas, player, medidor do microfone);
- a **demonstração**, que roda sempre na paciente de exemplo e nas contas sem a gravação;
- a **gravação real**, que liga quando `/me` devolve `scribe: true`.

`recRender` decide qual delas aparece.

- **Estado.** O bloco de comentário no começo da gravação real descreve cada gravação (`RR.by[k]`, uma por consulta,
  `k = ctx._rk`): as situações (`idle`, `live`, `paused`, `interrupted`, `ending`, `gen`, `fail`, `done`, `saved`,
  `nomic`), os estados de cada trecho e os campos.
- **Cortes** (`SEG`, os mesmos números de `scribe_eval.CORTE`; um teste confere):
  - o trecho tem de 15 a 30 s;
  - corta depois de 3 blocos de silêncio ou, aos 30 s, no bloco mais baixo dos últimos 20;
  - o piso de ruído é o 10º percentil dos últimos 30 s;
  - o limiar é piso × 2,5, entre 0,004 e 0,03;
  - trecho com menos de 2 blocos acima do limiar é silêncio e não sobe.
- **Fila** (`qKick`):
  - sobe um trecho por vez, do mais antigo;
  - sem rede, espera crescente;
  - erro do servidor (5xx, 429, 403): tenta de novo e, depois de 3 falhas, deixa o trecho para depois (até 10 min) e
    segue com os outros;
  - 401: espera entrar de novo;
  - 400, 404, 413 e 415: o trecho fica marcado como recusado e aparece como "fora da evolução".
- **Recuperação** (`rrLoad`): ao abrir a consulta, junta o que o servidor já transcreveu e o que ficou no aparelho.
  - Consulta da agenda: acha a gravação pelo `event_id`.
  - Consulta com evolução: pelo `note_id`.
  - Consulta avulsa ainda sem evolução: pelas gravações "órfãs" do paciente nas últimas 12 h.
  - A última geração volta inteira: evolução, pontos e conferidos.
- **Preencher e gerar de novo** (`rrApply`):
  - o texto da gravação entra nos campos vazios ou abaixo do que já existe;
  - ao gerar de novo, troca campo por campo o texto gerado antes, se continua igual;
  - campo que o médico editou fica como está;
  - "Desfazer" volta ao texto anterior à primeira geração.
- **Microfone:** se o escolhido saiu (fone Bluetooth, USB), usa o padrão do computador. A tela fica acordada enquanto
  grava, inclusive ao voltar para a aba.

## Formatos

**`POST /prontuario/transcribe`**: o corpo é o WAV (16 kHz, mono, 16 bits, até 5 MB e 60 s). Os cabeçalhos são
`X-Patient-Id`, `X-Rec-Id` (UUID criado na página), `X-Seq`, `X-At` (início do trecho, em s), `X-Event-Id`, `X-Note-Id`
e `X-Consent` (ISO: quando a gravação começou, com a autorização do paciente marcada). O nome do paciente nunca vai.
- Mesmo `rec_id` + `seq` já transcrito: devolve o texto guardado sem cobrar.
- Mesmo trecho chegando ao mesmo tempo: o segundo espera o primeiro (`_EM_ANDAMENTO`).
- Teto: 6 h de gravação por médico em 24 h.

**`data.scribe`** (na evolução) e **`recordings.scribe`** (na gravação) usam o mesmo rastreio, definido em
`server._scribe_rastreio`:
- campos: `rec_ids`, `prompt`, `model`, `consent_at`, `generated_at`, `pontos {alto, medio, info}`, `segundos`,
  `gen_s`, `conferidos` e `conf_idx`;
- a página só acrescenta `conferidos` e `conf_idx`;
- `recordings.scribe.saida` guarda a última evolução gerada (`result`), os pontos (`flags`) e a numeração dos trechos
  (`segs`), para a revisão continuar depois de recarregar a página ou noutro dia.

**`data.timing.scribe`** (ao finalizar), só números: `rec_s`, `gen_s`, `review_s`, `fim_s`, `mantido_pct`,
`alto/medio/info`, `conferidos` e `pendentes`.

**Ligação gravação ↔ evolução** (`db._ligar`, a única regra):
- só vale evolução do mesmo médico e do mesmo paciente;
- a gravação ainda sem evolução ganha a que chegar: pelo cabeçalho do trecho, ao salvar a evolução (`rec_ids`) ou ao
  gerar;
- a evolução salva com `data.scribe` passa a ser a das gravações que a geraram.

## Testes

- `python -m pytest tests/ -q`:
  - `test_scribe.py`: máscara, números, remédios, alergia, conferências, e se rótulos e versão do prompt estão em dia;
  - `test_scribe_routes.py`: as rotas, com `tests/fake_gravacao.py`;
  - `test_scribe_eval.py`: gabaritos coerentes, pontuação e cortes iguais aos da página;
  - `test_db_integration.py`: no banco de testes.
- **Ponta a ponta** (Chrome sem tela, microfone sintético), contra o preview:
  ```bash
  .venv/bin/uvicorn scripts.preview_gravacao:app --port 8770
  ```
  ```bash
  node tests/e2e/gravacao.mjs
  ```
  Use `PREVIEW=` se a porta for outra e `SO=3,5` para rodar só alguns cenários. São 16 cenários e cerca de 13 minutos,
  porque grava em tempo real. É obrigatório quando a gravação muda.
- **Preview local** (`/_preview/pr?pid=9003&ev=evA`):
  - pacientes fictícios (9001 Maria Silva, de exemplo; 9003; 9004);
  - botões "Internet" e "IA" para simular falhas;
  - `/_preview/sim`, `/_preview/estado`, `/_preview/reset` para os testes.
  - A limpeza descarta os envios que começaram antes dela.

## Avaliação

```bash
python -m app.scribe_eval --estimar
```
```bash
python -m app.scribe_eval --duvida 0.8 --teto-usd 0.70
```
```bash
python -m app.scribe_eval --calibrar-duvida --teto-usd 0.20
```
```bash
python -m app.scribe_eval --comparar
```

- **O que cada comando faz:**
  - `--estimar`: grátis, só estima o custo;
  - `--duvida 0.8`: GASTA, com teto, e reaproveita a calibragem;
  - `--calibrar-duvida`: mede o limite de dúvida (só a transcrição);
  - `--comparar`: monta a tabela das rodadas do dia.
- **Como mede:** a avaliação usa os mesmos cortes, contexto e palavras-chave da produção.
- **Cache e gasto:** o cache (`evals/scribe/cache/`, fora do git) evita pagar duas vezes. Repontuar do cache não gasta
  e soma ao gasto que o relatório já tinha.
- **Pedir antes:** toda rodada paga precisa do ok do usuário, com o valor.

## Decisões

| Data | Decisão | Por quê |
|---|---|---|
| 15/10/2026 | Transcritor `gpt-transcribe`, evolução `gpt-5.4` | melhor par na avaliação (comparação em `evals/scribe/relatorios/`) |
| 15/10/2026 | Áudio não é guardado; a transcrição fica com o prontuário | privacidade; o prontuário precisa do texto |
| 15/10/2026 | Palavras-chave de exame físico desligadas (`SCRIBE_KW_EXAME`) | acertam termos, mas a dúvida cai de 20% para 6% dos erros |
| 15/10/2026 | Limite de dúvida 0,8 (era 0,6) | marca 40% dos erros do transcritor, contra 14%, com a mesma precisão; custa ~1 ponto a mais por consulta. Confirmar com consultas encenadas |
| 15/10/2026 | Prompt `2026-10-15.7` | passou nos critérios de segurança nos dois limites de dúvida |
| 15/10/2026 | O contexto da transcrição vai sem CPF, telefone e e-mail; o nome falado fica | o áudio já contém o nome; mascarar o nome pode fazer o transcritor escrever "[PACIENTE]" |
| 15/10/2026 | A paciente de exemplo fica sempre com a demonstração | conta liberada continua mostrando o fluxo sem gravar ninguém |
| 19/10/2026 | Aba Consulta no design do Figma "Consulta" (nó 1089:32631): Transcrição \| SOAP, o pé com Iniciar consulta ou a barra, o player depois | pedido do usuário, que desenha a tela no Figma |
| 19/10/2026 | Evolução só em SOAP; sem Salvar, "Copiar da última", "Finalizar evolução" e o relógio "Iniciar consulta" | a evolução salva sozinha; um "Finalizar" só: gravando, encerra e gera; pronta, assina |
| 19/10/2026 | "Adicionar adendo" e o aviso da IA flutuam por cima do texto, sem máscara; a finalizada aparece só na aba SOAP | como no Figma (1090:32797) |
| 19/10/2026 | Na gravação real, o player percorre a transcrição sem som | o áudio não é guardado |

## Pendências

- **Antes de pacientes reais fora da conta do fundador:** DPA da OpenAI, pedido de ZDR e cláusulas-padrão da ANPD.
  Também a revisão jurídica do RIPD, da Política e dos Termos.
- **Validação:** médico revisor para os gabaritos e as regras do prompt, e pelo menos 8 consultas encenadas por pessoas
  (elas também confirmam o limite de dúvida).
- **Lista da CMED:** `scripts/cmed_import.py` está pronto. Baixar a planilha depende de ok.
- **Pontos repetidos:** juntar os pontos que falam do mesmo problema (um nome ouvido com dúvida pode virar até 4).
- **Baixa prioridade, ainda abertos:**
  - microfone Bluetooth antigo a 8 kHz (o worklet não aumenta a taxa);
  - limite de envios por IP numa clínica com vários médicos;
  - o aviso dos 80 minutos depois de recuperar uma gravação;
  - escolher o microfone com a gravação pausada não mostra resposta.
