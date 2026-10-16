# Prescrições: receita da consulta e possíveis prescrições

A aba Prescrições do prontuário tem dois cartões:

1. **Prescrições:** a receita da consulta aberta. É um rascunho salvo junto com a evolução, em `data.receita`.
   - Cada item tem remédio, dose, posologia, quantidade e a origem: `ia`, `uso` ou `manual`. Itens da IA levam também
     a fonte e a versão do prompt e do modelo.
   - Clicar na linha abre a edição. Dá para copiar o texto e "Gerar receita": a folha da receita, para imprimir ou
     salvar em PDF, com espaço para carimbo e assinatura (o app ainda não guarda o CRM).
   - Gerar a receita fica registrado nos acessos como exportação.
   - Evolução finalizada: a receita não muda mais.
2. **Possíveis prescrições:** a IA propõe, para cada remédio em uso, manter, ajustar ou suspender, e pode sugerir
   iniciar remédios novos. Cada sugestão traz o artigo da base do assistente que a sustenta. O "+" leva o item à
   receita; nada entra sem esse clique.

## Fluxo (`app/prescricao.py`, `POST /prontuario/prescricao/sugerir`)

1. **Perfil, sem nome:** sexo, idade, problemas, remédios e alergias do cadastro, mais o último valor de cada sinal e
   exame das evoluções, com a data. A TFG é calculada pela CKD-EPI 2021, com a idade na data do exame, igual à tela.
   O texto ainda passa por `scribe.mask`.
2. **Fontes:**
   - uma busca na base do assistente por problema (até 4);
   - com a TFG abaixo de 60, também a dose de cada remédio em uso na doença renal.
   
   As buscas rodam em paralelo. Trecho com semelhança abaixo de 0,35 fica de fora, e o limite é de 12 trechos.
   A base hoje tem artigos do PubMed Central, em inglês e de acesso aberto. As diretrizes brasileiras ainda não estão
   nela.
3. **Modelo:** `OPENAI_PRESC_MODEL`, padrão gpt-5.4, com saída em JSON. O prompt fica em
   `app/data/prescricao_prompt.txt`, versionado em `PROMPT_VERSION`; o teste amarra a versão ao texto.
4. **Conferências sem IA** (`finish`):
   - ação desconhecida sai;
   - ajustar e suspender exigem fonte dada e remédio em uso;
   - iniciar exige fonte e remédio conhecido (`scribe.drug_lookup`), não pode bater com alergia (inclusive família e
     marca) e não pode ter contraindicação renal. São no máximo 4 remédios novos;
   - dose fora da faixa usual vira aviso (`app/data/doses.tsv`);
   - a função renal vira aviso (`app/data/ajuste_renal.tsv`);
   - remédio em uso que o modelo esqueceu volta como "manter".
5. **Guarda em memória** por médico, paciente, perfil, prompt e modelo, por 24 h: abrir a aba de novo não gasta
   crédito. "Gerar de novo" força outra geração.

## Acesso, custo e falhas

- **Acesso:** só as contas liberadas da gravação (`SCRIBE_EMAILS` / `SCRIBE_ALL`; `SCRIBE_OFF` desliga). Sem acesso,
  a lista mostra só a renovação do uso contínuo, sem IA: `POST /prontuario/renovacao` → `scribe.renovacao`.
- **Custo e tempo:** com o gpt-5.4, cerca de US$ 0,015 a 0,025 por geração (testes de 16/10/2026). Leva de 15 a 25 s,
  sendo de 2 a 7 s da busca.
- **Falhas:** se a IA falhar, a tela cai para a renovação e mostra "Tentar de novo". O log leva só números.
- **Limite:** `RATE_LIMITS["prescricao"]`.

## Testes

- `tests/test_prescricao.py`: perfil, TFG, conferências, aviso renal, rota, guarda e `data.receita`. O modelo e a
  busca são simulados.
- `tests/test_renovacao.py`: a renovação sem IA.
- `scripts/presc_try.py`: qualidade com a OpenAI e a busca de verdade, com pacientes fictícios. **Gasta crédito:**
  rode só com o ok do usuário.
- **Preview:** `scripts/preview_gravacao.py` usa a resposta real guardada em `scripts/preview_prescricao.json`, sem
  OpenAI e sem banco. O botão "IA" faz a geração falhar.

## Pendências antes de abrir para outros médicos

- **Médico revisor:** conferir o prompt, `ajuste_renal.tsv` e uma amostra de sugestões. É sugestão de conduta, perto da
  regra de software como dispositivo médico da Anvisa (RDC 657/2022).
- **Base de evidência:** pôr diretrizes brasileiras (SBD, SBC, PCDT). Hoje a base raramente traz ajuste de dose renal,
  e o modelo só ajusta com fonte; por isso existe a tabela renal.
- **RIPD e Política de Privacidade:** registrar este envio. O perfil sem nome vai ao modelo ao abrir a aba, sem o médico
  digitar.
