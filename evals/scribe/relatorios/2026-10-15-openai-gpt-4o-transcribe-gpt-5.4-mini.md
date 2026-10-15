# Avaliação da gravação — 2026-10-15 · gpt-4o-transcribe + gpt-5.4-mini · prompt 2026-10-15.4

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.116 · remédios {'rem_certo': 45, 'rem_aviso': 14, 'rem_sem_aviso': 0, 'rem_falta': 3, 'rem_inventado': 0} · sinais 47/68 · CID 25/33 · fatos 138/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.072)

- sem divergências
- ponto para conferir [medio] duvida: Refere glicemias de jejum entre 110 e 130 e nega hipoglicemias. (ouvido com dúvida: entre)
- ponto para conferir [info] cadastro: Diabetes tipo 2 em meta.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso regular de losartana, metformina e remédio do colesterol. Relata caminhada 4 vezes por semana por cerca de 30 minutos. Refere dois episódios nesta semana de tontura ao levantar da cama, com melhora rápida em menos de um minuto ao sentar. Nega desmaio, dor e falta de ar. Refere glicemias de jejum entre 110 e 130 e nega hipoglicemias. Informa hemoglobina glicada de 6,9. Plano de manter os três remédios, levantar devagar e aguardar exame de urina para os rins e ácido úrico, com retorno em três meses.
O: Pressão arterial 128 por 82 mmHg. Frequência cardíaca 74 bpm. Peso 86,8 kg. Glicemia capilar 108 mg/dL. Coração e pulmões sem alterações. Pés sem alterações. Pulsos presentes. Sensibilidade preservada no monofilamento.
A: Diabetes tipo 2 em meta. Tontura ao levantar, possivelmente relacionada a queda de pressão em ortostatismo.
P: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite. Orientada a levantar devagar e sentar na cama por um minuto antes de ficar em pé. Solicitados exame de urina para os rins e ácido úrico. Retorno em três meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.413)

- sinal pa_s: esperado 152.0 / saiu None
- sinal pa_d: esperado 94.0 / saiu None
- sinal fc: esperado 80.0 / saiu None
- sinal peso: esperado 92.0 / saiu None
- fato ausente: esquec
- fato ausente: creatinina + potassio
- fato ausente: 30 dias
- fato ausente: agua|hidrat
- fato ausente: infeccao urinaria|higiene
- fato ausente: 2 meses|dois meses
- ponto para conferir [medio] inferido: Diabetes tipo 2 com controle acima da meta.
- ponto para conferir [medio] inferido: Hipertensão arterial em ajuste de tratamento.
- ponto para conferir [medio] pendencia: Losartana dita com dúvida na gravação na parte de iniciar/ajustar e na dose de 100 miligramas.
- ponto para conferir [medio] pendencia: Empagliflozina dita com dúvida na gravação na dose de 10 miligramas.

```
S: Trouxe exames. Hemoglobina glicada 8,1, acima da meta. Paciente em uso de metformina 850 duas vezes ao dia.
O: Hemoglobina glicada 8,1.
A: Diabetes tipo 2 com controle acima da meta. Hipertensão arterial em ajuste de tratamento.
P: Mantida metformina 850 mg, 2 vezes ao dia. Losartana ajustada para 100 mg, 1 vez ao dia. Empagliflozina iniciada, 10 mg, de manhã.
```

## 03-fibrilacao-rivaroxabana (voz natural, 80.2 s, WER 0.235)

