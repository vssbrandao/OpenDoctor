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

### Base de medicamentos (`app/medicamentos.py`, `GET /prontuario/remedios/busca?q=`)
- **Fonte:** a Lista de Preços de Medicamentos da CMED/Anvisa (pública, sai todo mês, em gov.br/anvisa → CMED →
  Preços).
- **Script:** `scripts/cmed_medicamentos.py` gera `app/data/medicamentos.tsv.gz` (cerca de 270 KB; 20 mil
  apresentações) com:
  - substância, marca, laboratório, tipo (genérico, similar, novo…), tarja e se foi comercializado no último ano;
  - dose, forma e quantidade da embalagem, lidas da apresentação;
  - a apresentação original.
  
  Fica de fora o que tem restrição hospitalar, e os preços não entram.
- **Atualizar** (todo mês, ou quando quiser): baixar a planilha PMC e rodar
  `.venv/bin/python -m scripts.cmed_medicamentos lista_PMC__AAAAMMDD.xlsx`. O script precisa do `openpyxl` (só no
  desenvolvimento).
- **Busca:** todas as palavras precisam bater, até 12 resultados. Vem primeiro o que começa com o termo, a substância
  antes das marcas dela e as comercializadas antes. A substância junta todas as apresentações dela, de qualquer
  laboratório.

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
- **O cartão:** a nova receita segue o design do Figma (arquivo Concept, nó 1001:7340; cartão 1079:49100), com as
  medidas exatas do quadro de 1440. A largura acompanha a coluna do meio. O cartão tem:
  - fundo branco, canto de 19,34 e sombra;
  - uma linha a 161,99 do topo; o espaço acima fica vazio, como no Figma;
  - os dados: Paciente, Documento (o CPF do cadastro, ou "—") e Data de emissão por extenso. A Validade do Figma
    saiu, a pedido do usuário;
  - outra linha e os remédios numerados 01, 02…, na ordem em que entraram (a impressão continua agrupando por via);
  - a barra "Adicionar medicamento";
  - embaixo, o estado do rascunho e Copiar · Emitir.

  Os textos vêm de um print colado no Figma em escala 0,806 e ficam pequenos:
  - rótulos 8,87 px #858585;
  - valores 9,67 px bold #383838;
  - nome do remédio 10,48 px bold #303030;
  - linhas do remédio 9,27 px #555.
- **Lista:** cada remédio mostra:
  - o nome com a dose;
  - "Forma farmacêutica: …", quando veio da base (o item guarda `forma`);
  - a posologia;
  - "Quantidade: …";
  - os avisos.

  O "×" aparece ao passar o mouse e tem "Desfazer". Clicar edita: remédio, dose, posologia, quantidade, via e uso
  contínuo. Trocar o nome do remédio limpa a forma.
- **Novo item:** a barra do Figma tem 40,3 px, fundo #F3F3F3, canto 8, o "+" do SF Symbol (exportado do Figma) e
  "Adicionar medicamento" 11,28/16,12 Medium #6B7173. Fica sempre aberta, abaixo da lista. Ao digitar, abre embaixo
  o painel de busca no padrão do Google Finance, com as medidas tiradas da página de verdade:
  - **Painel:** #E9EBF0, com sombra.
  - **Filtros:** Todas · Substâncias · Marcas; o escolhido em #B8D5FF.
  - **Linhas:** título 16/20 e detalhe 12/16 à esquerda, o valor à direita (no máximo metade da linha), e o branco
    ao passar o mouse.
  
  São 3 passos dentro do painel:
  1. Resultados da base de medicamentos (veja "Base de medicamentos"). No fim, `Usar "texto"` aceita o texto livre;
     Enter sem escolher faz o mesmo.
  2. As apresentações do produto: dose e forma, com a embalagem à direita.
  3. Posologia, com a forma como dica, e quantidade, já com a embalagem de 30 quando existe. No texto livre, a dose
     também. Depois, "Adicionar".
  
  - A marca entra como "Marca (substância)".
  - ↑↓ e Enter escolhem; Esc volta um passo; clicar fora fecha.
  - Via e uso contínuo ficam na edição do item.
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
- **Observação da IA:** não aparece (o servidor ainda a devolve).
- **Nada com indicação clara:** aparece "Nenhum remédio novo com indicação clara agora."
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
