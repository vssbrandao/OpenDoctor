# Avaliação da gravação — 2026-10-15 · gpt-4o-mini-transcribe + gpt-5.4-mini · prompt 2026-10-15.4

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.025 · remédios {'rem_certo': 47, 'rem_aviso': 6, 'rem_sem_aviso': 0, 'rem_falta': 9, 'rem_inventado': 0} · sinais 65/68 · CID 24/33 · fatos 163/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Tontura ao ortostatismo.
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 em meta.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso regular de losartana, metformina e remédio do colesterol. Mantém caminhada quatro vezes por semana, por cerca de trinta minutos. Relata tontura ao levantar da cama nesta semana, em duas ocasiões, com melhora rápida ao sentar. Nega desmaio, falta de ar e dor no peito. Relata glicemias em jejum entre 110 e 130 e nega hipoglicemias.
O: Pressão arterial de 128 por 82 mmHg e frequência cardíaca de 74 bpm. Peso de 86,8 kg e glicemia capilar de 108 mg/dL. Hemoglobina glicada de 6,9. Pés sem alterações referidas e pulsos presentes. Monofilamento com sensibilidade preservada.
A: Diabetes mellitus tipo 2 em meta. Tontura ao ortostatismo.
P: Manter os três remédios. Orientada a levantar devagar e sentar na cama por um minuto antes de ficar em pé. Solicitado exame de urina para os rins e ácido úrico. Retorno em três meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.008)

- fato ausente: 8,1|8.1
- ponto para conferir [medio] duvida: Refere uso de metformina 850 mg duas vezes ao dia, mas às vezes esquece a da noite. (ouvido com dúvida: duas, esquece)
- ponto para conferir [medio] inferido: Hipertensão arterial.
- ponto para conferir [medio] inferido: Diabetes tipo 2.
- ponto para conferir [medio] pendencia: valor exato da hemoglobina glicada não ficou claro na gravação por conter dúvida na transcrição

```
S: Paciente traz exames e refere que a hemoglobina glicada veio acima da meta. Refere uso de metformina 850 mg duas vezes ao dia, mas às vezes esquece a da noite.
O: Pressão arterial 152/94 mmHg. Frequência cardíaca 80 bpm. Peso 92 kg.
A: Hipertensão arterial. Diabetes tipo 2.
P: Aumentar losartana para 100 mg 1 vez ao dia. Iniciar empagliflozina 10 mg 1 comprimido de manhã. Manter metformina 850 mg 2 vezes ao dia. Orientado a beber bastante água e caprichar na higiene íntima por risco de infecção urinária com o novo remédio. Solicitados creatinina e potássio em 30 dias. Retorno em dois meses.
```

## 03-fibrilacao-rivaroxabana (voz natural, 80.2 s, WER 0.023)

