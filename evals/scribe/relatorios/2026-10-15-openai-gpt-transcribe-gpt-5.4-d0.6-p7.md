# Avaliação da gravação — 2026-10-15 · gpt-transcribe + gpt-5.4 · prompt 2026-10-15.7

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.019 · remédios {'rem_certo': 59, 'rem_aviso': 1, 'rem_sem_aviso': 0, 'rem_falta': 2, 'rem_inventado': 0} · sinais 68/68 · CID 28/33 · fatos 173/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.01)

- sem divergências
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 na meta.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso regular de losartana, metformina e medicação do colesterol. Refere caminhada 4 vezes por semana, por cerca de 30 minutos. Refere 2 episódios de tontura ao levantar da cama nesta semana. Refere que a tontura passa em menos de 1 minuto ao sentar. Nega desmaio. Nega dor no peito e falta de ar. Refere glicemias em jejum em casa entre 110 e 130 mg/dL. Nega episódios de hipoglicemia.
O: PA 128x82 mmHg. FC 74 bpm. Peso 86,8 kg. Glicemia capilar 108 mg/dL. Coração e pulmões sem alterações ao exame. Pés sem alterações, com pulsos presentes. Sensibilidade preservada ao monofilamento. Hemoglobina glicada 6,9%.
A: Diabetes mellitus tipo 2 na meta. Queixa de tontura ao levantar.
P: Mantidos losartana, metformina e atorvastatina. Orientada a levantar devagar e sentar na cama por 1 minuto antes de ficar em pé. Solicitado exame de urina para os rins. Solicitado ácido úrico. Retorno em 3 meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.008)

- fato ausente: 30 dias
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento na consulta.
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em acompanhamento na consulta.
- ponto para conferir [medio] inferido: Ajustada losartana de 50 mg 1x/dia para 100 mg 1x/dia.
- ponto para conferir [info] cadastro: Ajustada losartana de 50 mg 1x/dia para 100 mg 1x/dia.

```
S: Refere que os exames não vieram muito bons. Refere uso de metformina 850 mg duas vezes ao dia, com esquecimento ocasional da dose da noite. Pergunta sobre cuidados com o novo medicamento.
O: Hemoglobina glicada 8,1. Pressão arterial 152x94 mmHg. Frequência cardíaca 80 bpm. Peso 92 kg.
A: Hemoglobina glicada acima da meta. Hipertensão arterial em acompanhamento na consulta. Diabetes mellitus tipo 2 em acompanhamento na consulta.
P: Ajustada losartana de 50 mg 1x/dia para 100 mg 1x/dia. Iniciada empagliflozina 10 mg, um comprimido de manhã. Mantida metformina 850 mg duas vezes ao dia. Orientado tentar não esquecer a dose noturna da metformina. Orientado beber bastante água e caprichar na higiene íntima. Informado que o novo remédio pode dar infecção urinária. Solicitados creatinina e potássio para daqui a trinta dias. Retorno em dois meses.
```

## 03-fibrilacao-rivaroxabana (voz natural, 80.2 s, WER 0.008)

