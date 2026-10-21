# RIPD — Gravação e transcrição da consulta

Relatório de Impacto à Proteção de Dados Pessoais (LGPD, art. 38) da função "gravar a consulta" do
OpenDoctor. **Rascunho técnico** (15/10/2026), para revisão jurídica antes do primeiro paciente real fora
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

## 2. Dados tratados

| Dado | Origem | Onde fica | Por quanto tempo |
|---|---|---|---|
| Áudio da consulta (voz do médico, do paciente e de acompanhantes) | microfone do computador do médico | trechos no navegador (IndexedDB) até o servidor confirmar; memória do servidor durante a transcrição | navegador: até a confirmação, no máximo 48 h, apagado ao sair da conta; servidor: não é gravado |
| Texto de cada trecho (transcrição), com o minuto e as palavras ouvidas com dúvida | transcrição (OpenAI) | banco do OpenDoctor (`recording_segments`) | junto do prontuário: mínimo 20 anos (Lei 13.787/2018) |
| Último rascunho gerado (texto da evolução) e os pontos para conferir, para a revisão continuar depois de recarregar ou noutro dia | servidor | `recordings.scribe` (`saida`) | junto da transcrição; sai com "Apagar transcrição" |
| Data e hora em que a gravação começou (`consent_at`), duração, situação | página | `recordings` | idem |
| Rastreio da evolução gerada (versão do prompt, modelo, contagem de pontos conferidos) — sem texto | servidor | `clinical_notes.data.scribe` | idem |
| Métricas da revisão (segundos, %, contagens) — sem texto | página, ao finalizar | `clinical_notes.data.timing` | idem |

Categorias: **dados pessoais sensíveis de saúde** (LGPD, art. 5º, II) do paciente; dados de terceiros que
falem na consulta; voz (dado biométrico em potencial — o OpenDoctor não extrai nem guarda características da voz).

## 3. Fluxo

1. Navegador: `getUserMedia` → AudioWorklet (`web/rec-worklet.js`) → trechos de 15–30 s cortados no silêncio
   → WAV 16 kHz → IndexedDB (banco por médico) → fila de envio.
2. `POST /prontuario/transcribe` (login, dono do paciente, hora do início obrigatória, formato conferido) →
   `stt.atranscribe` → OpenAI `/v1/audio/transcriptions` → só o **texto** é gravado; o navegador apaga o trecho.
   Junto do áudio vão, como contexto, o fim do texto do trecho anterior — sem CPF, CNS, telefone e e-mail
   (`scribe.mask_docs`), mas com o nome falado, que o próprio áudio já contém — e os nomes de remédios, problemas
   e alergias do cadastro (palavras-chave). O mesmo trecho chegando duas vezes ao mesmo tempo é transcrito uma vez.
3. `POST /prontuario/scribe` → texto de todos os trechos da consulta, **mascarado** (`scribe.mask`: nome →
   `[PACIENTE]`, CPF, CNS, telefone, e-mail), + cadastro (problemas, remédios, alergias, idade, sexo) + evolução
   anterior do mesmo paciente (mascarada) + perfil de escrita do médico (só estatísticas e siglas de uma lista
   fixa) → OpenAI `/v1/chat/completions` → conferências sem IA (`scribe.check`) → rascunho + pontos para conferir.
4. Médico revisa, confere os pontos e finaliza; a evolução registra "Transcrição automática (IA)".

## 4. Agentes e locais

| Papel | Quem | Onde |
|---|---|---|
| Controlador | o médico ou a clínica que usa o OpenDoctor | — |
| Operador | OpenDoctor | servidor na Render (Ohio, EUA), atrás da Cloudflare; banco na Supabase (Canadá, `ca-central-1`) |
| Suboperador | OpenAI, L.L.C. (transcrição e rascunho) | EUA |

- Transferência internacional (EUA e Canadá): **[pendente]** mecanismo da Resolução CD/ANPD nº 19/2024
  (cláusulas-padrão contratuais com a OpenAI e a Supabase; a Render e a Cloudflare também processam dados
  em trânsito).
- **[pendente]** DPA da OpenAI assinado; pedido de **Zero Data Retention** para `/v1/chat/completions`
  (hoje a OpenAI pode reter até 30 dias para monitorar abuso; a transcrição não retém).

## 5. Base legal e transparência

- Base legal: tutela da saúde, em procedimento realizado por profissionais de saúde (LGPD, art. 11, II, "f").
- Transparência ao paciente: o médico avisa e pede a autorização antes de gravar (não há mais marca na tela desde
  20/10/2026); a data e a hora do início ficam registradas. A evolução gerada leva o aviso "Transcrição automática (IA)" (CFM 2.454/2026 —
  **[pendente]** conferir com o advogado o artigo e o texto exigidos).
