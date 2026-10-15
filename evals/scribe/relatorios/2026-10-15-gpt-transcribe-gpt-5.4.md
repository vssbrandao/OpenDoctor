# Avaliação da gravação — 2026-10-15 · gpt-transcribe + gpt-5.4 · prompt 2026-10-15.3

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | **não** |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.364 · remédios {'rem_certo': 54, 'rem_aviso': 1, 'rem_sem_aviso': 0, 'rem_falta': 7, 'rem_inventado': 2} · sinais 66/68 · CID 9/33 · fatos 127/183 · proibidos 0

## 01-has-dm-tontura (sintética, 98.6 s, WER 0.196)

- fato ausente: nega + sincope|desmai
- ponto para conferir [medio] pendencia: Frequência da caminhada não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre duração da tontura não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre desmaio, falta de ar e dor no peito não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Valores de pressão medidos em casa não ficaram claros na gravação.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso de losartana, metformina e medicação para colesterol. Refere glicemias capilares em casa entre 110 e 130 mg/dL.
O: Pressão arterial 128/82 mmHg. Frequência cardíaca 74 bpm. Peso 86,8 kg. Glicemia capilar no momento 108 mg/dL. Coração e pulmões sem alterações. Pés sem alterações, com pulsos presentes e sensibilidade preservada ao monofilamento. Hemoglobina glicada 6,9.
A: Diabetes está na meta. Tontura ao levantar pode ser por queda da pressão ao ficar em pé.
P: Mantidos os três remédios em uso. Orientada a levantar devagar e sentar na cama por um minuto antes de ficar em pé. Solicitados exame de urina para os rins e ácido úrico. Retorno em três meses com os exames.
```

## 02-ajuste-dose-empagliflozina (sintética, 74.1 s, WER 0.365)

- fato ausente: agua|hidrat
- ponto para conferir [alto] numero: Hemoglobina glicada 8,1, acima da meta.
- ponto para conferir [medio] inferido: Pressão arterial elevada na consulta.

```
S: Refere uso de metformina 850 mg duas vezes ao dia; às vezes esquece a dose da noite.
O: Hemoglobina glicada 8,1, acima da meta. Pressão arterial 152/94 mmHg. Frequência cardíaca 80 bpm. Peso 92 kg.
A: Hemoglobina glicada acima da meta. Pressão arterial elevada na consulta.
P: Ajustada losartana para 100 mg uma vez ao dia. Mantida metformina 850 mg duas vezes ao dia. Iniciada empagliflozina 10 mg pela manhã. Orientado que empagliflozina pode dar infecção urinária. Solicitados creatinina e potássio em 30 dias. Retorno em dois meses.
```

## 03-fibrilacao-rivaroxabana (sintética, 69.4 s, WER 0.129)

- fato ausente: nega + sincope|desmai
- ponto para conferir [medio] pendencia: Resposta sobre dor no peito e falta de ar deitado não ficou clara na gravação.
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere início há uma semana de palpitações e cansaço ao subir escada. Relato de desmaio há uma semana.
O: Pulso irregular. Frequência cardíaca 112 bpm. Pressão arterial 138/86 mmHg. Eletrocardiograma mostrou fibrilação atrial.
A: Fibrilação atrial.
P: Iniciada rivaroxabana 20 miligramas, uma vez ao dia, junto com o jantar, para prevenir derrame. Suspenso AAS. Iniciado metoprolol succinato 50 miligramas uma vez ao dia para controlar o coração. Mantido anlodipino. Solicitados ecocardiograma, TSH e função dos rins. Orientado procurar pronto-socorro se sangramento que não para, fezes pretas ou urina com sangue. Retorno em quatro semanas.
```

## 04-pediatria-otite (sintética, 71.4 s, WER 0.54)

- faltou: amoxicilina
- sinal temp: esperado 38.2 / saiu 38.0
- fato ausente: ouvido + direit
- fato ausente: abaulad
- fato ausente: nega + vomito|diarreia
- ponto para conferir [alto] numero: Paciente com febre, referida até 38,5.
- ponto para conferir [medio] pendencia: Nome do antibiótico e posologia ficaram parcialmente ininteligíveis na gravação.
- ponto para conferir [medio] pendencia: Descrição do exame da garganta/ouvido e eventual diagnóstico não ficaram claros na gravação.