- avisado: rivaroxabana esperado 20 mg 1x/dia iniciado / saiu  1x/dia com o jantar iniciado
- fato ausente: nega + sincope|desmai
- ponto para conferir [medio] inferido: Hipertensão arterial em seguimento.
- ponto para conferir [medio] cid: CID I48.9 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: dose da rivaroxabana foi dita com dúvida ('20 miligramas')
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere palpitações há uma semana, com cansaço ao subir escadas. Nega dor no peito e falta de ar ao deitar.
O: Pulso irregular, frequência 112 bpm e pressão 138/86 mmHg. Eletrocardiograma com fibrilação atrial.
A: Fibrilação atrial. Hipertensão arterial em seguimento.
P: Iniciar rivaroxabana, com o jantar, para prevenir derrame. Suspender AAS. Iniciar metoprolol succinato 50 mg 1x/dia para controle da frequência cardíaca. Manter anlodipino. Solicitar ecocardiograma, TSH e função renal. Retorno em quatro semanas. Orientado procurar pronto-socorro se houver sangramento que não para, fezes pretas ou urina com sangue.
```

## 04-pediatria-otite (voz natural, 78.9 s, WER 0.063)

- avisado: amoxicilina esperado 8 ml 12/12h iniciado / saiu   iniciado
- faltou: paracetamol
- fato ausente: abaulad
- ponto para conferir [medio] duvida: Ouvido direito vermelho e abalado. (ouvido com dúvida: abalado)
- ponto para conferir [medio] pendencia: dose/concentração da amoxicilina não ficou clara na gravação
- ponto para conferir [medio] pendencia: paracetamol ouvido com dúvida; não foi registrado como medicação ativa
- ponto para conferir [medio] pendencia: posologia completa da amoxicilina não ficou clara na gravação

```
S: Febre desde ontem, chegando a 38,5. Choro com dor no ouvido direito. Nega vômito, diarreia e falta de ar. Refere estar mais molinho e comendo pouco.
O: Peso de 16 quilos. Temperatura atual de 38,2. Ouvido direito vermelho e abalado. Ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações.
A: Otite média aguda.
P: Amoxicilina iniciada. Orientado retornar antes se a febre não baixar após 48 horas de antibiótico ou se ficar prostrado. Retorno em 10 dias.
```

## 05-prenatal-28-semanas (voz natural, 68.3 s, WER 0.01)

- faltou: sulfato ferroso
- ponto para conferir [medio] pendencia: medicação para ferro foi citada com dúvida em 'sulfato ferroso'; dose e posologia do ferro foram ditas como 40 miligramas de ferro, 1 comprimido por dia, longe do café e do leite
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Gestante com 28 semanas. Refere bebê mexendo bastante. Relata um pouco de azia à noite. Nega sangramento, perda de líquido e contrações.
O: Pressão 110/70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. Batimentos fetais 144 bpm.
A: Gestação com 28 semanas. Azia noturna.
P: Solicitada curva glicêmica / TTG de 75 gramas. Orientada vacina DTPA no posto. Orientadas medidas dietéticas para azia: refeições menores e evitar deitar logo após comer. Retorno em duas semanas.
```

## 06-idoso-queda-desprescricao (voz natural, 74.5 s, WER 0.014)