- fato ausente: nega + sincope|desmai
- ponto para conferir [medio] inferido: Hipertensão arterial.
- ponto para conferir [medio] inferido: Mantido anlodipino 5 mg 1 vez ao dia.
- ponto para conferir [medio] cid: CID I48.9 não existe na tabela do DATASUS: usado I48 (Flutter e fibrilação atrial)
- ponto para conferir [medio] pendencia: Resposta sobre desmaio não ficou clara na gravação.
- ponto para conferir [info] cadastro: Mantido anlodipino 5 mg 1 vez ao dia.
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere coração disparando há 1 semana, com palpitações. Refere cansar mais para subir escada. Nega dor no peito. Nega falta de ar ao deitar.
O: Pulso irregular. Frequência cardíaca 112 bpm. Pressão arterial 138x86 mmHg. Eletrocardiograma com fibrilação atrial.
A: Fibrilação atrial. Hipertensão arterial.
P: Iniciada rivaroxabana 20 mg 1 vez ao dia, junto com o jantar. Suspenso AAS. Iniciado metoprolol succinato 50 mg 1 vez ao dia. Mantido anlodipino 5 mg 1 vez ao dia. Solicitado ecocardiograma. Solicitados TSH e função dos rins. Orientado procurar pronto-socorro se sangramento que não para, fezes pretas ou urina com sangue. Retorno em 4 semanas.
```

## 04-pediatria-otite (voz natural, 78.9 s, WER 0.048)

- sem divergências

```
S: Paciente com febre desde ontem, com pico referido de 38,5 °C, e chorando com dor no ouvido direito. Nega vômito, diarreia e falta de ar. Paciente mais molinho e comendo pouco.
O: Peso 16 kg. Temperatura 38,2 °C. Ouvido direito vermelho e abaulado. Ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações.
A: Otite média aguda.
P: Iniciada amoxicilina 250 mg/5 mL, 8 mL de 12 em 12 horas por 10 dias. Prescrito paracetamol gotas, 16 gotas a cada 6 horas, se precisar, para febre ou dor. Orientado retorno antes se mantiver febre após 48 horas de antibiótico ou se ficar prostrado. Retorno em 10 dias.
```

## 05-prenatal-28-semanas (voz natural, 68.3 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Peso 68,4 kg.
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere 28 semanas de gestação. Refere movimentos fetais presentes, mexendo bastante. Refere um pouco de azia à noite. Nega sangramento, perda de líquido e contrações.
O: Pressão arterial 110x70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. Batimentos cardíacos fetais 144 bpm.
A: Gestação com 28 semanas. Azia noturna.
P: Iniciado sulfato ferroso 40 miligramas de ferro, um comprimido por dia, longe do café e do leite. Suspenso ácido fólico. Solicitada curva glicêmica, TOTG de 75 gramas. Orientada vacina DTPA no posto. Orientadas refeições menores e evitar deitar logo após comer para azia. Retorno em duas semanas.
```

## 06-idoso-queda-desprescricao (voz natural, 74.5 s, WER 0.022)