```
S: Paciente com febre, referida até 38,5. Responsável questiona conduta caso a febre não baixe.
O: Peso 16 kg. Temperatura no momento 38.
A: 
P: Prescrito paracetamol em gotas: 16 gotas a cada 6 em 6 horas, se precisar. Orientado retornar antes se continuar com febre por 48 horas durante o antibiótico. Orientado retorno em 10 dias.
```

## 05-prenatal-28-semanas (sintética, 57.5 s, WER 0.118)

- fato ausente: nega + sangramento|perda
- ponto para conferir [medio] pendencia: Resposta sobre movimentação do bebê, sangramento, perda de líquido e contração não ficou registrada na gravação.
- ponto para conferir [info] cadastro: Ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: 
O: Gestação com 28 semanas hoje. Pressão arterial 110/70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. Batimentos cardíacos fetais 144 bpm.
A: 
P: Iniciado sulfato ferroso 40 miligramas de ferro, um comprimido por dia, longe do café e do leite. Orientado parar ácido fólico. Solicitada curva glicêmica (TOTG de 75 gramas). Orientada vacinação DTPA no posto. Para azia, orientadas refeições menores e evitar deitar logo depois de comer. Retorno em duas semanas.
```

## 06-idoso-queda-desprescricao (sintética, 78.0 s, WER 0.703)

- sinal fc: esperado 72.0 / saiu None
- fato ausente: queda + banheiro
- fato ausente: vista escure|tontura
- fato ausente: em pe + 112
- fato ausente: sentado + 138
- fato ausente: luz
- fato ausente: 1 mes|um mes
- ponto para conferir [medio] vital_longe: pa_s = 112: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 70: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] pendencia: Há menção a 138/78 e 112/70, mas a posição/condição das medidas não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Trecho inicial da gravação está ininteligível.
- ponto para conferir [info] cadastro: Anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente com sintomas de estômago. Refere apenas um hematoma, sem dor.
O: Peso 61 kg. Pressões medidas: 138/78 e 112/70.
A: Hipertensão arterial. Diazepam aumenta o risco de queda.
P: Orientada redução do diazepam para 5 mg por duas semanas e depois suspensão. Suspenso omeprazol. Mantidos anlodipino e sinvastatina.
```

## 07-depressao-sertralina (sintética, 54.1 s, WER 0.214)

- fato ausente: dorme mal|insonia|sono

```
S: Em uso de sertralina há dois meses. Nega pensamentos de se machucar ou de morrer. Refere enjoo no começo do uso da medicação, já resolvido.
O: Questionário de hoje com 15 pontos.
A: Depressão moderada.
P: Ajustada sertralina para 100 miligramas pela manhã. Encaminhada para psicoterapia. Orientada a procurar ajuda imediatamente se surgirem pensamentos de se machucar, podendo ligar no 188. Retorno em quatro semanas.
```

## 08-asma-crise (sintética, 65.9 s, WER 0.513)

- faltou: budesonida
- a mais (foi citado, não está no gabarito): formoterol iniciado
- fato ausente: espacador
- fato ausente: gripe|resfriado|infecc
- ponto para conferir [medio] pendencia: Trecho 3 com áudio pouco claro ('Stress. Comissada.' e 'A recusa').
- ponto para conferir [medio] pendencia: Dose/apresentação do formoterol não foi dita.

```
S: História de asma.
O: Saturação 93%. Frequência respiratória 24 irpm. Frequência cardíaca 104 bpm. Sibilos bilaterais. Após três séries de salbutamol, saturação 97% e sibilos bem menos intensos.
A: Asma.
P: Salbutamol 4 jatos a cada 20 minutos. Prednisolona 40 miligramas uma vez ao dia por cinco dias. Formoterol 2 jatos de 12 em 12 horas, todos os dias. Orientado retorno em uma semana se piora ou falta de ar ou boca seca, rouquidão, bronquite.
```

