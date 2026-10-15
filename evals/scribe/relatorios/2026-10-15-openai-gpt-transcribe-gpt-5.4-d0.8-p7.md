# Avaliação da gravação — 2026-10-15 · gpt-transcribe + gpt-5.4 · prompt 2026-10-15.7

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | sim |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.019 · remédios {'rem_certo': 60, 'rem_aviso': 1, 'rem_sem_aviso': 0, 'rem_falta': 1, 'rem_inventado': 0} · sinais 68/68 · CID 26/33 · fatos 176/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.01)

- sem divergências
- ponto para conferir [medio] duvida: Refere estar tomando losartana, metformina e medicação ouvida como "docolesterol" corretamente. (ouvido com dúvida: docolesterol)
- ponto para conferir [medio] inferido: Tontura ao levantar, breve, sem síncope, dor torácica ou dispneia.
- ponto para conferir [medio] duvida: Orientada a levantar devagar e sentar na cama por 1 minuto antes de ficar em pé. (ouvido com dúvida: levantar)
- ponto para conferir [medio] inferido: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [medio] pendencia: Confirmar medicação ouvida com dúvida: "docolesterol".
- ponto para conferir [medio] pendencia: Confirmar palavra ouvida com dúvida na orientação: "Levante".
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 na meta, com hemoglobina glicada 6,9%.
- ponto para conferir [info] cadastro: Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere estar tomando losartana, metformina e medicação ouvida como "docolesterol" corretamente. Refere caminhada 4 vezes por semana, cerca de 30 minutos. Relata 2 episódios de tontura ao levantar da cama nesta semana, com duração menor que 1 minuto e melhora ao sentar. Nega desmaio, dor no peito e falta de ar. Refere glicemias domiciliares em jejum entre 110 e 130 mg/dL. Nega hipoglicemia.
O: PA 128x82 mmHg. FC 74 bpm. Peso 86,8 kg. Glicemia capilar 108 mg/dL. Coração e pulmões sem alterações. Pés sem alterações, com pulsos presentes. Sensibilidade preservada ao monofilamento. Hemoglobina glicada 6,9%.
A: Diabetes mellitus tipo 2 na meta, com hemoglobina glicada 6,9%. Tontura ao levantar, breve, sem síncope, dor torácica ou dispneia.
P: Orientada a levantar devagar e sentar na cama por 1 minuto antes de ficar em pé. Manter losartana 50 mg 12/12h, metformina 850 mg 2x/dia e atorvastatina 20 mg à noite. Solicitados exame de urina para os rins e ácido úrico. Retorno em 3 meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.008)

- sem divergências
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em acompanhamento.
- ponto para conferir [info] cadastro: Ajustada losartana de 50 mg 1x/dia para 100 mg 1x/dia.

```
S: Trouxe exames e referiu que acha que não vieram muito bons. Refere uso de metformina 850 mg 2x/dia, com esquecimento ocasional da dose da noite.
O: Hemoglobina glicada 8,1. PA 152x94 mmHg. FC 80 bpm. Peso 92 kg.
A: Hemoglobina glicada acima da meta. Hipertensão arterial em acompanhamento. Diabetes mellitus tipo 2 em acompanhamento.
P: Ajustada losartana de 50 mg 1x/dia para 100 mg 1x/dia. Iniciada empagliflozina 10 mg, 1 comprimido pela manhã. Mantida metformina 850 mg 2x/dia. Orientado tentar não esquecer a dose noturna da metformina. Orientado beber bastante água e caprichar na higiene íntima. Informado que o remédio novo pode dar infecção urinária. Solicitados creatinina e potássio em 30 dias. Retorno em 2 meses.
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
- ponto para conferir [medio] pendencia: Confirmar apresentação da amoxicilina ouvida com dúvida: 250 mg por 5 mL.
- ponto para conferir [medio] pendencia: Confirmar posologia da amoxicilina ouvida com dúvida: 8 mL de 12/12 horas por 10 dias.

```
S: Mãe refere febre desde ontem, com pico de 38,5 °C, e choro por dor em ouvido direito. Nega vômito, diarreia e falta de ar. Refere que está mais molinho e comendo pouco.
O: Peso 16 kg. Temperatura atual 38,2 °C. Ouvido direito vermelho e abaulado. Ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações.
A: Otite média aguda.
P: Iniciada amoxicilina 250 mg por 5 mL, 8 mL de 12/12 horas por 10 dias. Prescrito paracetamol gotas, 16 gotas a cada 6 horas, se precisar, para febre ou dor. Orientado retorno antes se mantiver febre após 48 horas de antibiótico ou se ficar prostrado. Retorno em 10 dias.
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