- sem divergências
- ponto para conferir [alto] numero: PA sentado 138/78 mmHg e em pé 112/70 mmHg.
- ponto para conferir [alto] duvida_grave: diazepam: 5 ouvido com dúvida
- ponto para conferir [alto] duvida_grave: anlodipino: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [alto] duvida_grave: anlodipino: 5 ouvido com dúvida
- ponto para conferir [medio] duvida: Relata escurecimento da vista ao levantar para ir ao banheiro. (ouvido com dúvida: para)
- ponto para conferir [medio] duvida: Usa diazepam 10 toda noite há uns 20 anos. (ouvido com dúvida: diazepam)
- ponto para conferir [medio] inferido: Queda associada a tontura ao levantar, com escurecimento visual.
- ponto para conferir [medio] duvida: Reduzir diazepam para 5 mg por duas semanas e depois parar. (ouvido com dúvida: 5)
- ponto para conferir [medio] duvida: Manter anlodipino e sinvastatina. (ouvido com dúvida: anlodipino)
- ponto para conferir [medio] vital_longe: pa_s = 112: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 70: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] dose_longe: diazepam: 5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] dose_longe: diazepam: 2 está no trecho, mas não junto do nome do remédio
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Queda no banheiro de madrugada na semana passada, com trauma no braço. Relata escurecimento da vista ao levantar para ir ao banheiro. Usa diazepam 10 toda noite há uns 20 anos.
O: PA sentado 138/78 mmHg e em pé 112/70 mmHg. FC 72 bpm. Peso 61 kg. Braço com apenas hematoma, sem dor para mexer.
A: Queda associada a tontura ao levantar, com escurecimento visual. Uso crônico de diazepam com risco de queda. Sem mais sintomas gástricos referidos.
P: Reduzir diazepam para 5 mg por duas semanas e depois parar. Suspender omeprazol. Manter anlodipino e sinvastatina. Orientadas medidas para dormir: luz baixa à noite, evitar café à tarde e deixar uma luz acesa no caminho do banheiro. Retorno em um mês.
```

## 07-depressao-sertralina (voz natural, 62.9 s, WER 0.01)

- avisado: sertralina esperado 100 mg * ajustado / saiu  de manhã ajustado
- fato ausente: 15
- ponto para conferir [medio] duvida: Escore do questionário de hoje: quinze pontos, compatível com depressão moderada. (ouvido com dúvida: quinze)
- ponto para conferir [medio] inferido: Episódio depressivo em acompanhamento, com melhora parcial e sintomas residuais.
- ponto para conferir [medio] duvida: Sertralina ajustada para 100 mg de manhã. (ouvido com dúvida: para)
- ponto para conferir [medio] duvida: Encaminhada para psicoterapia. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: dose da sertralina ajustada para 100 miligramas veio com dúvida na gravação
- ponto para conferir [medio] pendencia: escore do questionário de hoje veio com dúvida na gravação: quinze pontos

```
S: Refere um pouco de melhora desde início da sertralina há dois meses, porém mantém falta de vontade para fazer as coisas. Nega ideias de se machucar ou de morrer. Diz que pensa nos filhos. Relata sono ruim e choro fácil. Refere um pouco de enjoo no começo da sertralina, já resolvido. Escore do questionário de hoje: quinze pontos, compatível com depressão moderada.
O: 
A: Episódio depressivo em acompanhamento, com melhora parcial e sintomas residuais. Depressão moderada pelo questionário de hoje.
P: Sertralina ajustada para 100 mg de manhã. Encaminhada para psicoterapia. Orientada a procurar ajuda imediata se surgir pensamento de se machucar; informado contato 188. Retorno em quatro semanas.
```

## 08-asma-crise (voz natural, 68.8 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Asma em exacerbação.

```
S: Paciente com falta de ar desde ontem e chiado importante. Usou a bombinha umas seis vezes hoje, sem resolução. Referiu gripe na semana passada.
O: Saturação 93%. Frequência respiratória 24 irpm. Frequência cardíaca 104 bpm. Sibilos em ambos os pulmões. Após três séries de salbutamol com espaçador, saturação 97% e sibilos bem menores.
A: Asma em exacerbação.
P: Feito salbutamol, 4 jatos a cada 20 minutos, três vezes com espaçador. Prescrita prednisolona 40 mg uma vez ao dia por cinco dias. Iniciada budesonida com formoterol, 2 jatos de 12 em 12 horas, todos os dias. Orientado retorno em uma semana. Orientado procurar pronto-socorro se piorar a falta de ar ou se a boca ficar roxa.
```

## 09-meio-comprimido-captopril (voz natural, 47.4 s, WER 0.0)

- faltou: hidroclorotiazida
- ponto para conferir [medio] inferido: Hipertensão arterial com controle inadequado.
- ponto para conferir [medio] pendencia: medicação 'hidroclorotiazida' e dose '25 miligramas' não ficaram seguras na gravação

```
S: Paciente refere pressão em casa sempre alta, com valores de 160 e 150. Refere uso de meio comprimido de captopril 25 mg por orientação de terceiros.
O: Pressão arterial na consulta: 156/92 mmHg. Frequência cardíaca: 78 bpm.
A: Hipertensão arterial com controle inadequado.
P: Captopril 25 mg ajustado para 1 comprimido inteiro 2 vezes ao dia. Orientada aferição da pressão em casa e anotação das medidas. Retorno em 4 semanas com as medidas.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.022)

- sem divergências
- ponto para conferir [medio] duvida: Refere ardência para urinar há dois dias e vontade toda hora. (ouvido com dúvida: ardencia)
- ponto para conferir [medio] duvida: Temperatura de 36,8. (ouvido com dúvida: temperatura)
- ponto para conferir [medio] duvida: Punho-percussão negativa. (ouvido com dúvida: punho)

