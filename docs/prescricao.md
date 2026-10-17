# Prescrições: receitas, possíveis prescrições e receitas anteriores

A aba Prescrições do prontuário tem três partes (fases 1, 2 e 3 do plano; o que falta está em "Pendências"):

1. **Prescrições:** a receita da consulta aberta, que fica no rascunho até ser emitida.
2. **Possíveis prescrições:** sugestões da IA (ou só a renovação, sem IA). O "+" leva o item à receita; nada entra sem
   esse clique.
3. **Histórico:** as emitidas, as canceladas e os rascunhos de outras consultas, numa tabela com o mesmo visual da
   de Consultas.

## Receitas (tabela própria, migração `0014_receitas.sql`)
- **Ciclo:** `rascunho` → `emitida` (não muda mais) → `cancelada`, com o motivo e a hora.
- **Tipos:** `simples`, `especial` (controle especial) e `antimicrobiano`.
- **Item:** remédio, dose, posologia, quantidade, via, uso contínuo, origem (`ia`, `uso`, `manual`, `anterior`,
  `gravacao`), fonte e versão do prompt e do modelo, quando vem da IA. O servidor limpa cada item com
  `prescricao.item_limpo`.
- **Consulta:** o rascunho é desta consulta (`event_id` da agenda ou `note_id` da evolução). Sem consulta, ou numa
  avulsa ainda não salva, fica sem os dois, e é a renovação sem consulta.
- **Paciente:** excluir o paciente apaga os rascunhos. Receita emitida ou cancelada é prontuário: segura a exclusão
  (`has_notes`), como as evoluções.

### Rotas (privadas, sempre do médico)
- `GET /prontuario/receitas?patient_id=` e `POST /prontuario/receitas` (cria o rascunho).
- `PATCH` e `DELETE /prontuario/receitas/{id}`: só no rascunho.
- `POST /prontuario/receitas/conferir`: avisos de cada item; nada é gravado.
- `POST /prontuario/receitas/{id}/emitir`:
  - confere de novo;
  - exige nome, CRM e UF do médico;
  - recusa o que pede Notificação de Receita (talão);
  - separa controle especial e antimicrobiano em receitas próprias, emitidas juntas;
  - entra no registro de acessos.
- `POST /prontuario/receitas/{id}/cancelar`: só emitida, com motivo; entra no registro de acessos.
- `GET` e `PATCH /me/medico`: dados do médico e o papel da receita, A4 ou A5 (`web/opendoctor-configuracoes.html`).
- `POST /prontuario/prescricao/avaliar` e `GET /prontuario/prescricao/avaliacoes?patient_id=`: o "útil / não útil"
  das sugestões da IA (veja abaixo).

### Conferência de cada item (`prescricao.conferir`, inclusive o que o médico digita)
- Alergia do cadastro, inclusive família e marca (`scribe.allergy_hits`).
- Dose fora da faixa usual (`app/data/doses.tsv`).
- Função renal pela TFG das evoluções (`app/data/ajuste_renal.tsv`).
- Remédio repetido e nome fora da lista conhecida.
- **Controle especial** (`app/data/controlados.tsv`, Portaria 344):
  - **C1, C5 e o adendo A2** (tramadol, codeína): receituário de controle especial em 2 vias, com comprador e
    fornecedor;
  - **A, B e C2:** só avisam; precisam do talão e não saem pelo app.
- **Antimicrobiano** (`app/data/antimicrobianos.tsv`, RDC 471/2021): 2 vias, válida por 10 dias.

### Tela
- **Lista:** cada linha mostra os avisos e tem "×" com "Desfazer". Clicar edita: remédio, dose, posologia,
  quantidade, via e uso contínuo. O nome do remédio tem sugestão enquanto digita (`GET /prontuario/remedios`, a lista
  de `app/data/remedios.txt`, num `<datalist>`).
- **Emitir receita:** confirma mostrando os avisos e imprime as folhas, com o cabeçalho do médico e os itens agrupados
  por via de uso.