- sem divergências
- ponto para conferir [alto] duvida_grave: diazepam: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] duvida: Refere uso de diazepam 10 mg à noite há anos. (ouvido com dúvida: diazepam)
- ponto para conferir [medio] inferido: Queda da pressão arterial ao ortostatismo durante a consulta.
- ponto para conferir [medio] inferido: Insônia em uso crônico de diazepam.
- ponto para conferir [medio] duvida: Insônia em uso crônico de diazepam. (ouvido com dúvida: diazepam)
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] duvida: Reduzido diazepam de 10 mg à noite para 5 mg por duas semanas e depois suspender. (ouvido com dúvida: diazepam)
- ponto para conferir [medio] vital_longe: pa_s = 112: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 70: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] pendencia: Confirmar remédio ouvido com dúvida: diazepam 10 mg.
- ponto para conferir [medio] pendencia: Confirmar tempo de uso do diazepam, ouvido como cerca de 20 anos.
- ponto para conferir [info] cadastro: Mantidos anlodipino 5 mg 1x/dia e sinvastatina 20 mg à noite.
- ponto para conferir [info] cadastro: omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente refere queda no banheiro de madrugada na semana passada, com trauma no braço. Refere que levantou para ir ao banheiro e a vista escureceu antes da queda. Refere uso de diazepam 10 mg à noite há anos. Nega sintomas de estômago no momento.
O: PA sentada 138x78 mmHg. PA em pé 112x70 mmHg. FC 72 bpm. Peso 61 kg. Braço com hematoma, sem dor à movimentação.
A: Queda noturna após levantar para ir ao banheiro, precedida de escurecimento visual. Queda da pressão arterial ao ortostatismo durante a consulta. Insônia em uso crônico de diazepam. Gastrite sem sintomas no momento. Hipertensão arterial em acompanhamento.
P: Reduzido diazepam de 10 mg à noite para 5 mg por duas semanas e depois suspender. Suspenso omeprazol. Mantidos anlodipino 5 mg 1x/dia e sinvastatina 20 mg à noite. Orientado luz baixa à noite, evitar café à tarde e deixar uma luz acesa no caminho do banheiro. Retorno em um mês.
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
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento, com medidas domiciliares e de consultório elevadas.
- ponto para conferir [medio] pendencia: Confirmar remédio ouvido com dúvida na gravação: captopril 25 mg.
- ponto para conferir [info] cadastro: Relata estar tomando meio comprimido de captopril 25 mg duas vezes ao dia, porque foi orientada de que era forte.

```
S: Refere pressão arterial em casa sempre alta, com medidas de 160 e 150 mmHg. Relata estar tomando meio comprimido de captopril 25 mg duas vezes ao dia, porque foi orientada de que era forte.
O: Pressão arterial hoje: 156x92 mmHg. Frequência cardíaca hoje: 78 bpm.
A: Hipertensão arterial em acompanhamento, com medidas domiciliares e de consultório elevadas.
P: Ajustado captopril de meio comprimido para 1 comprimido inteiro de 25 mg, duas vezes ao dia. Iniciada hidroclorotiazida 25 mg, 1 comprimido pela manhã. Orientada a medir a pressão em casa e anotar. Retorno em 4 semanas com as medidas de pressão.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.011)

- sem divergências
- ponto para conferir [medio] inferido: Quadro de ardência ao urinar e urgência/frequência urinária.

```
S: Refere ardência para urinar há 2 dias e vontade de urinar toda hora. Nega febre. Nega dor nas costas. Nega sangue na urina. Relata uso prévio de Bactrim em outro episódio. Refere alergia a sulfa.
O: Temperatura 36,8 °C. Abdome sem dor. Punho-percussão negativa.
A: Quadro de ardência ao urinar e urgência/frequência urinária. Alergia a sulfa.
P: Iniciada nitrofurantoína 100 miligramas de 6 em 6 horas por 5 dias. Orientado beber bastante água. Orientada a retornar se tiver febre ou dor nas costas. Sem necessidade de retorno se houver melhora.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- sem divergências
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] inferido: Quadro de obstrução nasal e dor facial há 12 dias, com piora após início como gripe.
- ponto para conferir [medio] pendencia: Confirmar duração da amoxicilina, pois a palavra antes de '7 dias' foi ouvida com dúvida no áudio.