```
S: Refere ardência para urinar há dois dias e vontade toda hora. Nega febre, dor nas costas e sangue na urina. Refere alergia à sulfa.
O: Temperatura de 36,8. Abdômen sem dor. Punho-percussão negativa.
A: 
P: Prescrita nitrofurantoína 100 mg de seis em seis horas por cinco dias. Orientada hidratação e retorno se febre ou dor nas costas. Sem necessidade de retorno se melhorar.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- a mais (foi citado, não está no gabarito): lavagem nasal com soro iniciado
- ponto para conferir [alto] numero: Temperatura aferida: 37,6.
- ponto para conferir [alto] numero: temp = 37,6 não encontrado no trecho citado
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] inferido: Quadro de vias aéreas superiores com sintomas nasais e dor facial há 12 dias, com febre recente.

```
S: Paciente com nariz entupido e dor no rosto há 12 dias. Refere início como gripe, com piora posterior. Teve febre ontem, 38.
O: Temperatura aferida: 37,6. Dor à palpação nos seios maxilares e secreção amarelada na garganta.
A: Quadro de vias aéreas superiores com sintomas nasais e dor facial há 12 dias, com febre recente.
P: Amoxicilina 875 mg de 12 em 12 horas por 7 dias. Lavagem nasal com soro 3 vezes ao dia. Orientado retorno se não melhorar em 3 dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.021)

- sem divergências
- ponto para conferir [medio] inferido: Diabetes tipo 2 em controle acima da meta.
- ponto para conferir [medio] pendencia: dose e posologia do aumento da metformina não foram ditas
- ponto para conferir [medio] pendencia: orientação sobre cortar refrigerante doce ficou incerta na gravação por causa do
- ponto para conferir [info] cadastro: Diabetes tipo 2 em controle acima da meta.

```
S: Paciente refere que nas festas exagerou.
O: Hemoglobina glicada 7,8, ainda acima. PA 124/78 mmHg. Peso 74 kg.
A: Diabetes tipo 2 em controle acima da meta.
P: Aumentar a metformina. Reforçar a dieta. Repetir a glicada em três meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.071)

- faltou: paracetamol
- faltou: ciclobenzaprina
- fato ausente: 7 dias|sete dias
- fato ausente: compressa|calor
- ponto para conferir [alto] numero: Refere lombalgia após travar as costas ao carregar o filho no sábado. Nega dor descendo para a perna, formigamento, perda de força e alteração urinária. (src [2,3])
- ponto para conferir [alto] numero: Ao exame referido na consulta, Lasegue negativo e força preservada. (src [3])
- ponto para conferir [alto] numero: Impressão de lombalgia mecânica. Orientado retorno se a dor descer para a perna. (src [4])
- ponto para conferir [medio] duvida: Ao exame referido na consulta, Lasegue negativo e força preservada. (src [3]) (ouvido com dúvida: lasegue)
- ponto para conferir [medio] pendencia: medicações citadas com pouca certeza na gravação: 'paracetamol 750 mg de seis em seis horas', 'Cibor', 'ciclobenzaprina 5 mg à noite por sete dias'; palavra 'compressa morna' foi dita sem dúvida suficiente para registrar como medicação/conduta padronizada

```
LIVRE: Refere lombalgia após travar as costas ao carregar o filho no sábado. Nega dor descendo para a perna, formigamento, perda de força e alteração urinária. (src [2,3]) Ao exame referido na consulta, Lasegue negativo e força preservada. (src [3]) Impressão de lombalgia mecânica. Orientado retorno se a dor descer para a perna. (src [4])
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.056)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum por 8 semanas iniciado
- fato ausente: nega + sangue|melena|hematem
- ponto para conferir [medio] duvida: Abdômen com dor leve no epigástrio, sem outros achados. (ouvido com dúvida: abdomen)
- ponto para conferir [medio] inferido: Uso frequente de ibuprofeno com queixa de queimação epigástrica.
- ponto para conferir [medio] pendencia: dose do omeprazol não ficou clara na gravação