## 09-meio-comprimido-captopril (sintética, 53.2 s, WER 0.31)

- fato ausente: meio comprimido|metade|12,5
- fato ausente: 160|150
- ponto para conferir [medio] vital_longe: pa_s = 156: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 92: o número está no trecho, mas não junto de PA

```
S: Paciente refere uso de captopril 25 mg duas vezes ao dia.
O: Pressão arterial aferida em 156/92 mmHg. Frequência cardíaca de 78 bpm.
A: 
P: Mantido captopril 25 mg, um comprimido inteiro, duas vezes ao dia. Iniciada hidroclorotiazida 25 mg, um comprimido pela manhã. Orientada a medir a pressão arterial em casa diariamente. Retorno em quatro semanas com as medidas de pressão.
```

## 10-cistite-alergia-sulfa (sintética, 48.7 s, WER 0.451)

- fato ausente: ardencia|disuria
- fato ausente: 2 dias|dois dias
- ponto para conferir [medio] pendencia: Resposta sobre febre, dor nas costas e sangue na urina não ficou clara na gravação.

```
S: Alergia a sulfa relatada.
O: Temperatura 36,8 °C. Abdômen sem dor à palpação. Punho-percussão negativa.
A: 
P: Prescrita nitrofurantoína 100 mg de 6 em 6 horas por 5 dias. Orientado beber bastante água. Orientado retornar se tiver febre ou dor nas costas. Orientado que não precisa retorno se melhorar.
```

## 11-alergia-penicilina-esquecida (sintética, 41.5 s, WER 0.279)

- fato ausente: 12 dias|doze dias
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] inferido: Quadro de vias aéreas superiores com dor à palpação dos seios maxilares e secreção amarelada na garganta.
- ponto para conferir [medio] pendencia: Início e evolução inicial do quadro não ficaram totalmente claros na gravação do trecho 1.

```
S: Quadro há dois dias. Refere temperatura de 38 ontem.
O: Temperatura atual de 37,6 °C. Dor à palpação dos seios maxilares. Secreção amarelada na garganta.
A: Quadro de vias aéreas superiores com dor à palpação dos seios maxilares e secreção amarelada na garganta.
P: Iniciado amoxicilina 875 miligramas de 12 em 12 horas por 7 dias. Orientada lavagem nasal com soro três vezes ao dia. Orientado retornar se não melhorar em três dias.
```

## 12-metformina-sem-dose (sintética, 31.8 s, WER 0.208)

- sem divergências
- ponto para conferir [medio] pendencia: dose e posologia da metformina após ajuste não foram ditas
- ponto para conferir [info] cadastro: Diabetes tipo 2 com hemoglobina glicada 7,8, ainda acima.

```
S: 
O: Hemoglobina glicada 7,8, acima. Pressão arterial 124/78 mmHg. Peso 74 kg.
A: Diabetes tipo 2 com hemoglobina glicada 7,8, ainda acima.
P: Aumentada metformina. Orientada dieta, com corte de refrigerante e doce. Solicitada repetição da hemoglobina glicada em três meses.
```

## 13-nomes-terceiros-e-cpf (sintética, 66.5 s, WER 0.847)

- faltou: ciclobenzaprina
- fato ausente: lombar|lombalgia
- fato ausente: lasegue
- fato ausente: nega + formig|irradia|perna
- fato ausente: 7 dias|sete dias
- ponto para conferir [medio] pendencia: Descrição completa do mecanismo/início da dor nas costas ficou parcialmente ininteligível na gravação.
- ponto para conferir [medio] pendencia: Houve menção a outro medicamento em 5 miligramas a cada 8 horas, mas o nome não ficou claro na gravação.
- ponto para conferir [medio] pendencia: Achados adicionais do exame/avaliação em [3] ficaram parcialmente ininteligíveis na gravação.