- fato ausente: vista escure|tontura
- fato ausente: em pe + 112
- ponto para conferir [medio] vital_longe: pa_s = 112: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 70: o número está no trecho, mas não junto de PA
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente relata queda no banheiro de madrugada na semana passada, após levantar para ir ao banheiro, com escurecimento visual antes da queda. Refere uso de diazepam 10 mg todas as noites. Nega sintomas de estômago no momento.
O: PA sentada 138x78 mmHg. Ao ortostatismo, PA 112x70 mmHg. FC 72 bpm. Peso 61 kg. Braço com hematoma, sem dor para movimentar.
A: Diazepam aumenta o risco de queda.
P: Reduzir diazepam de 10 mg para 5 mg por duas semanas e depois suspender. Suspender omeprazol. Manter anlodipino. Manter sinvastatina. Orientado usar luz baixa à noite, evitar café à tarde e deixar uma luz acesa no caminho do banheiro. Retorno em 1 mês.
```

## 07-depressao-sertralina (voz natural, 62.9 s, WER 0.019)

- sem divergências
- ponto para conferir [medio] inferido: Episódio depressivo em acompanhamento, com melhora parcial com sertralina.
- ponto para conferir [info] cadastro: Ajustada sertralina de 50 mg 1x/dia para 100 mg pela manhã.

```
S: Refere estar um pouco melhor desde o início da sertralina há dois meses, mas ainda sem vontade de fazer as coisas. Refere dormir mal e chorar com facilidade. Nega pensamentos de se machucar ou de morrer. Relata enjoo no começo do uso da sertralina, já resolvido.
O: Questionário de hoje com 15 pontos. Depressão moderada no questionário de hoje.
A: Episódio depressivo em acompanhamento, com melhora parcial com sertralina.
P: Ajustada sertralina de 50 mg 1x/dia para 100 mg pela manhã. Orientado retorno para psicoterapia. Orientada a procurar ajuda imediatamente se surgirem pensamentos de se machucar; pode ligar no 188. Retorno em quatro semanas.
```

## 08-asma-crise (voz natural, 68.8 s, WER 0.035)

- sem divergências
- ponto para conferir [medio] inferido: Asma em manejo na consulta, com falta de ar e sibilância, com melhora após salbutamol.
- ponto para conferir [medio] pendencia: Confirmar posologia do salbutamol ouvida com dúvida: 4 jatos a cada 20 minutos, 3 vezes, com espaçador.
- ponto para conferir [medio] pendencia: Dose de budesonida com formoterol não foi dita.

```
S: Refere falta de ar desde ontem e chiado intenso. Relata que o spray não está resolvendo. Usou a bombinha cerca de seis vezes hoje. Refere gripe na semana passada.
O: Saturação inicial de 93%. Frequência respiratória de 24 irpm. Frequência cardíaca de 104 bpm. Sibilos em ambos os pulmões. Recebeu salbutamol: 4 jatos a cada 20 minutos, 3 vezes, com espaçador. Após as 3 séries, saturação de 97% e sibilos bem menores.
A: Asma em manejo na consulta, com falta de ar e sibilância, com melhora após salbutamol.
P: Prednisolona 40 mg uma vez ao dia por 5 dias. Iniciado budesonida com formoterol, 2 jatos de 12/12h, todos os dias. Orientado procurar pronto-socorro se piora da falta de ar ou boca roxa. Retorno em 1 semana.
```

## 09-meio-comprimido-captopril (voz natural, 47.4 s, WER 0.012)

- sem divergências
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento, com medidas pressóricas domiciliares elevadas referidas e pressão arterial elevada na consulta.
- ponto para conferir [medio] pendencia: Confirmar remédio ouvido com dúvida na gravação: captopril 25 mg.
- ponto para conferir [info] cadastro: Relata estar tomando meio comprimido de captopril 25 mg 2x/dia, porque lhe falaram que era forte.

```
S: Refere pressão arterial em casa sempre alta, com medidas de 150 a 160 mmHg. Relata estar tomando meio comprimido de captopril 25 mg 2x/dia, porque lhe falaram que era forte.
O: Pressão arterial 156x92 mmHg. Frequência cardíaca 78 bpm.
A: Hipertensão arterial em acompanhamento, com medidas pressóricas domiciliares elevadas referidas e pressão arterial elevada na consulta.
P: Ajustado captopril de meio comprimido para 1 comprimido de 25 mg 2x/dia. Iniciada hidroclorotiazida 25 mg, 1 comprimido pela manhã. Orientado medir a pressão em casa e anotar as medidas. Retorno em 4 semanas com as medidas de pressão arterial.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.011)

- sem divergências

```
S: Paciente refere ardência ao urinar há dois dias e vontade de urinar toda hora. Nega febre. Nega dor nas costas. Nega sangue na urina. Relata que em outra ocasião recebeu Bactrim e perguntou se poderia tomar novamente.
O: Temperatura 36,8 °C. Abdome sem dor. Punho-percussão negativa.
A: Alergia à sulfa mencionada na consulta.
P: Orientado não usar Bactrim por alergia à sulfa. Iniciada nitrofurantoína 100 miligramas de 6 em 6 horas por 5 dias. Orientado beber bastante água. Orientado retornar se tiver febre ou dor nas costas. Sem necessidade de retorno se houver melhora.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- sem divergências
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] inferido: Quadro de obstrução nasal, dor no rosto, febre referida e achados em seios maxilares e garganta.

```
S: Refere nariz entupido e dor no rosto há 12 dias. Relata que começou como gripe e piorou novamente. Relata febre ontem, 38 °C.
O: Temperatura atual 37,6 °C. Dor à palpação dos seios maxilares. Secreção amarelada na garganta.
A: Quadro de obstrução nasal, dor no rosto, febre referida e achados em seios maxilares e garganta.
P: Iniciada amoxicilina 875 mg a cada 12 horas por 7 dias. Orientada lavagem nasal com soro, 3 vezes ao dia. Orientado retorno se não houver melhora em 3 dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] pendencia: Confirmar nova dose e posologia da metformina ajustada na consulta.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em acompanhamento, com hemoglobina glicada 7,8.