- sinal pa_s: esperado 138.0 / saiu None
- sinal pa_d: esperado 86.0 / saiu None
- sinal fc: esperado 112.0 / saiu None
- fato ausente: nega + sincope|desmai
- fato ausente: irregular
- fato ausente: sangramento|fezes
- ponto para conferir [medio] duvida: Coração disparando há uma semana, com palpitações e cansaço para subir escada. (ouvido com dúvida: para)
- ponto para conferir [medio] duvida: Foi orientado iniciar rivaroxabana 20 mg uma vez ao dia junto com o jantar, suspender AAS e iniciar metoprolol suxinato 50 mg uma vez ao dia. Anlodipino mantido. (ouvido com dúvida: suxinato)
- ponto para conferir [medio] inferido: Palpitações.
- ponto para conferir [medio] inferido: Hipertensão arterial.
- ponto para conferir [medio] duvida: Iniciar metoprolol suxinato 50 mg uma vez ao dia. (ouvido com dúvida: suxinato)
- ponto para conferir [medio] pendencia: resposta sobre desmaio não ficou clara na gravação
- ponto para conferir [medio] pendencia: resposta sobre dor no peito e falta de ar deitado não ficou clara na gravação
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Coração disparando há uma semana, com palpitações e cansaço para subir escada.
O: Foi orientado iniciar rivaroxabana 20 mg uma vez ao dia junto com o jantar, suspender AAS e iniciar metoprolol suxinato 50 mg uma vez ao dia. Anlodipino mantido. Foram solicitados ecocardiograma, TSH e função dos rins.
A: Palpitações. Hipertensão arterial.
P: Iniciar rivaroxabana 20 mg uma vez ao dia junto com o jantar. Suspender AAS. Iniciar metoprolol suxinato 50 mg uma vez ao dia. Manter anlodipino. Solicitar ecocardiograma, TSH e função dos rins. Retorno em quatro semanas.
```

## 04-pediatria-otite (voz natural, 78.9 s, WER 0.222)

- avisado: amoxicilina esperado 8 ml 12/12h iniciado / saiu   iniciado
- sinal temp: esperado 38.2 / saiu None
- sinal peso: esperado 16.0 / saiu None
- fato ausente: 38,5|38.5|38 e meio
- fato ausente: abaulad
- ponto para conferir [medio] pendencia: temperatura citada com dúvida: 'trinta e oito e meio'
- ponto para conferir [medio] pendencia: dose e posologia da amoxicilina com fala com dúvida na gravação

```
S: Febre desde ontem. Dor no ouvido direito. Choro associado. Nega vômito, diarreia e falta de ar.
O: Ouvido direito vermelho e alterado. Ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações. Otite média aguda.
A: Otite média aguda.
P: Amoxicilina iniciada. Paracetamol gotas se necessário para febre ou dor. Orientado retorno em 10 dias. Orientado voltar antes se febre persistir após 48 horas de antibiótico ou se ficar prostrado.
```

## 05-prenatal-28-semanas (voz natural, 68.3 s, WER 0.02)

- fato ausente: dtpa
- ponto para conferir [medio] inferido: Gestação de 28 semanas.
- ponto para conferir [medio] pendencia: vacina DTPa ouvida com dúvida: 'DTPa'
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Gestante de 28 semanas. Refere bebê mexendo bastante. Refere azia à noite. Nega sangramento, perda de líquido e contrações.
O: Pressão arterial 110/70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. BCF 144 bpm.
A: Gestação de 28 semanas.
P: Iniciar sulfato ferroso 40 mg, 1 comprimido ao dia, longe do café e do leite. Suspender ácido fólico. Solicitar curva glicêmica / TOTG de 75 g. Orientada a fazer refeições menores e evitar deitar logo após comer por azia. Retorno em duas semanas.
```

## 06-idoso-queda-desprescricao (voz natural, 74.5 s, WER 0.312)