```
S: Queimação no estômago há um mês, pior quando come e à noite. Usa ibuprofeno quase todo dia para dor de cabeça.
O: Abdômen com dor leve no epigástrio, sem outros achados. Pressão arterial 126 por 80.
A: Uso frequente de ibuprofeno com queixa de queimação epigástrica.
P: Suspenso ibuprofeno. Iniciado omeprazol em jejum por 8 semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em 8 semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.0)

- avisado: dipirona esperado 1 g 6/6h iniciado / saiu   iniciado
- ponto para conferir [medio] pendencia: dose e posologia da dipirona não ficaram claras na gravação

```
S: Cefaleia no fim do dia, em aperto bilateral. Nega náusea, piora com luz, alteração de força ou de visão. Refere estresse no trabalho.
O: Pressão arterial 122/80. Exame neurológico normal.
A: Cefaleia tensional.
P: Dipirona. Alongamento e pausas no trabalho. Retorno se piorar.
```

## 16-dpoc-exacerbacao (voz natural, 62.5 s, WER 0.043)

- faltou: azitromicina
- ponto para conferir [alto] duvida_grave: budesonida com formoterol: 12 ouvido com dúvida
- ponto para conferir [medio] duvida: Cansaço piorou há quatro dias. Escarro esverdeado e aumentado. Nega febre e inchaço nas pernas. (ouvido com dúvida: escarro)
- ponto para conferir [medio] inferido: DPOC em manejo na consulta.
- ponto para conferir [medio] duvida: Budesonida com formoterol 1 inalação de 12 em 12 horas. (ouvido com dúvida: 12)
- ponto para conferir [medio] pendencia: nome e dose de "Eazitromicina" com dúvida na gravação
- ponto para conferir [medio] pendencia: concentração de "budesonida com formoterol 12x400" com dúvida na gravação
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Cansaço piorou há quatro dias. Escarro esverdeado e aumentado. Nega febre e inchaço nas pernas. Saturação 91%. Frequência respiratória 22. Frequência cardíaca 96. Sibilos esparsos.
O: Saturação 91%. Frequência respiratória 22. Frequência cardíaca 96. Sibilos esparsos.
A: DPOC em manejo na consulta.
P: Prednisona 40 mg 1 vez ao dia por 5 dias. Azitromicina 500 mg 1 vez ao dia por 3 dias. Tiotrópio mantido. Budesonida com formoterol 1 inalação de 12 em 12 horas. Orientado pronto-socorro se saturação em casa cair abaixo de 88 ou se piorar a falta de ar. Retorno em uma semana.
```

## 17-hipotireoidismo-levotiroxina (voz natural, 39.9 s, WER 0.0)

- sinal fc: esperado 62.0 / saiu None
- ponto para conferir [medio] pendencia: frequência cardíaca foi dita com dúvida: 'sessenta e dois'

```
LIVRE: TSH 8,2 e T4 livre 0,8. Refere cansaço e mais frio. Informa uso diário de levotiroxina em jejum, cerca de meia hora antes do café. Peso 70,5 kg. Tireoide sem nódulos à palpação. Levotiroxina ajustada para 75 microgramas em jejum. Repetir TSH em seis semanas.
```

## 18-lombalgia-doenca-renal (voz natural, 49.1 s, WER 0.071)

