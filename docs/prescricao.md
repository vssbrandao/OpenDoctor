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
  avulsa ainda não salva, fica sem os dois, e é a renovação sem consulta. Na avulsa, a receita feita antes da evolução
  (rascunho ou já emitida) passa a ser dela quando ela é salva (`receita_ids` no salvar), e o rascunho sem consulta
  emitido com a evolução já salva sai nela (`note_id` no emitir).
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
- **Busca:**
  - todas as palavras do nome precisam bater; vêm até 12 resultados;
  - vem primeiro o que começa com o termo, a substância antes das marcas dela e as comercializadas antes;
  - a substância junta todas as apresentações dela, de qualquer laboratório;
  - palavra com número filtra a dose ("losartana 50" só traz 50 mg), e o produto sem apresentação que bata sai;
  - a dose é escrita de um jeito só (`dose_limpa`: "(100,0 + 25,0) mg" vira "100 mg + 25 mg"), para não repetir a mesma
    apresentação.
- **Alergia:** com `&patient_id=`, cada resultado traz as alergias do cadastro que batem (`scribe.allergy_hits`, a
  mesma regra da conferência).

### Rotas (privadas, sempre do médico)
- `GET /prontuario/receitas?patient_id=` e `POST /prontuario/receitas` (cria o rascunho).
- `PATCH` e `DELETE /prontuario/receitas/{id}`: só no rascunho. POST, PATCH e emitir aceitam `orientacoes` (texto livre,
  limpo, até 1000 caracteres; sem o campo, ficam como estão).
- PATCH e emitir exigem o `patient_id` da receita (409 se for outro): a página manda o paciente da hora em que mexeu.
- Nada do que sai no papel é cortado (`prescricao.erro_itens`): mais de 20 remédios, posologia acima de 500 caracteres
  ou quantidade acima de 60 dão 400 com o motivo, que a tela mostra. Nome, dose e forma vêm da base CMED e não se
  editam: o teto deles (2000, 200 e 300) fica bem acima do maior da base e só barra abuso, nunca um remédio de verdade.
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

### Tela: o componente Receita (`Receita(raiz, op)` em `web/opendoctor-agenda.html`)
É o centro da aba. Tem poucas funções: busca, posologia, quantidade, avisos, tirar com Desfazer, emitir e imprimir, uso
contínuo e orientações. O visual segue a referência do usuário (print 2x, medidas pela metade): dois blocos, cada um
com título 14 Medium, descrição 13 #848486 e um cartão branco (borda #EBEBEB, canto 12).
- **Bloco 1 · Prescrever:**
  - a busca sempre aberta: linha cinza #F7F7F7 de 44, canto 12;
  - uma linha por remédio para renovar: o uso contínuo da última emissão (as receitas emitidas no mesmo dia) que não
    está nesta receita. Cada uma tem o seu "Renovar", com a posologia da última vez e a quantidade de 30 dias;
  - até 2 possíveis prescrições da IA, no mesmo desenho, com "Adicionar". A alergia pede um segundo clique. A linha
    some quando o remédio entra na receita (o cartão antigo de Possíveis prescrições saiu);
  - as alergias do cadastro, em roxo itálico #A177E0 (como o "Next run on…" da referência).
- **A busca:**
  - lista direto as apresentações, até 8, a primeira marcada. A marca entra como "Marca (substância)";
  - ordem: o que o paciente já usou ("Já usou"), depois a substância, depois as marcas;
  - alergia em vermelho na linha, e o Enter pede um segundo Enter;
  - "Já na receita": o Enter leva até o item, sem repetir;
  - Enter antes do resultado chegar vale para o primeiro.