- avisado: diazepam esperado 5 mg * ajustado / saiu  à noite ajustado
- fato ausente: vista escure|tontura
- fato ausente: em pe + 112
- fato ausente: sentado + 138
- fato ausente: luz
- fato ausente: 1 mes|um mes
- ponto para conferir [alto] duvida_grave: amlodipino: 5 ouvido com dúvida
- ponto para conferir [medio] inferido: Queda noturna com escurecimento visual ao levantar, em contexto de uso de diazepam.
- ponto para conferir [medio] duvida: Queda noturna com escurecimento visual ao levantar, em contexto de uso de diazepam. (ouvido com dúvida: levantar)
- ponto para conferir [medio] inferido: Insônia em manejo medicamentoso.
- ponto para conferir [medio] inferido: Gastrite em melhora, sem sintoma gástrico referido.
- ponto para conferir [medio] inferido: Hipertensão arterial em seguimento.
- ponto para conferir [medio] duvida: Reduzir diazepam para 5 mg por duas semanas e depois suspender. (ouvido com dúvida: 5)
- ponto para conferir [medio] pendencia: dose do diazepam ajustado foi ouvida com dúvida ('5mg')
- ponto para conferir [medio] pendencia: não ficou claro se a piora da tontura/queda foi atribuída formalmente ao diazepam
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: amlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: amlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Relata queda no banheiro de madrugada na semana passada, com impacto no braço. Refere escurecimento da vista ao levantar para ir ao banheiro. Nega dor ao mexer o braço; há apenas hematoma. Refere ausência de mais sintoma de estômago.
O: Pressão arterial 112/70 mmHg. Frequência cardíaca 72 bpm. Peso 61 kg. Braço com hematoma, sem dor à mobilização.
A: Queda noturna com escurecimento visual ao levantar, em contexto de uso de diazepam. Insônia em manejo medicamentoso. Gastrite em melhora, sem sintoma gástrico referido. Hipertensão arterial em seguimento.
P: Reduzir diazepam para 5 mg por duas semanas e depois suspender. Suspender omeprazol. Manter amlodipino e sinvastatina.
```

## 07-depressao-sertralina (voz natural, 62.9 s, WER 0.019)

- sem divergências
- ponto para conferir [medio] inferido: Episódio depressivo com sintomas persistentes, com melhora parcial.
- ponto para conferir [medio] pendencia: posologia da sertralina não ficou clara na gravação; foi dito apenas 'de manhã'

```
S: Refere um pouco de melhora desde o início da sertralina, há dois meses, mas persiste sem vontade de fazer as coisas. Relata sono ruim e choro fácil. Nega pensamentos de se machucar ou de morrer. Referiu um pouco de enjoo no começo, já passado.
O: Questionário de hoje com 15 pontos, compatível com depressão moderada.
A: Episódio depressivo com sintomas persistentes, com melhora parcial. Depressão moderada pelo questionário.
P: Aumentada sertralina para 100 mg. Encaminhada para psicoterapia. Orientada a procurar ajuda imediata se aparecer pensamento de se machucar; pode ligar para 188. Retorno em 4 semanas.
```

## 08-asma-crise (voz natural, 68.8 s, WER 0.043)

- avisado: prednisolona esperado 40 mg 1x/dia iniciado / saiu  1 vez ao dia por cinco dias iniciado
- ponto para conferir [alto] numero: Feito salbutamol, quatro jatos a cada 20 minutos, três vezes com espaçador.
- ponto para conferir [alto] numero: salbutamol: 4 jatos a cada 20 minutos, 3 vezes com espaçador
- ponto para conferir [medio] inferido: Quadro de dispneia com sibilância em manejo de asma.
- ponto para conferir [medio] pendencia: dose da prednisolona foi dita com dúvida na gravação
- ponto para conferir [medio] pendencia: 'todos os dias' da budesonida com formoterol ficou com dúvida na gravação
- ponto para conferir [medio] pendencia: orientação de procurar pronto socorro foi dita com dúvida na gravação

```
S: Falta de ar desde ontem, com chiado importante. Usou a bombinha cerca de seis vezes hoje. Referiu gripe na semana passada.
O: Saturação 93%, frequência respiratória 24 e frequência cardíaca 104. Sibilos bilaterais. Após três séries com salbutamol, saturação 97% e sibilos bem menores.
A: Quadro de dispneia com sibilância em manejo de asma.
P: Feito salbutamol, quatro jatos a cada 20 minutos, três vezes com espaçador. Prescrita prednisolona 40 mg uma vez ao dia por cinco dias. Iniciada budesonida com formoterol, dois jatos de doze em doze horas. Orientado retorno em uma semana.
```

## 09-meio-comprimido-captopril (voz natural, 47.4 s, WER 0.0)

- avisado: hidroclorotiazida esperado 25 mg 1x/dia iniciado / saiu  um comprimido de manhã iniciado
- ponto para conferir [medio] inferido: Hipertensão arterial.
- ponto para conferir [medio] pendencia: dose da hidroclorotiazida foi dita com dúvida na gravação ('25 miligramas')

```
S: Pressão em casa sempre alta, com medidas de 160 e 150. Usava meio comprimido de captopril por orientação de terceiros, por considerar a medicação forte.
O: Pressão arterial em consulta: 156 por 92 mmHg. Frequência: 78 bpm.
A: Hipertensão arterial.
P: Ajustado captopril para um comprimido inteiro de 25 mg, duas vezes ao dia. Iniciada hidroclorotiazida pela manhã. Orientada medida da pressão em casa e anotação dos valores. Retorno em quatro semanas com as medidas.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.011)