- faltou: paracetamol
- faltou: ciclobenzaprina
- fato ausente: 42
- fato ausente: 4 comprimidos|quatro comprimidos
- fato ausente: 7 dias|sete dias
- ponto para conferir [medio] inferido: Dor lombar após esforço, com achado compatível com acometimento muscular.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: medicação prescrita para dor ficou inaudível: "para acetamol" e "ciclobenzaprina cinco miligramas à noite por sete dias"
- ponto para conferir [medio] pendencia: confirmar nome exato do analgésico e do relaxante muscular ou se houve apenas orientação verbal
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Dor nas costas após carregar caixas. Pede orientação sobre diclofenaco em casa. Nega irradiação para a perna. Nega febre.
O: PA 134 por 84. Dor à palpação da musculatura lombar. Sem déficit.
A: Dor lombar após esforço, com achado compatível com acometimento muscular.
P: Orientado a não usar diclofenaco/anti-inflamatório, por risco de piora renal. Losartana continua.
```

## 19-dislipidemia-atorvastatina (voz natural, 39.3 s, WER 0.0)

- fato ausente: nega + dor muscular|mialgia
- ponto para conferir [medio] inferido: Dislipidemia em acompanhamento.
- ponto para conferir [medio] duvida: Triglicérides 160, com leitura incerta no áudio. (ouvido com dúvida: triglicerides)
- ponto para conferir [medio] inferido: Dislipidemia.
- ponto para conferir [medio] pendencia: triglicérides foi ouvido com dúvida no áudio
- ponto para conferir [medio] pendencia: não foram ditos valores de pressão arterial sistólica/diastólica além de 118 por 76

```
S: Dislipidemia em acompanhamento. Refere nenhuma dor muscular.
O: LDL 142, colesterol total 228. Triglicérides 160, com leitura incerta no áudio.
A: Dislipidemia.
P: Aumentada atorvastatina para 40 miligramas à noite. Repetir perfil lipídico e enzimas do fígado em três meses.
```

## 20-enxaqueca-profilaxia (voz natural, 46.5 s, WER 0.047)

- fato ausente: anticoncep
- ponto para conferir [alto] remedio: propranolol: não aparece na fala nem no cadastro
- ponto para conferir [medio] duvida: Enxaqueca com frequência de cerca de seis vezes por mês, com enjoo e fotofobia. Nega asma. Pressão arterial 112 por 72 mmHg e frequência cardíaca 76 bpm. Exame neurológico normal. Iniciada prevenção com propranolol 40 mg duas vezes ao dia. Orientado sumatriptana 50 mg na crise, no máximo dois comprimidos por dia. Orientado diário da dor. Retorno em dois meses. (ouvido com dúvida: pressao, duas)
- ponto para conferir [medio] dose_longe: propranolol: 40 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] dose_longe: propranolol: 2 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: expressão 'enxaqueca está' com baixa certeza na gravação

```
LIVRE: Enxaqueca com frequência de cerca de seis vezes por mês, com enjoo e fotofobia. Nega asma. Pressão arterial 112 por 72 mmHg e frequência cardíaca 76 bpm. Exame neurológico normal. Iniciada prevenção com propranolol 40 mg duas vezes ao dia. Orientado sumatriptana 50 mg na crise, no máximo dois comprimidos por dia. Orientado diário da dor. Retorno em dois meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.0)

- avisado: colchicina esperado 0,5 mg 8/8h iniciado / saiu 0,5 mg  iniciado
- ponto para conferir [medio] inferido: Queda do controle da hipertensão com necessidade de troca de hidroclorotiazida por amlodipino.
- ponto para conferir [medio] inferido: Quadro inflamatório agudo na primeira articulação do pé direito, com hiperuricemia referida.
- ponto para conferir [medio] duvida: Colchicina 0,5 mg de oito em oito horas até melhorar, no máximo por uma semana. (ouvido com dúvida: oito)
- ponto para conferir [medio] pendencia: temperatura ouvida com dúvida na transcrição
- ponto para conferir [medio] pendencia: posologia da colchicina ficou com dúvida em 'oito em oito horas'
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Paciente relata início súbito de inchaço no dedão do pé direito de madrugada, com vermelhidão e dor ao encostar o lençol. Refere que foi a primeira vez. Relata churrasco com cerveja no fim de semana.
O: Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: Queda do controle da hipertensão com necessidade de troca de hidroclorotiazida por amlodipino. Quadro inflamatório agudo na primeira articulação do pé direito, com hiperuricemia referida.
P: Colchicina 0,5 mg de oito em oito horas até melhorar, no máximo por uma semana. Gelo no local e repouso. Trocar hidroclorotiazida por anlodipino 5 mg uma vez ao dia. Considerar alopurinol após a crise passar. Retorno em duas semanas.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.013)