- **Bloco 2 · Receita:** a folha em texto, num painel cinza (13/22), que já nasce grande (340 de altura) com:
  - o médico (nome; CRM/UF e especialidade, ou "Completar meus dados de médico") e a data por extenso;
  - o paciente.
  
  Cada remédio é um parágrafo numerado que corre como texto, como a lista da referência:
  - a etiqueta branca inline (nome e dose; borda #E3E3E3, canto 7, 22 de altura, como o "JumpCloud");
  - a forma e a via, em cinza;
  - "— posologia" e "Quantidade:", trechos editáveis no meio da frase (`contenteditable="plaintext-only"`);
  - o × na ponta da linha, ao passar o mouse.
  
  No fim da folha vêm as orientações ao paciente: texto livre, salvo com o rascunho (`receitas.orientacoes`, migração
  0016), que sai impresso abaixo dos remédios e vai em cada receita emitida.
- **Ao escolher um remédio:** a posologia entra como da última vez ou em modelo da forma, com lacunas "_":
  - comprimido: "Tomar 1 comprimido a cada _ horas, por _ dias.";
  - também há modelo para cápsula, líquido, gotas, tópico, colírio, nasal e inalatório;
  - injetável fica em branco.
  
  O cursor fica na primeira lacuna, já selecionada, e Tab passa para a próxima. Lacuna que sobrou impede a emissão.
- **Quantidade calculada** (`Receita.quantidade`):
  - a conta é unidades por tomada × tomadas por dia × dias, com uso contínuo = 30 dias. Ex.: "1 cápsula a cada 8 horas,
    por 7 dias" → 21 cápsulas, com "calculada" em roxo;
  - só vale para o que se conta (comprimido, cápsula…);
  - "se dor", "se necessário", líquido ou lacuna aberta usam a embalagem da apresentação;
  - digitar a quantidade à mão desliga a conta.
- **Uso contínuo:** é o texto "uso contínuo" na posologia. O que se vê é o que sai.
- **Avisos:** a etiqueta fica vermelha (alergia, talão), âmbar (dose, rim) ou azul (controle especial,
  antimicrobiano), e as frases ficam numa lista logo abaixo do texto.
- **Teclado:**
  - ↑↓, Enter e Esc na busca;
  - Tab nas lacunas;
  - Enter na posologia → quantidade → busca;
  - ← ↑ no começo e → ↓ no fim de um trecho passam ao anterior ou ao próximo;
  - Backspace na posologia vazia tira o remédio (com Desfazer);
  - ⌘/Ctrl+Enter emite.
  
  Para o leitor de tela: combobox com `aria-activedescendant` e entrar, sair e a conta anunciados (`aria-live`).
- **Rodapé:** o que vai sair, ao vivo ("Saem 2 receitas: simples e antimicrobiano (2 vias)"), e Emitir.
  - Emitir confirma na própria tela: o que sai, os avisos, Voltar e "Emitir e imprimir".
  - Falta posologia ou quantidade: diz o quê e leva o cursor até lá.
- **Redesenhar:** cada item guarda o seu nó. Salvar ou conferir não recria o campo em que se está escrevendo.
- **Possíveis prescrições:** o "Adicionar" do bloco de cima leva à posologia do item, para revisar.
- **Histórico:** o "Usar nesta consulta" põe o item no texto.
- **Depois de emitir:** o cartão "Atualizar as medicações em uso?" mostra a diferença, cada linha com uma caixa:
  - entra o remédio de uso contínuo que não está no cadastro;
  - troca a linha quando a dose mudou (a mesma dose escrita de outro jeito não conta).
- **Histórico:** as emitidas aparecem no card da consulta e, com ele, no "Exportar PDF".
- **Impressão:** a linha do remédio leva a forma ("Losartana potássica 50 mg, comprimido revestido") e o uso
  contínuo uma vez só; as orientações vêm depois dos remédios. Só a folha vai para o papel enquanto `body.rxp` estiver ligado; desliga no `afterprint`. No Safari, o
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
- **Na tela:** as sugestões ficam no bloco "Prescrever" da receita, até 2, no desenho das linhas de Renovar. Cada uma
  mostra remédio, dose e posologia, e "Sugestão da IA · motivo" numa linha (inteiro ao passar o mouse). A única ação é
  **Adicionar**, que leva o item à receita, com o cursor na posologia para revisar. A linha some quando o remédio está
  na receita.
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
- gerar de novo não desfaz o que o médico fez: o remédio que alguma geração anterior já levou não volta (ele pode tê-lo
  tirado), mesmo que a última não o tenha citado — a gravação guarda a soma (`recordings.scribe.receita_meds`) — e a
  consulta com receita já emitida não ganha rascunho novo;
- a receita só muda depois que a evolução gerada é válida e foi guardada;
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