- **Copiar:** copia o texto da receita.
- **Histórico** (o visual da tabela de Consultas, sem abrir e fechar): **uma linha por remédio**, agrupadas pela
  receita.
  - **Cabeçalho de cada receita:**
    - data, hora, consulta, tipo e situação (Emitida, Cancelada com o motivo, ou Rascunho);
    - à direita, na mesma linha, as ações da receita inteira: "Imprimir 2ª via" (sai marcada, com a data original)
      e "Cancelar receita" (pede o motivo).
  - **Linha do remédio:**
    - remédio e dose, posologia e quantidade;
    - "Usar nesta consulta" leva só aquele remédio para a receita de hoje, e a escolha é linha a linha. Quando já
      está lá, o botão vira "Na receita".
  - **Busca:** "Buscar nas receitas" mostra só as linhas daquele remédio, cada uma com a sua receita. Sem busca,
    aparecem 5 receitas, com "Mostrar todas".
- **Depois de emitir:** o cartão "Atualizar as medicações em uso?" mostra a diferença, cada linha com uma caixa:
  - entra o remédio de uso contínuo que não está no cadastro;
  - troca a linha quando a dose mudou (a mesma dose escrita de outro jeito não conta);
  - "Tirar" o que foi suspenso e o médico quis manter nas em uso aparece desmarcado.
- **Histórico:** as emitidas aparecem no card da consulta e, com ele, no "Exportar PDF".
- **Impressão:** só a folha vai para o papel enquanto `body.rxp` estiver ligado; desliga no `afterprint`. No Safari, o
  `window.print()` não espera a impressão terminar.
- **Papel:** A4 ou A5 (meia folha), em Configurações. O `<style id="rxPapel">` põe o `@page` só enquanto a receita
  imprime; o PDF do prontuário continua em A4.

## Possíveis prescrições (`app/prescricao.py`, `POST /prontuario/prescricao/sugerir`)
1. **Perfil, sem nome:** sexo, idade, problemas, remédios e alergias, e o último valor de cada sinal e exame, com a
   data. A TFG é pela CKD-EPI 2021, igual à tela. Ainda passa por `scribe.mask`.
2. **Fontes:**
   - uma busca na base do assistente por problema (até 4);
   - com a TFG abaixo de 60, também a dose de cada remédio em uso na doença renal.
   
   As buscas rodam em paralelo. Trechos com semelhança abaixo de 0,35 ficam de fora, e o limite é de 12. A base tem
   artigos do PubMed Central, em inglês; as diretrizes brasileiras ainda não estão nela.
3. **Modelo:** `OPENAI_PRESC_MODEL`, padrão gpt-5.4. O prompt fica em `app/data/prescricao_prompt.txt`, com
   `PROMPT_VERSION` amarrada ao texto por teste.
4. **Conferências** (`finish`):
   - mudar algo exige fonte;
   - remédio novo precisa ser conhecido, sem alergia e sem contraindicação renal;
   - são no máximo 4 novos;
   - dose usual e função renal viram aviso;
   - remédio em uso esquecido pelo modelo volta como "manter".
5. **Guarda em memória** por 24 h, enquanto o perfil não muda. "Gerar de novo" força outra geração.

### Na tela
- **Adicionar** leva o item à receita. Em **ajustar**, se o remédio já está na receita, o botão vira "Trocar a dose" e
  a dose nova substitui a anterior.
- **Suspender:** tira o remédio da receita e pergunta se ele sai também das medicações em uso; o aviso tem "Desfazer",
  que devolve os dois.
- **Perguntar ao assistente:** põe no campo do assistente o perfil (sem o nome) e a pergunta sobre a sugestão; quem
  envia é o médico.
- **Não sugerir:** esconde a sugestão neste navegador (`localStorage`, por paciente). "Ver as que você tirou" mostra
  de novo, com "Voltar a sugerir".