- fato ausente: 35 + 30
- ponto para conferir [alto] numero: varfarina: 5 mg todos os dias; meio comprimido às segundas e quintas
- ponto para conferir [medio] inferido: Anticoagulação com INR acima da meta.
- ponto para conferir [medio] sem_origem: Fibrilação atrial em seguimento.
- ponto para conferir [medio] cid: CID I48.91 não existe na tabela (descartado)
- ponto para conferir [info] cadastro: varfarina: 5 mg todos os dias; meio comprimido às segundas e quintas (dose do cadastro: confirme se não mudou)

```
S: INR 3,8, acima da meta de 2 a 3. Relata sangramento na gengiva ao escovar, com parada espontânea. Nega sangue nas fezes e manchas roxas.
O: PA 128/76 mmHg. FC 70 bpm. INR 3,8.
A: Anticoagulação com INR acima da meta.
P: Ajustada a varfarina para 30 mg por semana, com 5 mg todos os dias e meio comprimido às segundas e quintas. Repetir INR em 1 semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.029)

- sem divergências

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Refere anemia por falta de ferro. Menstruação muito forte, por cerca de sete dias.
Iniciado sulfato ferroso, 1 comprimido de 40 mg de ferro, 2 vezes ao dia, longe das refeições, com suco de laranja. Solicitado ultrassom transvaginal para investigação do sangramento. Orientado que pode escurecer as fezes. Programada repetição de hemograma e ferritina em dois meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.029)

- sinal peso: esperado 9.2 / saiu None
- sinal temp: esperado 36.7 / saiu None
- fato ausente: 44
- fato ausente: senta
- ponto para conferir [alto] vital: peso = 9,2 kg: formato inválido (descartado)
- ponto para conferir [alto] vital: altura = 74 cm: formato inválido (descartado)
- ponto para conferir [alto] vital: temp = 36,7 °C: formato inválido (descartado)
- ponto para conferir [medio] duvida: Estatuto referido como ótimo para a idade. (ouvido com dúvida: para)
- ponto para conferir [medio] inferido: Crescimento e desenvolvimento referidos como adequados para a idade.
- ponto para conferir [medio] duvida: Crescimento e desenvolvimento referidos como adequados para a idade. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Perímetro cefálico foi ouvido com dúvida: 'quarenta e quatro'.

```
S: Está comendo papinha de legumes e fruta e mama no peito.
O: Peso de 9 quilos e 200 gramas. Comprimento de 74 centímetros. Temperatura de 36,7 °C. Sem apoio e já engatinha. Estatuto referido como ótimo para a idade. Vacinas em dia.
A: Crescimento e desenvolvimento referidos como adequados para a idade.
P: Manter vitamina D 400 unidades por dia. Oferecer água entre as refeições. Retorno com 12 meses. Próxima vacina aos 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.034)

- fato ausente: crepit
- ponto para conferir [alto] duvida_grave: carvedilol: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [alto] duvida_grave: enalapril: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] inferido: Quadro de congestão com edema de pernas, ortopneia e ganho de peso.
- ponto para conferir [medio] duvida: Carvedilol, espironolactona e enalapril mantidos. (ouvido com dúvida: carvedilol, enalapril)
- ponto para conferir [medio] pendencia: Nomes de carvedilol e enalapril foram ouvidos com dúvida na gravação.

```
S: Refere pernas inchadas de novo e dorme com dois travesseiros. Relata ganho de peso de uns dois quilos na semana.
O: PA 118/72 mmHg. FC 68 bpm. Peso 78,4 kg. Edema de pernas duas cruzes em quatro.
A: Quadro de congestão com edema de pernas, ortopneia e ganho de peso.
P: Furosemida ajustada para 40 mg duas vezes ao dia, de manhã e no começo da tarde. Carvedilol, espironolactona e enalapril mantidos. Orientado pesar todo dia de manhã. Solicitados potássio e creatinina em uma semana. Retorno em duas semanas.
```

## 26-insonia-sem-benzodiazepinico (voz natural, 51.0 s, WER 0.013)

- sem divergências

```
LIVRE: Insônia há três meses, com dificuldade para dormir e pensamentos relacionados ao trabalho ao deitar. Refere uso de celular até tarde e ingestão de café em torno de cinco xícaras por dia. Orientada a reduzir uso de celular fora do quarto e limitar café até o almoço. Prescrita trazodona 50 mg à noite. Encaminhada para terapia cognitiva para insônia. Retorno em um mês.
```

