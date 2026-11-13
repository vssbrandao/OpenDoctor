# RIPD — Gravação e transcrição da consulta

Relatório de Impacto à Proteção de Dados Pessoais (LGPD, art. 38) da função "gravar a consulta" do
OpenDoctor. **Rascunho técnico** (15/10/2026, revisto em 13/11/2026), para revisão jurídica antes do primeiro paciente real fora
da conta do fundador. Os itens marcados **[pendente]** precisam de decisão ou documento antes disso.

## 1. O que a função faz

O médico grava a consulta no navegador. O áudio vira texto (transcrição) e o texto vira um **rascunho** da
evolução em SOAP, que o médico revisa, corrige e assina. A função **documenta** o que foi dito:
não sugere diagnóstico, exame nem conduta (ver item 8).

- Liga só para contas liberadas (`SCRIBE_EMAILS` / `SCRIBE_ALL` no servidor); `SCRIBE_OFF=1` desliga para
  todos na hora.
- Desde 20/10/2026 (pedido do usuário) não há mais a marca "O paciente autorizou a gravação desta consulta" na tela:
  "Iniciar consulta" grava direto. Avisar o paciente e pedir a autorização antes de tocar no botão fica com o médico;
  a hora em que a gravação começou fica registrada. **[pendente]** revisão jurídica desta mudança.
- Desde 13/11/2026 (decisão do usuário) o **áudio original** de cada consulta gravada fica guardado por **1 ano**
  (tabela `recording_audio`), para o médico ouvir a consulta de novo no player do prontuário; depois a limpeza diária
  o apaga. Antes disso o áudio não era guardado: as consultas gravadas antes da mudança não têm som, e o player lê a
  transcrição com a voz instalada no computador (`speechSynthesis`, só vozes locais; nada sai da máquina). O desenho
  está em `docs/audio-contrato.md`. Continua sem marca de autorização na tela: o médico avisa o paciente de que a
  consulta fica **gravada** (e não só transcrita).

## 2. Dados tratados

| Dado | Origem | Onde fica | Por quanto tempo |
|---|---|---|---|
| Áudio para a transcrição (WAV 16 kHz, voz do médico, do paciente e de acompanhantes) | microfone do computador do médico | trechos no navegador (IndexedDB) até o servidor confirmar; memória do servidor durante a transcrição | navegador: até a confirmação; o que não subir em 48 h é apagado quando o OpenDoctor é aberto de novo nesse computador (com a página fechada, o navegador não tem como apagar); apagado ao sair da conta; servidor: não é gravado |
| Áudio original da consulta (webm/opus, mp4 ou ogg; o mesmo som, inclusive os silêncios) | microfone do computador do médico (`MediaRecorder`) | pedaços de 5 s no navegador (IndexedDB) até o servidor confirmar; banco do OpenDoctor (`recording_audio`, Supabase, Canadá) | navegador: como o WAV; banco: **1 ano** a partir do envio (limpeza diária), ou até "Apagar transcrição" ou a exclusão da conta, o que vier antes |
| Texto de cada trecho (transcrição), com o minuto e as palavras ouvidas com dúvida | transcrição (OpenAI) | banco do OpenDoctor (`recording_segments`) | junto do prontuário: mínimo 20 anos (Lei 13.787/2018) |
| Último rascunho gerado (texto da evolução) e os pontos para conferir, para a revisão continuar depois de recarregar ou noutro dia | servidor | `recordings.scribe` (`saida`) | junto da transcrição; sai com "Apagar transcrição" |
| Data e hora em que a gravação começou (`consent_at`), duração, situação | página | `recordings` | idem |
| Rastreio da evolução gerada (versão do prompt, modelo, contagem de pontos conferidos) — sem texto | servidor | `clinical_notes.data.scribe` | idem |
| Métricas da revisão (segundos, %, contagens) — sem texto | página, ao finalizar | `clinical_notes.data.timing` | idem |

Categorias: **dados pessoais sensíveis de saúde** (LGPD, art. 5º, II) do paciente; dados de terceiros que
falem na consulta; voz (dado biométrico em potencial): o OpenDoctor guarda a gravação da voz por 1 ano, mas não extrai nem guarda
características dela e não identifica ninguém pela voz.

## 3. Fluxo