```
LIVRE: Paciente relatou dor nas costas após carregar peso. Negou perda de força. Foi prescrito paracetamol 750 miligramas de 6 em 6 horas e compressa morna. Orientado a voltar se a dor não desaparecer ou piorar.
```

## 14-ruido-alto-gastrite (sintética, 43.2 s, WER 0.845)

- avisado: ibuprofeno esperado * * suspenso / saiu   iniciado
- fato ausente: queimacao|azia|dispeps
- fato ausente: 1 mes|um mes
- fato ausente: nega + sangue|melena|hematem
- fato ausente: pylori
- ponto para conferir [medio] vital_longe: pa_s = 126: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 80: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] pendencia: Posologia do omeprazol não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose e posologia do ibuprofeno não ficaram claras na gravação.
- ponto para conferir [medio] pendencia: Descrição completa da queixa abdominal não ficou clara na gravação.

```
S: Queixa abdominal em região de lado esquerdo/epigástrio; descrição ficou parcialmente ininteligível na gravação.
O: PA 126/80 mmHg.
A: 
P: Orientado uso de anti-inflamatório. Prescrito omeprazol 20 mg por oito semanas. Ibuprofeno citado em conduta; dose e posologia não ficaram claras na gravação.
```

## 15-pedido-dentro-da-fala (sintética, 49.3 s, WER 0.229)

- sem divergências

```
S: Refere dor de cabeça, descrita como aperto dos dois lados. Nega náuseas, piora com luz e alteração de força ou de visão. Relata estresse no trabalho.
O: Pressão arterial 122/80 mmHg. Exame neurológico normal.
A: Cefaleia tensional.
P: Iniciada dipirona 1 grama, até de 6 em 6 horas. Orientados alongamento e pausas no trabalho. Orientado retorno se piorar. Médico informou que não vai receitar morfina nem fornecer atestado, por não ser indicado para o caso.
```

## 16-dpoc-exacerbacao (sintética, 56.7 s, WER 0.415)

- fato ausente: 4 dias|quatro dias
- fato ausente: escarro|expector
- fato ausente: nega + febre
- ponto para conferir [alto] remedio: budesonida + formoterol: não aparece na fala nem no cadastro
- ponto para conferir [medio] inferido: FR 22 irpm.
- ponto para conferir [medio] inferido: FC 96 bpm.
- ponto para conferir [medio] inferido: Sibilos esparsos.
- ponto para conferir [medio] inferido: Quadro respiratório com sibilos.
- ponto para conferir [medio] inferido: Acrescentado budesonida com formoterol 12/400, 1 inalação de 12/12 horas.
- ponto para conferir [medio] dose_longe: budesonida + formoterol: 12 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] dose_longe: budesonida + formoterol: 400 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] dose_longe: budesonida + formoterol: 1 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: Descrição inicial dos sintomas ficou parcialmente ininteligível na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre febre e inchaço nas pernas não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose/apresentação do inalador novo ficou parcialmente ininteligível na gravação.
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Queixa respiratória.
O: SpO2 91%. FR 22 irpm. FC 96 bpm. Sibilos esparsos.
A: Quadro respiratório com sibilos.
P: Iniciada prednisona 40 miligramas uma vez ao dia por cinco dias. Iniciada azitromicina 500 miligramas uma vez ao dia por três dias. Mantido tiotrópio. Acrescentado budesonida com formoterol 12/400, 1 inalação de 12/12 horas. Orientado procurar pronto-socorro se saturação abaixo de 88 ou se piora/deteriorar. Retorno em uma semana.
```

## 17-hipotireoidismo-levotiroxina (sintética, 35.6 s, WER 0.182)

- fato ausente: cansa|frio
- ponto para conferir [medio] inferido: Peso 70,5 kg.
- ponto para conferir [medio] pendencia: Não ficou clara na gravação a resposta sobre uso da levotiroxina em jejum, meia hora antes do café.

```
LIVRE: TSH 8,2 e T4 livre 0,8. Frequência cardíaca 62 bpm. Peso 70,5 kg. Tireoide sem nódulos à palpação.
Orientado repetir TSH em seis semanas.
```

## 18-lombalgia-doenca-renal (sintética, 50.5 s, WER 0.321)

- faltou: ciclobenzaprina
- INVENTADO: ciprofloxacino
- fato ausente: 42
- ponto para conferir [alto] dose_incomum: ciprofloxacino 5 miligramas: fora da dose usual por tomada (250–750 mg). Confira o nome e a dose: o transcritor pode ter trocado o remédio.
- ponto para conferir [medio] inferido: Quadro de dor lombar.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere dor nas costas após carregar caixas. Nega febre. Pergunta se pode tomar diclofenaco que tem em casa.
O: PA 134/84 mmHg. Dor à palpação da musculatura lombar, sem déficit.
A: Quadro de dor lombar.
P: Orientado a não usar diclofenaco/anti-inflamatório devido contraindicação pelos rins. Prescrito paracetamol 750 miligramas de 6 em 6 horas se dor, no máximo quatro comprimidos por dia. Prescrito ciprofloxacino 5 miligramas a cada 8 por 7 dias. Mantido uso de losartana.
```