- avisado: nitrofurantoina esperado 100 mg 6/6h iniciado / saiu  de 6 em 6 horas por 5 dias iniciado
- fato ausente: alergia + sulfa
- ponto para conferir [medio] inferido: Quadro urinário com disúria e polaciúria.
- ponto para conferir [medio] cid: CID R35.0 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: dose da nitrofurantoína não ficou clara na gravação

```
S: Relata ardência para urinar há dois dias e vontade de urinar toda hora. Nega febre, dor nas costas e sangue na urina. Relata que na outra vez usou Bactrim e pergunta se pode tomar de novo.
O: Temperatura de 36,8. Abdome sem dor. Punho-percussão negativa.
A: Quadro urinário com disúria e polaciúria.
P: Iniciada nitrofurantoína 100 mg de 6 em 6 horas por 5 dias. Orientada a beber bastante água. Orientada a retornar se tiver febre ou dor nas costas. Não precisa retorno se melhorar.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- avisado: amoxicilina esperado 875 mg 12/12h iniciado / saiu   iniciado
- a mais (foi citado, não está no gabarito): lavagem nasal com soro iniciado
- fato ausente: 7 dias|sete dias
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] duvida: Nariz entupido e dor no rosto há doze dias, com início como gripe e piora posterior. (ouvido com dúvida: doze)
- ponto para conferir [medio] inferido: Quadro de congestão nasal e dor facial em evolução há cerca de doze dias, com febre referida.
- ponto para conferir [medio] duvida: Quadro de congestão nasal e dor facial em evolução há cerca de doze dias, com febre referida. (ouvido com dúvida: doze)
- ponto para conferir [medio] pendencia: dose e posologia da amoxicilina não ficaram claras na gravação

```
S: Nariz entupido e dor no rosto há doze dias, com início como gripe e piora posterior. Referiu febre de trinta e oito ontem.
O: Temperatura aferida de trinta e sete vírgula seis. Dor à palpação nos seios maxilares e secreção amarelada na garganta.
A: Quadro de congestão nasal e dor facial em evolução há cerca de doze dias, com febre referida.
P: Amoxicilina. Lavagem nasal com soro três vezes ao dia. Orientado retorno se não melhorar em três dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Diabetes tipo 2 com hemoglobina glicada acima da meta.
- ponto para conferir [medio] pendencia: dose/posologia do aumento da metformina não foram ditas
- ponto para conferir [info] cadastro: Diabetes tipo 2 com hemoglobina glicada acima da meta.