```
S: Refere nariz entupido e dor no rosto há 12 dias. Relata que começou como gripe e piorou novamente. Refere febre ontem, 38 °C.
O: Temperatura atual 37,6 °C. Dor à palpação nos seios maxilares. Secreção amarelada na garganta.
A: Quadro de obstrução nasal e dor facial há 12 dias, com piora após início como gripe.
P: Prescrita amoxicilina 875 mg, 12/12h, por 7 dias. Orientada lavagem nasal com soro, três vezes ao dia. Orientado retorno se não melhorar em três dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em acompanhamento, com hemoglobina glicada 7,8.
- ponto para conferir [medio] pendencia: nova dose e posologia da metformina não foram ditas
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 em acompanhamento, com hemoglobina glicada 7,8.

```
S: Refere que, nas festas, exagerou na alimentação.
O: Hemoglobina glicada 7,8, ainda acima. Pressão arterial 124x78 mmHg. Peso 74 kg.
A: Diabetes mellitus tipo 2 em acompanhamento, com hemoglobina glicada 7,8.
P: Ajustada metformina. Orientada reforço de dieta, com corte de refrigerante e doce. Solicitada repetição da hemoglobina glicada em três meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.051)

- fato ausente: lasegue
- ponto para conferir [medio] pendencia: Confirmar achado de exame ouvido com dúvida: Laségue negativo.

```
LIVRE: Refere travamento nas costas após carregar o filho no sábado.
Nega dor irradiada para a perna, formigamento, perda de força e alteração urinária.
Força preservada.
Quadro compatível com lombalgia mecânica. Iniciado paracetamol 750 mg de 6/6h se dor. Iniciada ciclobenzaprina 5 mg à noite por 7 dias. Orientada compressa morna. Orientado retorno se a dor descer para a perna.
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.028)

- fato ausente: nega + sangue|melena|hematem
- ponto para conferir [medio] inferido: Queimação no estômago há um mês, com piora alimentar e noturna.
- ponto para conferir [medio] pendencia: Resposta sobre vômito com sangue e fezes pretas não ficou suficientemente clara na gravação.
- ponto para conferir [medio] pendencia: Dose e posologia do ibuprofeno não foram ditas na consulta.

```
S: Refere queimação no estômago há um mês, com piora ao comer e à noite. Relata uso de ibuprofeno quase todos os dias para dor de cabeça.
O: Abdome com dor leve no epigástrio, sem outros achados. Pressão arterial 126x80 mmHg.
A: Queimação no estômago há um mês, com piora alimentar e noturna. Uso frequente de ibuprofeno para dor de cabeça.
P: Orientado parar o ibuprofeno. Iniciado omeprazol 20 mg em jejum por oito semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em oito semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] pendencia: Confirmar posologia ouvida com dúvida: dipirona 1 grama, se dor, até de 6 em 6 horas.