## 19-dislipidemia-atorvastatina (sintética, 34.2 s, WER 0.157)

- fato ausente: nega + dor muscular|mialgia
- ponto para conferir [medio] pendencia: Resposta sobre dor muscular e fraqueza não ficou registrada na transcrição.

```
S: 
O: LDL 142, colesterol total 228 e triglicérides 160. Pressão arterial 118/76 mmHg. Peso 63 kg.
A: 
P: Ajustada atorvastatina para 40 mg à noite. Solicitada repetição do perfil lipídico e das enzimas do fígado em três meses.
```

## 20-enxaqueca-profilaxia (sintética, 42.3 s, WER 0.281)

- fato ausente: nausea|enjoo
- fato ausente: fotofob|luz
- fato ausente: nega + asma

```
LIVRE: Paciente relata enxaqueca cerca de 6 vezes por mês, com incômodo importante. Refere uso de anticoncepcional.
Pressão arterial 112/72 mmHg e frequência cardíaca 76 bpm. Exame neurológico normal.
Iniciado propranolol 40 mg 2 vezes ao dia. Orientado sumatriptano 50 mg na crise, no máximo 2 comprimidos por dia. Orientado fazer diário da dor. Retorno em 2 meses.
```

## 21-gota-colchicina (sintética, 60.0 s, WER 0.41)

- faltou: anlodipino
- fato ausente: halux|dedao|primeira articulacao|metatarsofalang
- fato ausente: churrasco|cerveja|alcool
- fato ausente: gelo
- fato ausente: alopurinol + depois|apos
- ponto para conferir [alto] numero: Temperatura 37,2 °C.
- ponto para conferir [alto] numero: Ácido úrico no último exame: 9,1.
- ponto para conferir [alto] numero: temp = 37,2 não encontrado no trecho citado
- ponto para conferir [medio] inferido: Quadro doloroso em dedo/articulação, com gravação parcialmente ininteligível quanto à localização exata.
- ponto para conferir [medio] pendencia: localização exata do dedo/articulação acometido não ficou clara na gravação
- ponto para conferir [medio] pendencia: nome da medicação que substituiria a hidroclorotiazida não ficou claro na gravação
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Relata dor em dedo iniciada de madrugada, com sensibilidade importante ao toque, com piora nos últimos dias. Refere que é a primeira vez que apresenta esse quadro.
O: Temperatura 37,2 °C. Ácido úrico no último exame: 9,1.
A: Quadro doloroso em dedo/articulação, com gravação parcialmente ininteligível quanto à localização exata. Hidroclorotiazida foi relacionada ao aumento do ácido úrico.
P: Iniciada colchicina 0,5 miligrama de 8 em 8 horas até melhora, no máximo por uma semana. Orientado retorno em duas semanas. Foi discutida troca da hidroclorotiazida por outra medicação, mas o nome do medicamento não ficou claro na gravação.
```

## 22-varfarina-inr (sintética, 40.6 s, WER 0.187)

- fato ausente: 35 + 30
- fato ausente: gengiva
- ponto para conferir [medio] inferido: INR acima da meta terapêutica.
- ponto para conferir [medio] dose_longe: varfarina: 0,5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [info] cadastro: varfarina: 5 mg 5 mg todos os dias, menos segunda e quinta, que toma meio comprimido (dose do cadastro: confirme se não mudou)

```
S: Nega sangue na urina, nas fezes e manchas roxas.
O: INR 3,8. Meta de INR entre 2 e 3. Pressão arterial 128 por 76 mmHg. Frequência cardíaca 70 bpm, regular.
A: INR acima da meta terapêutica.
P: Ajustada varfarina para 30 mg por semana: 5 mg todos os dias, exceto segunda e quinta, quando deve tomar meio comprimido. Repetir INR em uma semana.
```

## 23-anemia-ferro-sem-exame-fisico (sintética, 39.6 s, WER 0.449)

- fato ausente: menstrua + 7 dias|sete dias|intensa|forte
- ponto para conferir [alto] numero: Hemoglobina 10,2 e ferritina 8.
- ponto para conferir [alto] numero: Hemoglobina 10,2 e ferritina 8.

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Quadro descrito como anemia por falta de ferro. Iniciado sulfato ferroso, 1 comprimido de 40 miligramas de ferro 2 vezes ao dia, longe das refeições. Orientado usar com suco de laranja. Orientado que pode escurecer as fezes, considerado normal. Solicitado ultrassom transvaginal para investigar o sangramento. Programada repetição de hemograma e ferritina em 2 meses.
```