```
S: Hemoglobina glicada 7,8, ainda acima. Refere ter exagerado nas festas.
O: PA 124/78 mmHg. Peso 74 kg.
A: Diabetes tipo 2 com hemoglobina glicada acima da meta.
P: Metformina ajustada. Reforçada dieta, com orientação para cortar refrigerante e doce. Hemoglobina glicada repetida em três meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.071)

- avisado: paracetamol esperado 750 mg 6/6h iniciado / saiu   iniciado
- avisado: ciclobenzaprina esperado 5 mg * iniciado / saiu   iniciado
- fato ausente: 7 dias|sete dias
- ponto para conferir [medio] duvida: Nega dor irradiada para a perna, formigamento, perda de força e alteração para urinar. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: dose e posologia do paracetamol foram ouvidas com dúvida
- ponto para conferir [medio] pendencia: dose da ciclobenzaprina foi ouvida com dúvida

```
LIVRE: Refere dor lombar após travar as costas ao carregar o filho no sábado. Nega dor irradiada para a perna, formigamento, perda de força e alteração para urinar. Lasegue negativo. Força preservada. Menciona lombalgia mecânica. Orientado paracetamol, ciclobenzaprina e compressa morna. Voltar se a dor descer para a perna.
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.042)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum iniciado
- ponto para conferir [medio] duvida: Abdome com dor leve no epigástrio. (ouvido com dúvida: epigastrio)
- ponto para conferir [medio] pendencia: dose do omeprazol não ficou clara na gravação
- ponto para conferir [medio] pendencia: dor leve no epigástrio foi ouvida com dúvida em 'epigastro'

```
S: Queimação no estômago há um mês, com piora quando come e à noite. Usa ibuprofeno quase todo dia para dor de cabeça. Nega sangue.
O: Abdome com dor leve no epigástrio. Pressão 126/80.
A: 
P: Suspenso ibuprofeno. Prescrito omeprazol em jejum por 8 semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em 8 semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.083)

- sem divergências

```
S: Refere dor de cabeça no fim do dia, em aperto bilateral. Refere estresse no trabalho. Nega náusea, piora com luz, alteração de força e alteração de visão.
O: Pressão arterial 122 por 80. Exame neurológico normal.
A: Cefaleia tensional.
P: Dipirona 1 grama se dor, até de 6 em 6 horas. Alongamento e pausas no trabalho. Retorno se piorar.
```

## 16-dpoc-exacerbacao (voz natural, 62.5 s, WER 0.351)

- faltou: prednisona
- sinal spo2: esperado 91.0 / saiu None
- sinal fr: esperado 22.0 / saiu None
- sinal fc: esperado 96.0 / saiu None
- fato ausente: escarro|expector
- fato ausente: nega + febre
- fato ausente: sibil
- ponto para conferir [medio] inferido: Quadro em acompanhamento por DPOC.
- ponto para conferir [medio] pendencia: descrição de "caroço"/"esverdeado" não ficou clara na gravação
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Paciente refere cansaço piorado há quatro dias.
O: 
A: Quadro em acompanhamento por DPOC.
P: Azitromicina 500 mg 1 vez ao dia por 3 dias. Tiotrópio mantido. Budesonida com formoterol 12 por 400, 1 inalação de 12 em 12 horas. Orientado pronto-socorro se a saturação em casa cair abaixo de 88 ou se piorar a falta de ar. Retorno em uma semana.
```

## 17-hipotireoidismo-levotiroxina (voz natural, 39.9 s, WER 0.509)

- faltou: levotiroxina
- sinal fc: esperado 62.0 / saiu None
- sinal peso: esperado 70.5 / saiu None
- fato ausente: 6 semanas|seis semanas
- ponto para conferir [medio] inferido: Não ficou clara a resposta sobre o uso da levotiroxina em jejum.
- ponto para conferir [medio] pendencia: resposta sobre uso da levotiroxina em jejum não ficou clara na gravação