## 27-renovacao-de-receita (voz natural, 28.5 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Renovação de receitas, com manutenção das medicações habituais nas mesmas doses.
- ponto para conferir [medio] cid: CID N40.0 não existe na tabela (descartado)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tansulosina: 0,4 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Consulta para renovar receita. Paciente refere que está tudo bem e sem queixas. Nega tontura, inchaço e dificuldade para urinar. Refere que urina bem com o remédio da próstata.
O: Pressão arterial 132 por 80. Frequência cardíaca 70.
A: Renovação de receitas, com manutenção das medicações habituais nas mesmas doses.
P: Renovadas as medicações nas mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (voz natural, 45.6 s, WER 0.046)

- fato ausente: 180 + 220
- fato ausente: nega + hipoglic
- ponto para conferir [alto] numero: Refere glicemias em jejum entre cento e oitenta e cento e vinte e oitenta e dois.
- ponto para conferir [medio] duvida: Refere glicemias em jejum entre cento e oitenta e cento e vinte e oitenta e dois. (ouvido com dúvida: cento)
- ponto para conferir [medio] inferido: Diabetes tipo 2 em controle inadequado.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em controle inadequado.
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere glicemias em jejum entre cento e oitenta e cento e vinte e oitenta e dois. Nega tremor e suor frio.
O: Hemoglobina glicada 9,4. Pressão arterial 136 por 82.
A: Diabetes tipo 2 em controle inadequado.
P: Ajuste da insulina NPH da noite para 14 unidades. Manter insulina NPH de manhã em 20 unidades. Manter metformina. Orientado anotar as glicemias em jejum. Retorno em um mês.
```

## 29-micose-cetoconazol (voz natural, 30.6 s, WER 0.1)

- faltou: cetoconazol
- fato ausente: prurido|coca
- ponto para conferir [medio] pendencia: remédio ouvido com dúvida em [2]; nome não ficou claro na gravação

```
LIVRE: Mancha vermelha pruriginosa na virilha há cerca de três semanas. Relata suor com prática de futebol. Placa avermelhada, com borda mais viva, em ambas as virilhas. Diagnóstico de micose. Orientado a secar bem a região, usar roupa de algodão e retornar se não melhorar em quatro semanas. Uso de creme ouvido com dúvida na gravação não foi registrado.
```

## 30-valor-corrigido (voz natural, 34.5 s, WER 0.038)

- sem divergências
- ponto para conferir [alto] duvida_grave: hidroclorotiazida: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [alto] duvida_grave: hidroclorotiazida: 25 ouvido com dúvida
- ponto para conferir [medio] duvida: Manter hidroclorotiazida 25 mg 1x/dia. (ouvido com dúvida: hidroclorotiazida, 25)
- ponto para conferir [medio] pendencia: medicamento e dose ouvidos com dúvida na gravação: 'Hidroclorotiazida 25mg'
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Hipertensão arterial em acompanhamento. Refere pressão em casa parecida.
O: PA 140/90 mmHg. FC 76 bpm.
A: Pressão arterial acima da meta.
P: Manter hidroclorotiazida 25 mg 1x/dia. Reduzir o sal. Medir a pressão em casa duas vezes por semana. Retorno em dois meses com as medidas.
```

## 31-exame-em-silencio (voz natural, 78.4 s, WER 0.013)

- fato ausente: raio x|radiografia

```
S: Tosse seca há três semanas. Nega febre. Nega tabagismo. Refere azia às vezes à noite. Nega nariz escorrendo.
O: Pulmões limpos, sem sibilos. Garganta sem alterações. Saturação de 98%.
A: Quadro sugestivo de refluxo.
P: Iniciado omeprazol 20 mg em jejum por 4 semanas. Orientada elevação da cabeceira da cama. Se não melhorar, realizar raio-X de tórax. Retorno em 4 semanas.
```