1. Navegador: `getUserMedia` → AudioWorklet (`web/rec-worklet.js`) → trechos de 15–30 s cortados no silêncio
   → WAV 16 kHz → IndexedDB (banco por médico) → fila de envio.
2. `POST /prontuario/transcribe` (login, dono do paciente, hora do início obrigatória, formato conferido) →
   `stt.atranscribe` → OpenAI `/v1/audio/transcriptions` → só o **texto** é gravado; o navegador apaga o trecho.
   Junto do áudio vão, como contexto, o fim do texto do trecho anterior — sem CPF, CNS, telefone e e-mail
   (`scribe.mask_docs`), mas com o nome falado, que o próprio áudio já contém — e os nomes de remédios, problemas
   e alergias do cadastro (palavras-chave). O mesmo trecho chegando duas vezes ao mesmo tempo é transcrito uma vez.
   Esse WAV não é guardado no servidor.
   Quem fala (desde 13/11/2026): o texto do trecho, **mascarado** (`scribe.mask`), e o fim do trecho anterior com os
   rótulos (também mascarado) vão ao modelo barato da OpenAI (`/v1/chat/completions`, `app/falante.py`), que devolve só
   onde cada fala termina e se é Médico, Paciente ou Acompanhante. O texto não é reescrito; os rótulos ficam em
   `recording_segments.falas` e o médico pode trocá-los (registrado no registro de acessos). Nenhuma voz ou amostra
   de voz é usada para isso.
3. Ao mesmo tempo, um `MediaRecorder` no mesmo microfone grava o som original (opus 24 kbps), uma parte por sessão
   do microfone (início, continuar, troca), em pedaços de 5 s → IndexedDB → fila própria →
   `POST /prontuario/recordings/audio` (login, conta com a gravação, dono do paciente, tipo conferido pelos bytes,
   tamanho, teto de 32 MB por parte e teto diário, limite de pedidos por conta; nunca cria a gravação) →
   `recording_audio`. A página troca de parte sozinha a cada 30 min de gravação. O áudio não vai a nenhum outro serviço.
   O player busca cada parte por `GET /prontuario/recordings/audio` (só ids na URL, dono pelo médico, sem cache) e
   toca no navegador; as audições ficam no registro de acessos (`recording_listen`), e as do mesmo paciente em
   10 minutos viram uma linha só.
4. `POST /prontuario/scribe` → texto de todos os trechos da consulta, **mascarado** (`scribe.mask`: nome →
   `[PACIENTE]`, CPF, CNS, telefone, e-mail), + cadastro (problemas, remédios, alergias, idade, sexo) + evolução
   anterior do mesmo paciente (mascarada) + perfil de escrita do médico (só estatísticas e siglas de uma lista
   fixa) → OpenAI `/v1/chat/completions` → conferências sem IA (`scribe.check`) → rascunho + pontos para conferir.
5. Médico revisa e finaliza; a evolução registra "Transcrição automática (IA)". Desde 13/11/2026 (pedido do usuário)
   os pontos para conferir não aparecem mais na tela: as conferências rodam, mas o médico não as vê.

## 4. Agentes e locais

| Papel | Quem | Onde |
|---|---|---|
| Controlador | o médico ou a clínica que usa o OpenDoctor | — |
| Operador | OpenDoctor | servidor na Render (Ohio, EUA), atrás da Cloudflare; banco na Supabase (Canadá, `ca-central-1`) |
| Suboperador | OpenAI, L.L.C. (transcrição e rascunho; não recebe o áudio guardado) | EUA |
| Suboperador | Supabase (banco, inclusive o áudio guardado por 1 ano) | Canadá |

- Transferência internacional (EUA e Canadá): **[pendente]** mecanismo da Resolução CD/ANPD nº 19/2024
  (cláusulas-padrão contratuais com a OpenAI e a Supabase; a Render e a Cloudflare também processam dados
  em trânsito). Com o áudio guardado, a Supabase passa a guardar a voz por 1 ano.
- **[pendente]** DPA da OpenAI assinado; pedido de **Zero Data Retention** para `/v1/chat/completions`
  (hoje a OpenAI pode reter até 30 dias para monitorar abuso; a transcrição não retém).

## 5. Base legal e transparência