```
LIVRE: TSH 8,2. T4 livre 0,8. Refere cansaço e mais frio.
Não ficou clara a resposta sobre o uso da levotiroxina em jejum.
```

## 18-lombalgia-doenca-renal (voz natural, 49.1 s, WER 0.262)

- avisado: paracetamol esperado 750 mg 6/6h iniciado / saiu  de 6/6h se dor, no máximo 4 cp/dia iniciado
- avisado: ciclobenzaprina esperado 5 mg * iniciado / saiu  à noite por 7 dias iniciado
- sinal pa_s: esperado 134.0 / saiu None
- sinal pa_d: esperado 84.0 / saiu None
- fato ausente: nega + febre|irradia
- fato ausente: 4 comprimidos|quatro comprimidos
- ponto para conferir [medio] inferido: Dor nas costas após esforço.
- ponto para conferir [medio] inferido: Doença renal crônica em acompanhamento.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: Dose do paracetamol foi ouvida com dúvida ('750 mg').
- ponto para conferir [medio] pendencia: Dose da ciclobenzaprina foi ouvida com dúvida ('5 mg').
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Dor nas costas após carregar caixas. Solicitou diclofenaco que tinha em casa. Refere doença nos rins. Última filtração foi 42.
O: Sem déficit.
A: Dor nas costas após esforço. Doença renal crônica em acompanhamento.
P: Orientado não usar diclofenaco / anti-inflamatório. Paracetamol com uso se dor, de 6/6h, no máximo 4 cp/dia. Ciclobenzaprina 5 mg à noite por 7 dias. Losartana continua.
```

## 19-dislipidemia-atorvastatina (voz natural, 39.3 s, WER 0.02)

- sem divergências
- ponto para conferir [medio] inferido: Dislipidemia em acompanhamento, com LDL elevado.

```
S: Refere exame com LDL 142, colesterol total 228 e triglicérides 160. Questionada sobre dor muscular, nega dor. Questionada sobre fraqueza, nega fraqueza.
O: Pressão arterial 118 por 76 mmHg. Peso 63 kg.
A: Dislipidemia em acompanhamento, com LDL elevado.
P: Aumentada atorvastatina para 40 mg à noite. Solicitado repetir perfil lipídico e enzimas do fígado em três meses.
```

## 20-enxaqueca-profilaxia (voz natural, 46.5 s, WER 0.375)

- faltou: propranolol
- sinal pa_s: esperado 112.0 / saiu None
- sinal pa_d: esperado 72.0 / saiu None
- sinal fc: esperado 76.0 / saiu None
- fato ausente: nega + asma
- fato ausente: anticoncep
- ponto para conferir [medio] pendencia: medicação de 40 mg duas vezes ao dia foi ouvida com dúvida e não foi possível identificar com segurança

```
LIVRE: Enxaqueca com frequência de umas seis vezes por mês, associada a enjoo e fotofobia. Orientada sumatriptana 50 mg na crise, com máximo de dois comprimidos por dia. Orientado fazer diário da dor e retorno em dois meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.0)

- avisado: colchicina esperado 0,5 mg 8/8h iniciado / saiu  de 8 em 8 horas, até melhorar, no máximo, por uma semana iniciado
- fato ausente: alopurinol + depois|apos
- ponto para conferir [medio] inferido: Hipertensão arterial em tratamento.
- ponto para conferir [medio] inferido: Hiperuricemia.
- ponto para conferir [medio] pendencia: dose da colchicina foi ouvida com dúvida: '0,5 miligrama'
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Paciente refere inchaço no dedão do pé direito desde a madrugada, com vermelhidão e dor importante ao encostar o lençol. Relata que é a primeira vez. Relata churrasco com cerveja no fim de semana.
O: Temperatura de 37,2°C. Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: Hipertensão arterial em tratamento. Hiperuricemia.
P: Colchicina por até uma semana, de 8 em 8 horas, até melhorar. Gelo local e repouso. Suspensa hidroclorotiazida. Iniciado anlodipino 5 mg 1 vez ao dia. Retorno em duas semanas.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.027)