```
S: Refere que, nas festas, exagerou na alimentação.
O: Hemoglobina glicada 7,8, ainda acima. Pressão arterial 124x78 mmHg. Peso 74 kg.
A: Diabetes tipo 2 em acompanhamento, com hemoglobina glicada 7,8.
P: Ajustada metformina. Orientada dieta, com reforço para cortar refrigerante e doce. Solicitada repetição da hemoglobina glicada em três meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.051)

- fato ausente: compressa|calor

```
LIVRE: Paciente refere que travou as costas ao carregar o filho no sábado. Refere dor restrita à região lombar.
Nega dor descendo para a perna, formigamento, perda de força e alteração para urinar. Laségue negativo. Força preservada.
Lombalgia mecânica. Orientado retorno se a dor descer para a perna.
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.028)

- fato ausente: queimacao|azia|dispeps
- ponto para conferir [medio] inferido: Pressão arterial 126x80 mmHg.
- ponto para conferir [medio] inferido: Dor epigástrica.

```
S: Refere mação no estômago há 1 mês, com piora ao comer e à noite. Relata uso de ibuprofeno quase todo dia para dor de cabeça. Nega vômito com sangue e fezes pretas.
O: Abdome com dor leve no epigástrio, sem outros achados. Pressão arterial 126x80 mmHg.
A: Dor epigástrica.
P: Orientado suspender ibuprofeno. Iniciado omeprazol 20 mg em jejum por 8 semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em 8 semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] pendencia: Confirmar posologia ouvida com dúvida: dipirona se dor, até de 6 em 6 horas.

```
S: Refere cefaleia no fim do dia, tipo aperto bilateral. Nega náusea, piora com luz, alteração de força e alteração de visão. Relaciona o quadro a estresse no trabalho.
O: Pressão arterial 122x80 mmHg. Exame neurológico normal.
A: Cefaleia tensional.
P: Prescrita dipirona 1 grama, se dor, até de 6 em 6 horas. Orientados alongamento e pausas no trabalho. Orientado retorno se piorar.
```

## 16-dpoc-exacerbacao (voz natural, 62.5 s, WER 0.032)

- fato ausente: nega + febre
- ponto para conferir [medio] inferido: DPOC em acompanhamento, com piora de cansaço há quatro dias e aumento de escarro esverdeado.
- ponto para conferir [medio] pendencia: Confirmar presença de febre; resposta na gravação ficou duvidosa.
- ponto para conferir [info] cadastro: Mantido tiotrópio 2,5 mcg 2 jatos 1x/dia.
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere piora do cansaço há quatro dias. Refere aumento do escarro, com coloração esverdeada. Nega inchaço nas pernas.
O: Saturação de oxigênio: 91%. Frequência respiratória: 22 irpm. Frequência cardíaca: 96 bpm. Sibilos esparsos.
A: DPOC em acompanhamento, com piora de cansaço há quatro dias e aumento de escarro esverdeado.
P: Iniciada prednisona 40 miligramas uma vez ao dia por cinco dias. Iniciada azitromicina 500 miligramas uma vez ao dia por três dias. Mantido tiotrópio 2,5 mcg 2 jatos 1x/dia. Acrescentada budesonida com formoterol 12 por 400, uma inalação de 12 em 12 horas. Orientado procurar pronto-socorro se a saturação em casa cair abaixo de 88 ou se houver piora da falta de ar. Retorno em uma semana.
```

## 17-hipotireoidismo-levotiroxina (voz natural, 39.9 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Hipotireoidismo em acompanhamento.
- ponto para conferir [info] cadastro: Ajustada levotiroxina de 50 mcg para 75 microgramas em jejum.

```
LIVRE: TSH 8,2 e T4 livre 0,8. Refere cansaço e sensação de mais frio.
Relata uso diário de levotiroxina em jejum, meia hora antes do café. Frequência cardíaca 62 bpm. Peso 70,5 kg.
Tireoide sem nódulos à palpação. Hipotireoidismo em acompanhamento. Ajustada levotiroxina de 50 mcg para 75 microgramas em jejum. Orientado repetir TSH em seis semanas.
```

## 18-lombalgia-doenca-renal (voz natural, 49.1 s, WER 0.024)