- Política de Privacidade (`web/privacy.html`): seção "Gravação da consulta".

## 6. Necessidade e minimização

- O áudio não é guardado em lugar nenhum do servidor; só o texto, que é o que o prontuário precisa.
- Trechos só de silêncio não são enviados.
- Para o rascunho vai texto mascarado; o nome do paciente nunca vai em URL nem em log, e os logs da
  gravação só têm números (duração, tempo).
- O perfil de escrita é estatístico: nenhum texto de outros pacientes vai ao modelo.
- Teto de 6 h de gravação por médico em 24 h; limite de pedidos por IP.

## 7. Riscos e medidas

| Risco | Medidas | Risco residual |
|---|---|---|
| Acesso indevido à transcrição | login obrigatório em todas as rotas; toda consulta ao banco filtra pelo médico; RLS ligado nas tabelas novas (só o servidor acessa); teste automático percorre as rotas | baixo |
| Reidentificação pelo texto enviado ao modelo | máscara de nome, apelidos comuns do primeiro nome, CPF, CNS, telefone, e-mail; nome que também é palavra da consulta ("Maria das Dores", "dos Remédios", "doença de Chagas") só sai quando é nome | **médio**: a máscara não pega nomes de parentes, apelidos incomuns, endereço falado; o áudio enviado à transcrição contém tudo, e o contexto da transcrição leva o nome falado |
| Retenção na OpenAI | transcrição sem retenção; rascunho até 30 dias (monitoramento de abuso), sem uso para treino | médio até o ZDR **[pendente]** |
| Áudio esquecido no computador (consultório compartilhado) | banco do navegador por médico; apagado quando o servidor confirma; apagado após 48 h; "sair da conta" limpa o navegador | baixo. Se o médico sair da conta sem internet, trechos ainda não enviados se perdem (o aviso ao fechar a aba alerta) |
| Perda de parte da consulta | captura contínua sem buracos entre trechos; cada trecho fica no navegador até a confirmação; o trecho em andamento é salvo a cada 2 s; fila com novas tentativas; recuperação ao reabrir | baixo (no máximo ~2 s se o computador desligar) |
| Erro clínico no rascunho (remédio, dose, valor, alergia, CID) | o médico revisa e assina; conferências sem IA (número fora da fala, remédio que não aparece, dose fora do usual, alergia, sinal vital impossível, CID inexistente, frase deduzida); palavras ouvidas com dúvida; pedido de confirmação ao finalizar com pontos não conferidos | médio: depende da revisão do médico. Avaliação com 31 casos fictícios, sem nenhum remédio ou dose inventados; **[pendente]** conferência dos gabaritos por um médico e consultas encenadas por pessoas |
| Texto do médico sobrescrito | o rascunho só preenche campos vazios e entra abaixo do que já foi escrito; "Desfazer" | baixo |
| Uso sem autorização do paciente | sem marca na tela desde 20/10/2026: só a hora do início fica registrada | médio: depende só da conduta do médico; **[pendente]** revisão jurídica |

## 8. Fronteira com dispositivo médico (Anvisa, RDC 657/2022)

A função só registra o que foi dito na consulta: o prompt proíbe sugerir diagnóstico, exame ou tratamento;
o CID-10 vem só de diagnóstico afirmado pelo médico ou de problema do cadastro manejado na consulta; frases
deduzidas viram ponto para conferir. **[pendente]** confirmação jurídica de que, assim, a função fica fora do
escopo de software como dispositivo médico.

## 9. Direitos do paciente

O paciente exerce os direitos (acesso, correção, informação) com o médico (controlador). O médico pode ver a
transcrição de cada consulta ("Ver transcrição") e apagá-la ("Apagar transcrição"); a exclusão fica no
registro de acessos. A evolução assinada segue as regras do prontuário (correções por adendo).

## 10. Antes de abrir para pacientes reais (fora da conta do fundador)

- [ ] Cláusulas-padrão (ANPD 19/2024) com OpenAI e Supabase; DPA da OpenAI; pedido de ZDR.
- [ ] Revisão jurídica deste RIPD, da Política de Privacidade e dos Termos (CFM 2.454/2026, RDC 657/2022).
- [ ] Médico revisor para os gabaritos da avaliação e as regras do prompt.
- [ ] ≥ 8 consultas encenadas por pessoas, com ruído real, passando nos critérios do plano.
- [ ] Modelo de texto para o médico pedir a autorização ao paciente.