- fato ausente: 35 + 30
- fato ausente: meio comprimido|2,5
- fato ausente: segunda + quinta
- ponto para conferir [medio] inferido: Anticoagulação com INR acima da meta.
- ponto para conferir [medio] cid: CID I48.91 não existe na tabela (descartado)
- ponto para conferir [medio] dose_longe: varfarina: 30 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: posologia exata da varfarina após o ajuste não ficou completamente clara na gravação
- ponto para conferir [info] cadastro: varfarina: 5 mg 30 mg por semana (dose do cadastro: confirme se não mudou)

```
S: INR 3,8, acima da meta de 2 a 3. Refere sangramento na gengiva ao escovar, com cessação espontânea. Nega sangue na urina. Nega sangue nas fezes e manchas roxas.
O: PA 128/76 mmHg. Frequência cardíaca 70, irregular.
A: Anticoagulação com INR acima da meta.
P: Repetir INR em uma semana. Varfarina ajustada para 30 mg por semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.13)

- fato ausente: menstrua + 7 dias|sete dias|intensa|forte
- ponto para conferir [medio] pendencia: dose de ferro do sulfato ferroso foi ouvida com dúvida: '40 miligramas'

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Anemia por falta de ferro. Prescrito sulfato ferroso, 1 comprimido de ferro 2 vezes ao dia, longe das refeições, com suco de laranja. Solicitado ultrassom transvaginal para investigar o sangramento. Orientado que pode escurecer as fezes. Repetir hemograma e ferritina em 2 meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.043)

- sinal peso: esperado 9.2 / saiu None
- fato ausente: 44
- ponto para conferir [medio] inferido: Peso e perímetro cefálico foram ditos com dúvida na gravação, sem valor seguro para registrar.
- ponto para conferir [medio] inferido: Seguimento de puericultura sem queixa relatada.
- ponto para conferir [medio] pendencia: peso não foi informado com segurança na gravação
- ponto para conferir [medio] pendencia: perímetro cefálico não foi informado com segurança na gravação
- ponto para conferir [info] cadastro: vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Mãe relata que a paciente está comendo papinha de legumes e fruta, e mama no peito. Peso e perímetro cefálico foram ditos com dúvida na gravação, sem valor seguro para registrar.
O: Peso não informado com segurança na gravação. Comprimento de 74 cm. Temperatura de 36,7 °C. Senta sem apoio e já engatinha. Está ótimo para a idade. Vacinas em dia.
A: Seguimento de puericultura sem queixa relatada.
P: Manter vitamina D 400 unidades por dia. Oferecer água entre as refeições. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.148)

- sinal peso: esperado 78.4 / saiu None
- fato ausente: 2 quilos|dois quilos|2 kg
- fato ausente: crepit
- ponto para conferir [medio] inferido: Insuficiência cardíaca com piora de edema e ortopneia.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1 vez ao dia (dose do cadastro: confirme se não mudou)

```
S: Paciente refere pernas inchadas de novo e dormir com dois travesseiros.
O: Pressão arterial 118/72 mmHg, frequência cardíaca 68 bpm. Edema de pernas 2+/4.
A: Insuficiência cardíaca com piora de edema e ortopneia. Hipertensão arterial em acompanhamento.
P: Furosemida ajustada para 40 mg 2 vezes ao dia, de manhã e no começo da tarde. Carvedilol 6,25 mg 2 vezes ao dia mantido. Espironolactona 25 mg e enalapril 10 mg 2 vezes ao dia mantidos. Orientado a pesar todo dia de manhã. Solicitados potássio e creatinina em 1 semana. Retorno em 2 semanas.
```

## 26-insonia-sem-benzodiazepinico (voz natural, 51.0 s, WER 0.039)

- avisado: trazodona esperado 50 mg * iniciado / saiu  à noite iniciado
- fato ausente: 3 meses|tres meses
- fato ausente: celular
- fato ausente: cafe
- fato ausente: terapia cognitiva|tcc
- fato ausente: 1 mes|um mes
- ponto para conferir [medio] pendencia: dose da trazodona não ficou clara na gravação, com menção a 50 miligramas

```
LIVRE: 
```

## 27-renovacao-de-receita (voz natural, 28.5 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Hipertensão arterial e hiperplasia prostática em seguimento, sem queixas no momento.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tansulosina: 0,4 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Vem apenas para renovar a receita. Relata que está tudo bem. Nega tontura, inchaço e dificuldade para urinar. Refere que urina bem com o remédio da próstata.
O: PA 132/80 mmHg. FC 70 bpm.
A: Hipertensão arterial e hiperplasia prostática em seguimento, sem queixas no momento.
P: Renovadas as medicações nas mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (voz natural, 45.6 s, WER 0.062)

- fato ausente: 180 + 220
- fato ausente: nega + hipoglic
- ponto para conferir [medio] inferido: Diabetes tipo 2 em seguimento.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em seguimento.
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Glicemias em jejum entre 180 e 120, com média de 182. Refere uso de NPH 20 de manhã e 10 à noite.
O: HbA1c 9,4. Pressão arterial 136 por 82.
A: Diabetes tipo 2 em seguimento.
P: NPH da noite ajustada para 14 unidades. NPH da manhã mantida em 20 unidades. Metformina mantida. Orientado anotar as glicemias em jejum. Retorno em um mês.
```