- **Útil? Sim · Não:** a avaliação de cada sugestão da IA vai para a tabela `prescricao_avaliacoes` (migração
  `0015`), uma por sugestão (versão da IA, ação e remédio). Clicar de novo desmarca. Guarda só a sugestão, sem o
  perfil. Para o médico revisor, `scripts/avaliacoes_prescricao.py` mostra as contagens por versão da IA, sem médico
  e sem paciente (ler produção só com o ok do usuário).
- **Perfil mudou:** abrir a aba com o resumo clínico mudado gera de novo. Com a aba aberta, e quando chega sinal ou
  exame novo, só avisa "O perfil mudou desde estas sugestões", com "Gerar de novo", porque gerar gasta crédito e troca
  a lista. O que o médico muda pela própria aba (suspender, atualizar as em uso) não conta como mudança.

### Gravação da consulta
Os remédios que a gravação extrai (`scribe.finish` → `meds`) entram no rascunho da receita desta consulta como "Da
gravação" (`prescricao.da_gravacao`), para revisar:
- entra o mantido, o ajustado (os dois de uso contínuo) e o iniciado; o suspenso não entra;
- o que já está no rascunho não repete (`prescricao.mesmo_remedio`), nem ao gerar de novo;
- a tela recarrega a receita e avisa quantos entraram;
- se der erro, a evolução sai do mesmo jeito, sem a receita (`_receita_da_gravacao`).

**Acesso:** só as contas da gravação (`SCRIBE_EMAILS` / `SCRIBE_ALL`; `SCRIBE_OFF` desliga). Sem acesso, ou se a IA
falhar, aparece a renovação sem IA (`POST /prontuario/renovacao` → `scribe.renovacao`).

**Custo:** cerca de US$ 0,015 a 0,025 por geração, levando de 15 a 25 s.

## Testes
- **Sem crédito:**
  - `tests/test_receitas.py`: rotas e conferência, com o banco em memória `tests/fake_receitas.py`, também usado pelo
    preview;
  - `tests/test_db_integration.py`: o SQL no banco de testes;
  - `tests/test_prescricao.py` e `tests/test_renovacao.py`.
- **E2E** `tests/e2e/prescricoes.mjs`, num preview só dele: `PREVIEW=http://localhost:8792`, launch config
  `opendoctor-presc-e2e`, nunca a porta que o usuário está usando. Cenários:
  - excluir e desfazer;
  - item manual com alergia;
  - emitir sem CRM e depois em vias;
  - talão;
  - controle especial;
  - cancelar;
  - 2ª via;
  - recarregar no meio;
  - receita no Histórico;
  - ajustar troca a dose; suspender com Desfazer (receita e medicações em uso);
  - atualizar as medicações em uso depois de emitir;
  - "Não sugerir" depois de recarregar, "Perguntar ao assistente" sem o nome e a sugestão do nome do remédio;
  - sinal novo na consulta: aviso de perfil mudado;
  - útil / não útil (grava, troca, desmarca e volta ao recarregar);
  - busca e escolha dos itens no Histórico;
  - receita em A5.

  As sugestões da IA desses cenários são trocadas no próprio Chrome (`Fetch.fulfillRequest`); o servidor nem é
  chamado.
- **Qualidade da IA:** `scripts/presc_try.py`. **Gasta crédito:** só com o ok do usuário.

## Pendências
- **Médico revisor:** `controlados.tsv`, `antimicrobianos.tsv`, `ajuste_renal.tsv` e o prompt. É sugestão de conduta,
  perto da RDC 657/2022 da Anvisa.
- **Advogado:** modelo de receita, assinatura digital (ICP-Brasil), RIPD e Política, incluindo o envio do perfil à IA.
- **Produção:** as migrações 0014 e 0015 vão para produção só com o ok do usuário; no banco de testes já foram
  aplicadas.
- **Fase 3, o que depende de decisão:**
  - enviar ao paciente por WhatsApp ou e-mail (dado de saúde saindo do app: decidir com o usuário e o advogado);
  - receita digital com assinatura ICP-Brasil (integração externa; decidir com o advogado).
- **Reordenar os itens da receita:** está no plano, sem fase.