## 24-puericultura-9-meses (sintética, 39.4 s, WER 0.171)

- fato ausente: peito|amament|leite materno
- ponto para conferir [medio] pendencia: Informação sobre alimentação no trecho 1 não ficou clara na gravação.
- ponto para conferir [info] cadastro: Vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: 
O: Peso 9 quilos e 200 gramas. Comprimento 74 centímetros. Perímetro cefálico 44. Temperatura 36,7 °C. Senta-se com apoio e já engatinha. Vacinas em dia; próxima aos 12 meses.
A: Desenvolvimento adequado para a idade.
P: Manter vitamina D 400 unidades por dia. Orientado oferecer água entre as refeições. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (sintética, 52.1 s, WER 0.477)

- INVENTADO: domperidona
- fato ausente: 2 travesseiros|dois travesseiros|ortopneia
- fato ausente: 2 quilos|dois quilos|2 kg
- ponto para conferir [alto] numero: Peso 78,4 kg.
- ponto para conferir [alto] numero: Edema de pernas 2+/4+.
- ponto para conferir [alto] numero: peso = 78,4 não encontrado no trecho citado
- ponto para conferir [medio] vital_longe: fc = 68: o número está no trecho, mas não junto de FC
- ponto para conferir [medio] pendencia: Dose e posologia da domperidona não foram ditas.
- ponto para conferir [medio] pendencia: Trechos iniciais sobre sintomas e possível ganho de peso ficaram incompletos/inaudíveis na gravação.
- ponto para conferir [info] cadastro: Mantido carvedilol 6,25 mg duas vezes ao dia.
- ponto para conferir [info] cadastro: carvedilol: 6,25 mg duas vezes ao dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Peso 78,4 kg.
O: PA 118/72 mmHg. FC 68 bpm. Edema de pernas 2+/4+. Crepitações nas bases.
A: 
P: Ajustada furosemida para 40 mg duas vezes ao dia. Iniciada domperidona. Mantido carvedilol 6,25 mg duas vezes ao dia. Mantida espironolactona 25 mg 1x/dia. Mantido enalapril 10 mg duas vezes ao dia. Solicitados potássio e creatinina em uma semana. Retorno em duas semanas.
```

## 26-insonia-sem-benzodiazepinico (sintética, 42.9 s, WER 0.416)

- fato ausente: 3 meses|tres meses
- fato ausente: terapia cognitiva|tcc
- ponto para conferir [medio] pendencia: Trecho sobre "apneia" e outros termos no início do trecho 2 ficou ininteligível na gravação.
- ponto para conferir [medio] pendencia: Não ficou claro na gravação qual terapia/encaminhamento foi referido como "volte a encaminhar para terapia cognitiva para insônia".

```
LIVRE: Relata uso de celular na cama e consumo de café após as quatro da tarde. Médico não recomenda medicação não especificada, referindo que vicia e piora a memória. Orientada a deixar o celular fora do quarto e a consumir café apenas até o almoço. Retorno em um mês.
```

## 27-renovacao-de-receita (sintética, 28.0 s, WER 0.31)

- sem divergências
- ponto para conferir [medio] inferido: Consulta para renovação de receitas, sem queixas no momento.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tansulosina: 0,4 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente veio para renovar receitas. Refere estar bem. Nega queixas, tontura, inchaço e dificuldade para urinar. Refere estar urinando bem com o remédio da próstata.
O: PA 132/80 mmHg. FC 70 bpm.
A: Consulta para renovação de receitas, sem queixas no momento.
P: Receitas renovadas, mantidas as mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (sintética, 38.3 s, WER 0.2)

- sem divergências
- ponto para conferir [medio] inferido: Glicemias de jejum elevadas e hemoglobina glicada 9,4.
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Glicemias em jejum entre 180 e 220. Nega hipoglicemia, tremor e suor frio.
O: Hemoglobina glicada 9,4. Pressão arterial 136 por 82.
A: Glicemias de jejum elevadas e hemoglobina glicada 9,4.
P: Ajustada insulina NPH da noite para 14 unidades; mantida insulina NPH da manhã em 20 unidades. Mantida metformina. Orientado anotar as glicemias em jejum. Retorno em um mês.
```