- sem divergências
- ponto para conferir [medio] inferido: Dor lombar após carregar caixas, sem irradiação para a perna, sem febre e sem déficit.
- ponto para conferir [medio] inferido: Hipertensão arterial em seguimento.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [info] cadastro: Doença renal crônica estágio 3.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere dor nas costas após carregar caixas. Pergunta se pode usar diclofenaco que tem em casa. Refere que a última filtração foi 42. Nega dor descendo para a perna. Nega febre.
O: Pressão arterial 134x84 mmHg. Dor à palpação da musculatura lombar. Sem déficit.
A: Dor lombar após carregar caixas, sem irradiação para a perna, sem febre e sem déficit. Doença renal crônica estágio 3. Hipertensão arterial em seguimento.
P: Orientado que não use diclofenaco. Informado que anti-inflamatório pode piorar a função renal. Iniciado paracetamol 750 miligramas de seis em seis horas se dor, no máximo quatro comprimidos por dia. Iniciada ciclobenzaprina 5 miligramas à noite por sete dias. Mantida losartana.
```

## 19-dislipidemia-atorvastatina (voz natural, 39.3 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Ajustada atorvastatina de 20 mg à noite para 40 mg à noite.
- ponto para conferir [info] cadastro: Ajustada atorvastatina de 20 mg à noite para 40 mg à noite.

```
S: Em uso de remédio para colesterol, refere que está tomando conforme prescrito. Nega dor muscular. Nega fraqueza.
O: LDL 142, colesterol total 228, triglicérides 160. Pressão arterial 118x76 mmHg. Peso 63 kg.
A: Dislipidemia em acompanhamento, com LDL 142, colesterol total 228 e triglicérides 160 em uso de atorvastatina.
P: Ajustada atorvastatina de 20 mg à noite para 40 mg à noite. Repetir perfil lipídico em 3 meses. Repetir enzimas do fígado em 3 meses.
```

## 20-enxaqueca-profilaxia (voz natural, 46.5 s, WER 0.031)

- sem divergências

```
LIVRE: Refere enxaqueca cerca de seis vezes por mês, associada a enjoo e fotofobia. Nega asma.
Refere uso de anticoncepcional. Pressão arterial 112x72 mmHg. Frequência cardíaca 76 bpm. Exame neurológico normal.
Iniciada prevenção com propranolol 40 mg, 2 vezes ao dia. Orientado sumatriptana 50 mg na crise, no máximo 2 comprimidos por dia. Orientado fazer diário da dor. Retorno em 2 meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.019)

- faltou: hidroclorotiazida
- faltou: anlodipino
- ponto para conferir [medio] pendencia: Confirmar posologia da colchicina ouvida com dúvida: de 8 em 8 horas.
- ponto para conferir [medio] pendencia: Confirmar conduta sobre troca da hidroclorotiazida; foi ouvido com dúvida 'trocar por alopurinol de 5 miligramas uma vez ao dia', mas também foi dito que o alopurinol seria pensado depois que a crise passar.

```
S: Refere inchaço e vermelhidão no dedão do pé direito desde a madrugada, com dor ao ponto de não conseguir encostar o lençol. Refere que é a primeira vez que isso acontece. Relata churrasco com cerveja no fim de semana.
O: Temperatura 37,2 °C. Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: 
P: Iniciada colchicina 0,5 mg, de 8 em 8 horas, até melhorar, no máximo por uma semana. Orientado gelo no local e repouso. Orientado retorno em duas semanas. Foi dito que a hidroclorotiazida aumenta o ácido úrico. Foi dito que o alopurinol seria pensado depois que a crise passar.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.027)

- sem divergências
- ponto para conferir [medio] inferido: Fibrilação atrial em anticoagulação com INR acima da meta terapêutica.
- ponto para conferir [medio] dose_longe: varfarina: 0,5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: resposta sobre presença de sangue na urina não ficou clara na gravação
- ponto para conferir [medio] pendencia: confirmar dia ouvido com dúvida no esquema da varfarina: 'segunda e quinta'
- ponto para conferir [info] cadastro: varfarina: 5 mg todos os dias; na segunda e na quinta, meio comprimido (dose do cadastro: confirme se não mudou)

```
S: Relata sangramento na gengiva ao escovar, com interrupção espontânea. Nega sangue nas fezes e manchas roxas.
O: INR 3,8. Meta terapêutica de INR entre 2 e 3. PA 128x76 mmHg. FC 70 bpm.
A: Fibrilação atrial em anticoagulação com INR acima da meta terapêutica.
P: Ajustada varfarina de 35 mg por semana para 30 mg por semana. Orientado uso de varfarina 5 mg todos os dias, exceto segunda e quinta, quando deve tomar meio comprimido. Repetir INR em 1 semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.014)