- Base legal: tutela da saúde, em procedimento realizado por profissionais de saúde (LGPD, art. 11, II, "f").
- Transparência ao paciente: o médico avisa e pede a autorização antes de gravar (não há mais marca na tela desde
  20/10/2026); desde 13/11/2026 o aviso precisa dizer que a consulta fica **gravada** e que o som fica guardado por
  1 ano. A data e a hora do início ficam registradas. A evolução gerada leva o aviso "Transcrição automática (IA)" (CFM 2.454/2026 —
  **[pendente]** conferir com o advogado o artigo e o texto exigidos).
- Política de Privacidade (`web/privacy.html`): seção "Gravação da consulta".

## 6. Necessidade e minimização

- O texto é o que o prontuário precisa e fica com ele. O áudio original fica guardado só para o médico conferir a
  transcrição e a evolução contra a fala real (decisão do usuário, 13/11/2026), com prazo menor que o do prontuário
  (1 ano), acesso só do médico dono e as audições no registro de acessos (as de 10 minutos agrupadas). O WAV enviado à transcrição não é guardado.
- Trechos só de silêncio não são enviados à transcrição (o áudio guardado inclui os silêncios, para o player não
  ter buracos).
- Para o rascunho vai texto mascarado; o nome do paciente nunca vai em URL nem em log, e os logs da
  gravação só têm números (duração, tempo).
- O perfil de escrita é estatístico: nenhum texto de outros pacientes vai ao modelo.
- Teto de 6 h de gravação por médico em 24 h; para o áudio guardado, pedaço de até 512 KB e teto de 300 MB por
  médico em 24 h; limite de pedidos por IP.

## 7. Riscos e medidas

| Risco | Medidas | Risco residual |
|---|---|---|
| Acesso indevido à transcrição e ao áudio guardado | login obrigatório em todas as rotas; toda consulta ao banco filtra pelo médico; RLS ligado nas tabelas novas (só o servidor acessa); teste automático percorre as rotas; o áudio só sai pela rota do player, por id, do médico dono, sem cache no navegador (`no-store`), com o tipo fixado pelos bytes (lista fechada) e as audições no registro de acessos (as de 10 minutos agrupadas) | baixo |
| Vazamento do áudio guardado (o dado mais identificável: voz, nome falado, terceiros) | RLS sem políticas (só o servidor acessa); prazo de 1 ano; apagado com "Apagar transcrição" e com a exclusão da conta; não vai a nenhum outro serviço. Não há criptografia própria da aplicação sobre o áudio, além da que o banco e o HTTPS oferecem | **médio**: tudo o que foi dito fica no banco por 1 ano; **[pendente]** avaliar cifrar o áudio na aplicação |
| Áudio que continua existindo depois de apagado | "Apagar transcrição", a exclusão da conta e a limpeza de 1 ano apagam do banco na hora | médio: as cópias de segurança e a recuperação a um ponto no tempo (PITR) da Supabase guardam o áudio apagado pelo prazo delas; "apagado" vale com esse atraso |
| Gravação órfã (gravada e nunca gerada nem ligada a uma evolução) | o áudio sai pela limpeza de 1 ano e com a exclusão da conta | médio: nenhum "Apagar transcrição" chega a ela na tela; fica no banco até 1 ano |
| Reidentificação pelo texto enviado ao modelo | máscara de nome, apelidos comuns do primeiro nome, CPF, CNS, telefone, e-mail; nome que também é palavra da consulta ("Maria das Dores", "dos Remédios", "doença de Chagas") só sai quando é nome | **médio**: a máscara não pega nomes de parentes, apelidos incomuns, endereço falado; o áudio enviado à transcrição contém tudo, e o contexto da transcrição leva o nome falado |
| Retenção na OpenAI | transcrição sem retenção; rascunho até 30 dias (monitoramento de abuso), sem uso para treino | médio até o ZDR **[pendente]** |
| Áudio esquecido no computador (consultório compartilhado) | banco do navegador por médico (os trechos WAV e os pedaços do áudio original); apagado quando o servidor confirma; o que não subiu em 48 h é apagado quando o OpenDoctor é aberto de novo nesse computador; "sair da conta" limpa o navegador | baixo. Se o médico sair da conta sem internet, trechos ainda não enviados se perdem (o aviso ao fechar a aba alerta). Se a aba for fechada sem internet, o som fica no aparelho até a próxima abertura do OpenDoctor nele (com a página fechada, o navegador não tem como apagar) |
| Perda de parte da consulta | captura contínua sem buracos entre trechos; cada trecho fica no navegador até a confirmação; o trecho em andamento é salvo a cada 2 s; fila com novas tentativas; recuperação ao reabrir | baixo (no máximo ~2 s se o computador desligar) |
| Erro clínico no rascunho (remédio, dose, valor, alergia, CID) | o médico revisa e assina; conferências sem IA (número fora da fala, remédio que não aparece, dose fora do usual, alergia, sinal vital impossível, CID inexistente, frase deduzida); palavras ouvidas com dúvida (marcadas na transcrição). Desde 13/11/2026 a lista de pontos para conferir e o pedido de confirmação ao finalizar com pontos abertos saíram da tela (pedido do usuário): as conferências rodam, mas não são mostradas | médio a alto: depende só da revisão do médico, sem os avisos. **[pendente]** decidir se voltam ou se o risco é aceito. Avaliação com 31 casos fictícios, sem nenhum remédio ou dose inventados; **[pendente]** conferência dos gabaritos por um médico e consultas encenadas por pessoas |
| Texto do médico sobrescrito | o rascunho só preenche campos vazios e entra abaixo do que já foi escrito; "Desfazer" | baixo |
| Uso sem autorização do paciente | sem marca na tela desde 20/10/2026: só a hora do início fica registrada | médio: depende só da conduta do médico, agora também para a guarda do som por 1 ano; **[pendente]** revisão jurídica |
| Prazo do áudio diferente do prontuário | o áudio é tratado como apoio à evolução, não como o prontuário: fica 1 ano, e o texto (transcrição e evolução) fica pelo prazo do prontuário | **[pendente]** revisão jurídica: se o som for considerado parte do prontuário (Lei 13.787/2018, mínimo 20 anos), apagar com 1 ano pode conflitar com a guarda |