## 29-micose-cetoconazol (voz natural, 30.6 s, WER 0.033)

- fato ausente: prurido|coca
- ponto para conferir [medio] pendencia: dose do cetoconazol creme não foi dita

```
LIVRE: Paciente refere mancha vermelha pruriginosa na virilha há cerca de três semanas, com suor ao jogar bola. Descreve placa avermelhada com borda mais viva em ორივas virilhas. Foi dito tratar-se de micose. Prescrito cetoconazol creme, duas vezes ao dia por quatro semanas, mesmo após sumir. Orientado a secar bem a região, usar roupa de algodão e retornar se não melhorar em quatro semanas.
```

## 30-valor-corrigido (voz natural, 34.5 s, WER 0.019)

- sem divergências
- ponto para conferir [alto] duvida_grave: hidroclorotiazida: 25 ouvido com dúvida
- ponto para conferir [medio] duvida: Manter hidroclorotiazida 25 mg 1x/dia. (ouvido com dúvida: 25)
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: 
O: PA 140/90 mmHg em consulta; em casa semelhante. FC 76 bpm.
A: Pressão arterial um pouco acima da meta.
P: Manter hidroclorotiazida 25 mg 1x/dia. Reduzir o sal. Medir a pressão em casa duas vezes por semana. Retorno em dois meses com as medidas.
```

## 31-exame-em-silencio (voz natural, 78.4 s, WER 0.038)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum iniciado
- fato ausente: raio x|radiografia
- ponto para conferir [medio] inferido: Tosse seca há três semanas, sem febre, com azia noturna ocasional.
- ponto para conferir [medio] pendencia: dose de omeprazol não foi dita; "20mg" ouvido com dúvida
- ponto para conferir [medio] pendencia: garganta mencionada com dúvida na gravação

```
S: Tosse seca há três semanas. Nega febre. Nega rinorreia. Refere azia às vezes à noite. Nega tabagismo.
O: Pulmões limpos, sem sibilos. Saturação 98%.
A: Tosse seca há três semanas, sem febre, com azia noturna ocasional.
P: Foi orientado omeprazol e elevar a cabeceira da cama. Foi orientado retorno em quatro semanas. Se não houver melhora, será feito raio-x do tórax.
```