```
S: Refere cefaleia no fim do dia, em aperto, bilateral. Nega náusea, fotofobia, alteração de força e alteração de visão. Relaciona a dor a estresse no trabalho.
O: Pressão arterial 122x80 mmHg. Exame neurológico normal.
A: Cefaleia tensional.
P: Iniciada dipirona 1 grama, se dor, até de 6 em 6 horas. Orientados alongamento e pausas no trabalho. Orientado retorno se piorar.
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
- ponto para conferir [medio] inferido: Doença renal crônica estágio 3 em acompanhamento.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] inferido: Dor lombar após esforço.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: Resposta sobre irradiação da dor ficou com gravação incerta ('desce pra perna').
- ponto para conferir [info] cadastro: Doença renal crônica estágio 3 em acompanhamento.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere dor nas costas após carregar caixas. Perguntou se poderia usar diclofenaco que tem em casa. Nega febre. Refere última filtração de 42.
O: Pressão arterial 134x84 mmHg. Dor à palpação da musculatura lombar. Sem déficit.
A: Doença renal crônica estágio 3 em acompanhamento. Hipertensão arterial em acompanhamento. Dor lombar após esforço.
P: Orientado que anti-inflamatório pode piorar por doença renal e que não use diclofenaco. Iniciado paracetamol 750 mg de 6/6h se dor, no máximo 4 comprimidos por dia. Iniciada ciclobenzaprina 5 mg à noite por 7 dias. Mantida losartana.
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
- ponto para conferir [alto] duvida_grave: propranolol: 40 ouvido com dúvida
- ponto para conferir [medio] duvida: Iniciada prevenção com propranolol 40 mg, duas vezes ao dia. (ouvido com dúvida: 40)
- ponto para conferir [medio] pendencia: Confirmar dose ouvida com dúvida: propranolol 40 mg.

```
LIVRE: Refere enxaqueca cerca de seis vezes por mês, com enjoo e incômodo com a luz. Nega asma. Refere uso de anticoncepcional.
Pressão arterial 112x72 mmHg. Frequência cardíaca 76 bpm. Exame neurológico normal.
Iniciada prevenção com propranolol 40 mg, duas vezes ao dia. Na crise, orientado sumatriptana 50 mg, no máximo dois comprimidos por dia. Orientado diário da dor. Retorno em dois meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.019)

- faltou: anlodipino
- a mais (foi citado, não está no gabarito): alopurinol iniciado
- ponto para conferir [alto] duvida_grave: alopurinol: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [alto] dose_incomum: alopurinol 5 mg: fora da dose usual por tomada (50–600 mg). Confira o nome e a dose: o transcritor pode ter trocado o remédio.
- ponto para conferir [medio] duvida: Ácido úrico do último exame: 9,1. (ouvido com dúvida: 9,1)
- ponto para conferir [medio] inferido: Hipertensão arterial em uso de hidroclorotiazida, com decisão de troca na consulta.
- ponto para conferir [medio] duvida: Decidida troca da hidroclorotiazida por alopurinol de 5 mg uma vez ao dia. (ouvido com dúvida: alopurinol)
- ponto para conferir [medio] duvida: Médico relatou que pensará em alopurinol depois que a crise passar. (ouvido com dúvida: alopurinol)
- ponto para conferir [medio] pendencia: Confirmar valor do ácido úrico do último exame, ouvido com dúvida: 9,1.
- ponto para conferir [medio] pendencia: Confirmar posologia da colchicina, ouvida com dúvida: 8/8 h.
- ponto para conferir [medio] pendencia: Confirmar remédio ouvido com dúvida na troca da hidroclorotiazida: alopurinol 5 mg 1x/dia.
- ponto para conferir [medio] pendencia: A fala sobre alopurinol ficou contraditória na gravação: foi dita troca para alopurinol 5 mg 1x/dia e também que alopurinol seria pensado depois que a crise passar.
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Relata que o dedão do pé direito inchou de madrugada, ficou vermelho e não consegue encostar o lençol. Refere ser a primeira vez que isso acontece. Relata churrasco com cerveja no fim de semana.
O: Temperatura 37,2 °C. Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: Hipertensão arterial em uso de hidroclorotiazida, com decisão de troca na consulta.
P: Iniciada colchicina 0,5 mg, de 8/8 h, até melhorar, no máximo por uma semana. Orientado gelo no local e repouso. Informado que a hidroclorotiazida aumenta o ácido úrico. Decidida troca da hidroclorotiazida por alopurinol de 5 mg uma vez ao dia. Médico relatou que pensará em alopurinol depois que a crise passar. Retorno em duas semanas.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.027)

- sem divergências
- ponto para conferir [alto] dose_incomum: varfarina 30 mg por semana: fora da dose usual por tomada (0,5–15 mg). Confira o nome e a dose: o transcritor pode ter trocado o remédio.
- ponto para conferir [medio] inferido: Fibrilação atrial em uso de anticoagulação oral com INR acima da meta.
- ponto para conferir [medio] dose_longe: varfarina: 30 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] dose_longe: varfarina: 0,5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [info] cadastro: varfarina: 30 mg por semana 5 mg todos os dias, exceto segunda e quinta, quando toma meio comprimido (dose do cadastro: confirme se não mudou)