- sem divergências

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Menstruação muito forte, com duração de cerca de sete dias.
Anemia por falta de ferro. Iniciado sulfato ferroso 40 mg de ferro, 1 comprimido 2 vezes ao dia, longe das refeições, com suco de laranja. Orientado que pode escurecer as fezes, considerado normal. Solicitado ultrassom transvaginal para investigação do sangramento. Programada repetição de hemograma e ferritina em 2 meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.043)

- fato ausente: senta
- ponto para conferir [medio] inferido: Peso 9,2 kg.
- ponto para conferir [medio] pendencia: Confirmar negativa ou sintoma ouvido com dúvida: tosse.
- ponto para conferir [medio] pendencia: Confirmar achado ouvido com dúvida: 'sem apoio'.
- ponto para conferir [info] cadastro: Vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Alimenta-se com papinha de legumes e fruta e mama no peito ainda. Vacinas em dia.
O: Peso 9,2 kg. Comprimento 74 cm. Perímetro cefálico 44 cm. Temperatura 36,7 °C. Já engatinha.
A: Desenvolvimento descrito como ótimo para a idade.
P: Manter vitamina D 400 UI por dia. Orientado oferecer água entre as refeições. Próxima vacina aos 12 meses. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.034)

- fato ausente: crepit
- ponto para conferir [alto] duvida_grave: enalapril: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] inferido: Peso 78,4 kg.
- ponto para conferir [medio] inferido: PA 118x72 mmHg.
- ponto para conferir [medio] inferido: FC 68 bpm.
- ponto para conferir [medio] inferido: Insuficiência cardíaca em seguimento, com piora de edema de pernas e ganho de peso referidos.
- ponto para conferir [medio] inferido: Hipertensão arterial em seguimento.
- ponto para conferir [medio] duvida: Mantido enalapril 10 mg 2x/dia. (ouvido com dúvida: enalapril)
- ponto para conferir [medio] pendencia: Confirmar remédio ouvido com dúvida: enalapril 10 mg 2x/dia.
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere que as pernas incharam novamente. Refere estar dormindo com dois travesseiros. Refere ganho de cerca de 2 kg na semana.
O: Peso 78,4 kg. PA 118x72 mmHg. FC 68 bpm. Edema de pernas 2+/4+.
A: Insuficiência cardíaca em seguimento, com piora de edema de pernas e ganho de peso referidos. Hipertensão arterial em seguimento.
P: Ajustada furosemida de 40 mg pela manhã para 40 mg 2x/dia, de manhã e no começo da tarde. Mantido carvedilol 6,25 mg 2x/dia. Mantida espironolactona 25 mg 1x/dia. Mantido enalapril 10 mg 2x/dia. Orientado pesar-se todo dia de manhã. Solicitados potássio e creatinina em 1 semana. Retorno em 2 semanas.
```

## 26-insonia-sem-benzodiazepinico (voz natural, 51.0 s, WER 0.026)

- avisado: trazodona saiu como Traz Zodona (nome errado, com sugestão)
- ponto para conferir [alto] remedio_nome: Traz Zodona: nome de remédio não reconhecido. Seria trazodona? Confira na transcrição.
- ponto para conferir [medio] duvida: Prescrito Traz Zodona 50 miligramas à noite. (ouvido com dúvida: zodona)
- ponto para conferir [medio] pendencia: Confirmar nome do remédio ouvido com dúvida: Traz Zodona 50 miligramas à noite.
- ponto para conferir [medio] pendencia: Confirmar fala possivelmente truncada na frase do encaminhamento: 'vou te encaminhar para terapia cognitiva para insônia'.

```
LIVRE: Paciente refere não conseguir dormir há três meses; deita e fica pensando no trabalho. Refere uso de celular na cama até tarde. Refere consumo de café, cerca de cinco xícaras por dia.
Perguntou sobre uso de clonazepam; orientado que não é recomendado, pois vicia e piora a memória. Prescrito Traz Zodona 50 miligramas à noite. Orientado deixar o celular fora do quarto. Orientado café somente até o almoço. Encaminhamento para terapia cognitiva para insônia. Retorno em um mês.
```

## 27-renovacao-de-receita (voz natural, 28.5 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento na consulta.
- ponto para conferir [medio] inferido: Hiperplasia prostática em acompanhamento na consulta.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tansulosina: 0,4 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Veio para renovar receitas. Refere estar tudo bem, sem queixas. Nega tontura, inchaço e dificuldade para urinar. Refere urinar bem com o remédio da próstata.
O: Pressão arterial 132x80 mmHg. Frequência cardíaca 70 bpm.
A: Hipertensão arterial em acompanhamento na consulta. Hiperplasia prostática em acompanhamento na consulta.
P: Receitas renovadas nas mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (voz natural, 45.6 s, WER 0.046)

- fato ausente: 180 + 220
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em acompanhamento.
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 em acompanhamento.
- ponto para conferir [info] cadastro: Ajustada insulina NPH noturna de 10 UI para 14 unidades.
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere glicemias em jejum entre 120 e 182 mg/dL. Refere uso de insulina NPH 20 UI pela manhã e 10 UI à noite até esta consulta. Nega hipoglicemia, tremor e suor frio.
O: Hemoglobina glicada 9,4. Pressão arterial 136x82 mmHg.
A: Diabetes mellitus tipo 2 em acompanhamento.
P: Ajustada insulina NPH noturna de 10 UI para 14 unidades. Mantida insulina NPH 20 UI pela manhã. Mantida metformina. Orientado anotar as glicemias em jejum. Retorno em 1 mês.
```