## 29-micose-cetoconazol (sintética, 32.2 s, WER 0.417)

- faltou: cetoconazol
- fato ausente: prurido|coca
- ponto para conferir [alto] numero: Orientado uso de creme 2 vezes ao dia por 4 semanas.
- ponto para conferir [medio] pendencia: Nome do creme prescrito não ficou claro na gravação.

```
LIVRE: Paciente relata mancha vermelha na virilha há cerca de três semanas. Descrita placa avermelhada com borda mais viva em virilhas e diagnóstico de tinea crural.
Orientado uso de creme 2 vezes ao dia por 4 semanas. Orientado usar roupa de algodão. Orientado retorno se não melhorar em 4 semanas.
```

## 30-valor-corrigido (sintética, 33.2 s, WER 0.321)

- sem divergências
- ponto para conferir [medio] vital_longe: pa_s = 140: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 90: o número está no trecho, mas não junto de PA
- ponto para conferir [info] cadastro: Mantida hidroclorotiazida 25 mg 1x/dia.
- ponto para conferir [info] cadastro: Hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: 
O: PA 140/90 mmHg. FC 76 bpm.
A: Pressão arterial acima da meta.
P: Mantida hidroclorotiazida 25 mg 1x/dia. Orientada redução do sal. Orientada aferição da pressão arterial em casa duas vezes por semana. Retorno em dois meses com as medidas domiciliares.
```

## 31-exame-em-silencio (sintética, 82.0 s, WER 0.628)

- faltou: omeprazol
- fato ausente: tosse seca
- fato ausente: 3 semanas|tres semanas
- fato ausente: nega + febre
- fato ausente: nega + tabag|fuma
- fato ausente: pulmoes limpos|sem sibilos|murmurio
- ponto para conferir [medio] pendencia: Descrição do sintoma principal no trecho 1 não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Demais achados do trecho 4 não ficaram claros na gravação.
- ponto para conferir [medio] pendencia: Nome, dose e posologia do medicamento citado no trecho 5 não ficaram claros na gravação.

```
S: Refere sintoma não claramente compreensível na gravação há 3 meses. Sem febre. Refere nariz escorrendo.
O: Saturação de O2 98%.
A: 
P: Orientado elevar a cabeceira da cama. Se não houver melhora, considerar raio X de tórax. Retorno em 4 semanas.
```