```
S: Relata sangramento na gengiva ao escovar os dentes, com cessação espontânea. Nega sangue na urina, sangue nas fezes e manchas roxas.
O: INR 3,8. Meta de INR entre 2 e 3. PA 128x76 mmHg. FC 70 bpm.
A: Fibrilação atrial em uso de anticoagulação oral com INR acima da meta.
P: Ajustada varfarina de 35 mg por semana para 30 mg por semana. Orientado varfarina 5 mg todos os dias, exceto segunda e quinta, quando toma meio comprimido. Repetir INR em 1 semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.014)

- sem divergências

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Menstruação muito forte, com duração de cerca de sete dias.
Anemia por falta de ferro. Iniciado sulfato ferroso 40 mg de ferro, 1 comprimido 2 vezes ao dia, longe das refeições, com suco de laranja. Orientado que pode escurecer as fezes, considerado normal. Solicitado ultrassom transvaginal para investigação do sangramento. Programada repetição de hemograma e ferritina em 2 meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.043)

- fato ausente: senta
- ponto para conferir [medio] duvida: Desenvolvimento avaliado como adequado para a idade. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Confirmar negativa ou sintoma ouvido com dúvida: sem tosse.
- ponto para conferir [info] cadastro: Vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Alimenta-se com papinha de legumes e fruta e mama no peito ainda. Vacinas em dia.
O: Peso 9,2 kg. Comprimento 74 cm. Perímetro cefálico 44 cm. Já engatinha. Desenvolvimento avaliado como adequado para a idade.
A: 
P: Manter vitamina D 400 UI por dia. Orientado oferecer água entre as refeições. Próxima vacina aos 12 meses. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.034)

- fato ausente: crepit
- ponto para conferir [alto] duvida_grave: enalapril: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] inferido: Peso 78,4 kg.
- ponto para conferir [medio] inferido: PA 118x72 mmHg.
- ponto para conferir [medio] inferido: FC 68 bpm.
- ponto para conferir [medio] inferido: Edema em pernas 2+/4+.
- ponto para conferir [medio] inferido: Insuficiência cardíaca em acompanhamento, com piora de edema em pernas e ganho de peso referidos na consulta.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] inferido: Ajustada furosemida de 40 mg pela manhã para 40 mg 2x/dia, de manhã e no começo da tarde.
- ponto para conferir [medio] inferido: Mantida espironolactona 25 mg 1x/dia.
- ponto para conferir [medio] inferido: Mantido enalapril 10 mg 2x/dia.
- ponto para conferir [medio] duvida: Mantido enalapril 10 mg 2x/dia. (ouvido com dúvida: enalapril)
- ponto para conferir [medio] pendencia: Confirmar medicamento ouvido com dúvida: enalapril 10 mg.
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere que as pernas incharam de novo. Refere estar dormindo com dois travesseiros. Refere ganho de cerca de 2 kg na semana.
O: Peso 78,4 kg. PA 118x72 mmHg. FC 68 bpm. Edema em pernas 2+/4+.
A: Insuficiência cardíaca em acompanhamento, com piora de edema em pernas e ganho de peso referidos na consulta. Hipertensão arterial em acompanhamento.
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
- ponto para conferir [medio] duvida: Orientado cetoconazol creme 2 vezes ao dia por 4 semanas, mesmo após sumirem as lesões. (ouvido com dúvida: cetoconazol)
- ponto para conferir [medio] pendencia: Confirmar medicamento ouvido com dúvida: cetoconazol creme.

```
LIVRE: Refere mancha vermelha pruriginosa na virilha há cerca de três semanas. Relata que joga bola e fica suado. Descreve placa avermelhada com borda mais viva em ambas as virilhas.
Médico afirmou micose/tínea crural. Orientado cetoconazol creme 2 vezes ao dia por 4 semanas, mesmo após sumirem as lesões. Orientado secar bem a região e usar roupa de algodão. Orientado retornar se não houver melhora em 4 semanas.
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
O: Pulmões limpos. Sem sibilos. Garganta sem alterações. Saturação de oxigênio 98%.
A: Tosse seca há três semanas.
P: Iniciado omeprazol 20 miligramas em jejum por quatro semanas. Orientado elevar a cabeceira da cama. Se não melhorar, fazer raio-X do tórax. Retorno em quatro semanas.
```