## 29-micose-cetoconazol (voz natural, 30.6 s, WER 0.0)

- sem divergências
- ponto para conferir [alto] duvida_grave: cetoconazol: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] duvida: Orientado cetoconazol creme 2 vezes ao dia por 4 semanas, mesmo após sumir. (ouvido com dúvida: cetoconazol)
- ponto para conferir [medio] pendencia: Confirmar medicamento ouvido com dúvida: cetoconazol creme.

```
LIVRE: Paciente refere mancha vermelha pruriginosa em virilha há cerca de três semanas. Relata que joga bola e fica suado.
Placa avermelhada com borda mais viva em ambas as virilhas. Médico afirmou micose crural. Orientado cetoconazol creme 2 vezes ao dia por 4 semanas, mesmo após sumir. Orientado secar bem a região e usar roupa de algodão. Orientado retornar se não melhorar em 4 semanas.
```

## 30-valor-corrigido (voz natural, 34.5 s, WER 0.0)

- sem divergências
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere pressão arterial em casa parecida com a medida da consulta.
O: Pressão arterial 140x90 mmHg. Frequência cardíaca 76 bpm.
A: Hipertensão arterial com pressão arterial um pouco acima da meta.
P: Mantida hidroclorotiazida 25 mg 1x/dia. Orientada redução de sal. Orientada a medir a pressão arterial em casa duas vezes por semana. Retorno em dois meses com as medidas de pressão arterial.
```

## 31-exame-em-silencio (voz natural, 78.4 s, WER 0.026)

- sem divergências

```
S: Refere tosse seca há três semanas. Nega febre. Nega tabagismo. Refere azia às vezes à noite. Nega nariz escorrendo.
O: Pulmões limpos, sem sibilos. Garganta sem alterações. SpO2 98%.
A: Tosse seca há três semanas. Médico considerou possibilidade de refluxo.
P: Iniciado omeprazol 20 mg em jejum por quatro semanas. Orientado elevar a cabeceira da cama. Se não houver melhora, considerar raio-X de tórax. Retorno em quatro semanas.
```