## 8. Fronteira com dispositivo médico (Anvisa, RDC 657/2022)

A função só registra o que foi dito na consulta: o prompt proíbe sugerir diagnóstico, exame ou tratamento;
o CID-10 vem só de diagnóstico afirmado pelo médico ou de problema do cadastro manejado na consulta; frases
deduzidas viram ponto para conferir (que, desde 13/11/2026, não aparece na tela). **[pendente]** confirmação jurídica de que, assim, a função fica fora do
escopo de software como dispositivo médico.

## 9. Direitos do paciente

O paciente exerce os direitos (acesso, correção, informação) com o médico (controlador). O médico pode ver a
transcrição de cada consulta ("Ver transcrição"), ouvir o áudio guardado no player do prontuário e apagar os dois
("Apagar transcrição" apaga também o áudio); a exclusão fica no registro de acessos. A evolução assinada segue as
regras do prontuário (correções por adendo).

- Acesso ao som: não há como baixar o áudio; o pedido do paciente é atendido pelo médico, ouvindo a consulta no
  prontuário com ele. **[pendente]** revisão jurídica de que isso basta, ou criar um "Baixar áudio" (com registro no
  `access_log`).
- Exclusão da conta: o áudio guardado do médico é apagado; a transcrição e a evolução ficam pelo prazo legal. Depois
  disso, não há som para dar acesso.

## 10. Antes de abrir para pacientes reais (fora da conta do fundador)

- [ ] Cláusulas-padrão (ANPD 19/2024) com OpenAI e Supabase; DPA da OpenAI; pedido de ZDR.
- [ ] Revisão jurídica deste RIPD, da Política de Privacidade e dos Termos (CFM 2.454/2026, RDC 657/2022).
- [ ] Médico revisor para os gabaritos da avaliação e as regras do prompt.
- [ ] ≥ 8 consultas encenadas por pessoas, com ruído real, passando nos critérios do plano.
- [ ] Modelo de texto para o médico pedir a autorização ao paciente, dizendo que a consulta fica gravada e o som
  guardado por 1 ano.
- [ ] Revisão jurídica do prazo de 1 ano do áudio frente ao prazo do prontuário, do acesso do titular ao som e da
  guarda da voz (dado biométrico em potencial).
- [ ] Avaliar cifrar o áudio guardado na aplicação.
