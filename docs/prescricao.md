# Prescrições: receitas, possíveis prescrições e receitas anteriores

A aba Prescrições do prontuário tem três partes (fases 1, 2 e 3 do plano; o que falta está em "Pendências"):

1. **Prescrições:** a receita da consulta aberta, que fica no rascunho até ser emitida.
2. **Possíveis prescrições:** até 2 remédios que o paciente ainda não usou e talvez façam sentido, sugeridos pela IA.
   O "+" leva o item à receita; nada entra sem
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
  - troca a linha quando a dose mudou (a mesma dose escrita de outro jeito não conta).
- **Histórico:** as emitidas aparecem no card da consulta e, com ele, no "Exportar PDF".
- **Impressão:** só a folha vai para o papel enquanto `body.rxp` estiver ligado; desliga no `afterprint`. No Safari, o
  `window.print()` não espera a impressão terminar.
- **Papel:** A4 ou A5 (meia folha), em Configurações. O `<style id="rxPapel">` põe o `@page` só enquanto a receita
  imprime; o PDF do prontuário continua em A4.

## Possíveis prescrições (`app/prescricao.py`, `POST /prontuario/prescricao/sugerir`)
**O que sugere:** só remédios NOVOS para o paciente, no máximo 2. Nenhum que esteja em uso nem que já tenha saído
numa receita emitida. Os remédios em uso não aparecem aqui: ficam no Histórico, com "Usar nesta consulta" em cada
linha.

1. **Perfil, sem nome:** sexo, idade, problemas, remédios em uso e alergias; "Já usou" (os remédios das receitas
   emitidas que não estão em uso; cancelada não conta); e o último valor de cada sinal e exame, com a data. A TFG é
   pela CKD-EPI 2021, igual à tela. Ainda passa por `scribe.mask`.
2. **Fontes:**
   - uma busca na base do assistente por problema (até 4): tratamento e escolha do remédio;
   - com a TFG abaixo de 60, também a escolha e a dose de remédios na doença renal.
   
   As buscas rodam em paralelo. Trechos com semelhança abaixo de 0,35 ficam de fora, e o limite é de 12. A base tem
   artigos do PubMed Central, em inglês; as diretrizes brasileiras ainda não estão nela.
3. **Modelo:** `OPENAI_PRESC_MODEL`, padrão gpt-5.4. O prompt fica em `app/data/prescricao_prompt.txt`, com
   `PROMPT_VERSION` amarrada ao texto por teste.
4. **Conferências** (`finish`):
   - só entra "iniciar"; manter, ajustar e suspender são descartados;
   - cada um precisa de fonte e de ser um remédio conhecido;
   - fica de fora o que está em uso, o que já usou, o repetido, o que bate com alergia e o que a função renal
     contraindica;
   - são no máximo 2;
   - dose fora da faixa usual e ajuste renal viram aviso.
   
   A comparação de nomes é a de `scribe.same_drug`, que tolera até 2 letras de diferença. Por isso dapagliflozina e
   empagliflozina contam como o mesmo remédio, e outro remédio da mesma classe de um já usado também sai.
5. **Guarda em memória** por 24 h, enquanto o perfil não muda.

### Na tela
- **Cartão minimalista:** cada sugestão mostra remédio, dose e posologia, e o motivo numa linha (inteiro ao passar o
  mouse). A única ação é **Adicionar**, que leva o item à receita; de novo ("Na receita") tira.
- **Avisos:** os de alergia, dose e função renal aparecem quando houver.
- **Observação da IA:** em texto pequeno, em até 2 linhas.
- **Nada com indicação clara:** a lista vem vazia, com a observação da IA.
- **Perfil mudou:** gera de novo ao abrir a aba. Conta como mudança o cadastro e o último valor de cada sinal e exame.
  - **Com a aba aberta:** não gera sozinho, porque gerar gasta crédito e troca a lista. O que o médico muda pela
    própria aba (atualizar as em uso) não conta.
  - **Se a IA falhar:** abrir a aba de novo tenta outra vez.

### Gravação da consulta
Os remédios que a gravação extrai (`scribe.finish` → `meds`) entram no rascunho da receita desta consulta como "Da
gravação" (`prescricao.da_gravacao`), para revisar:
- entra o mantido, o ajustado (os dois de uso contínuo) e o iniciado; o suspenso não entra;
- o que já está no rascunho não repete (`prescricao.mesmo_remedio`), nem ao gerar de novo;
- a tela recarrega a receita e avisa quantos entraram;
- se der erro, a evolução sai do mesmo jeito, sem a receita (`_receita_da_gravacao`).

**Acesso:** só as contas da gravação (`SCRIBE_EMAILS` / `SCRIBE_ALL`; `SCRIBE_OFF` desliga). Sem acesso, o cartão não
aparece. Se a IA falhar, aparece o aviso com "Tentar de novo". A rota `POST /prontuario/renovacao` (`scribe.renovacao`)
continua no servidor, mas a tela não a usa mais.

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
  - atualizar as medicações em uso depois de emitir;
  - possíveis prescrições: só 2 remédios novos e só o "Adicionar"; a sugestão do nome do remédio;
  - busca e escolha dos itens no Histórico;
  - receita em A5.

  O preview usa uma resposta real guardada (`scripts/preview_prescricao.json`, prompt 2026-10-17.1, Maria fictícia):
  dapagliflozina e semaglutida.
- **Qualidade da IA:** `scripts/presc_try.py`. **Gasta crédito:** só com o ok do usuário.

## Pendências
- **Médico revisor:** `controlados.tsv`, `antimicrobianos.tsv`, `ajuste_renal.tsv` e o prompt. É sugestão de conduta,
  perto da RDC 657/2022 da Anvisa.
- **Advogado:** modelo de receita, assinatura digital (ICP-Brasil), RIPD e Política, incluindo o envio do perfil à IA.
- **Produção:** as migrações 0014 (receitas) e 0015 (papel da receita) vão para produção só com o ok do usuário; no
  banco de testes já foram aplicadas.
- **Fase 3, o que depende de decisão:**
  - enviar ao paciente por WhatsApp ou e-mail (dado de saúde saindo do app: decidir com o usuário e o advogado);
  - receita digital com assinatura ICP-Brasil (integração externa; decidir com o advogado).
- **Reordenar os itens da receita:** está no plano, sem fase.
