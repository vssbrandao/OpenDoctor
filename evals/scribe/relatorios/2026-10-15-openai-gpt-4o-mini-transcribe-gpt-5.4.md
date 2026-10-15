# Avaliação da gravação — 2026-10-15 · gpt-4o-mini-transcribe + gpt-5.4 · prompt 2026-10-15.4

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.025 · remédios {'rem_certo': 42, 'rem_aviso': 9, 'rem_sem_aviso': 0, 'rem_falta': 11, 'rem_inventado': 0} · sinais 61/68 · CID 26/33 · fatos 157/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] pendencia: Ausculta cardíaca e pulmonar com termo ouvido com dúvida: 'sem alterações'.
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso regular de losartana, metformina e medicação para colesterol. Refere caminhada 4 vezes por semana, cerca de 30 minutos. Relata dois episódios de tontura ao levantar da cama nesta semana, com melhora em menos de um minuto ao sentar. Nega desmaio, dor no peito e falta de ar associados aos episódios. Refere glicemias capilares em jejum entre 110 e 130. Nega episódios de hipoglicemia.
O: PA 128/82 mmHg. FC 74 bpm. Peso 86,8 kg. Glicemia capilar no momento 108 mg/dL. Pés sem alterações, com pulsos presentes. Sensibilidade preservada ao monofilamento. Hemoglobina glicada 6,9.
A: Diabetes em meta, segundo avaliação médica. Tontura ao levantar, com possibilidade de queda da pressão ao ficar em pé, segundo avaliação médica.
P: Manter os três remédios em uso. Orientada a levantar devagar e sentar na cama por um minuto antes de ficar em pé. Solicitados exame de urina para os rins e ácido úrico. Retorno em 3 meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.008)

- fato ausente: 8,1|8.1
- fato ausente: esquec
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em acompanhamento, com hemoglobina glicada acima da meta.
- ponto para conferir [medio] pendencia: valor exato da hemoglobina glicada não ficou claro na gravação
- ponto para conferir [medio] pendencia: adesão à dose noturna da metformina não ficou clara na gravação

```
S: Paciente trouxe exames. Refere uso de metformina.
O: Hemoglobina glicada acima da meta. PA 152/94 mmHg. FC 80 bpm. Peso 92 kg.
A: Hipertensão arterial em acompanhamento. Diabetes mellitus tipo 2 em acompanhamento, com hemoglobina glicada acima da meta.
P: Ajustada losartana para 100 mg uma vez ao dia. Iniciada empagliflozina 10 mg, um comprimido de manhã. Mantida metformina 850 mg, duas vezes ao dia. Orientado beber bastante água e caprichar na higiene íntima, pelo risco de infecção urinária com a medicação nova. Solicitados creatinina e potássio em 30 dias. Retorno em dois meses.
```

## 03-fibrilacao-rivaroxabana (voz natural, 80.2 s, WER 0.023)

- avisado: rivaroxabana esperado 20 mg 1x/dia iniciado / saiu  1 vez ao dia, junto com o jantar iniciado
- fato ausente: nega + sincope|desmai
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] pendencia: Resposta sobre desmaio não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose da rivaroxabana foi ouvida com dúvida.
- ponto para conferir [info] cadastro: Mantido anlodipino 5 mg 1x/dia.
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere coração disparando há uma semana, com palpitações e maior cansaço para subir escadas. Nega dor no peito e falta de ar ao deitar.
O: Pulso irregular. Frequência cardíaca 112 bpm. Pressão arterial 138/86 mmHg. Eletrocardiograma com fibrilação atrial.
A: Fibrilação atrial. Hipertensão arterial em acompanhamento.
P: Iniciada rivaroxabana 1 vez ao dia, junto com o jantar, para prevenir derrame. Suspenso AAS. Iniciado metoprolol succinato 50 mg 1 vez ao dia para controle da frequência cardíaca. Mantido anlodipino 5 mg 1x/dia. Solicitados ecocardiograma, TSH e função dos rins. Orientado procurar pronto-socorro se sangramento que não para, fezes pretas ou urina com sangue. Retorno em quatro semanas.
```

## 04-pediatria-otite (voz natural, 78.9 s, WER 0.063)

- avisado: amoxicilina esperado 8 ml 12/12h iniciado / saiu   iniciado
- faltou: paracetamol
- fato ausente: abaulad
- fato ausente: 48 horas
- ponto para conferir [medio] pendencia: Descrição do ouvido direito ficou parcialmente inaudível na gravação.
- ponto para conferir [medio] pendencia: Dose e apresentação da amoxicilina não ficaram claras na gravação.
- ponto para conferir [medio] pendencia: Posologia da amoxicilina não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Medicamento para febre/dor ouvido com dúvida: paracetamol.
- ponto para conferir [medio] pendencia: Prazo exato de reavaliação da febre após antibiótico não ficou claro na gravação.

```
S: Mãe refere febre desde ontem, com temperatura máxima de 38,5 °C, e choro por dor no ouvido direito. Nega vômitos, diarreia e falta de ar. Refere paciente mais molinho e comendo pouco.
O: Peso 16 kg. Temperatura 38,2 °C. Ouvido direito vermelho. Ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações.
A: Otite média aguda.
P: Iniciada amoxicilina. Orientado retorno antes em caso de persistência da febre após início do antibiótico ou se ficar prostrado. Retorno em 10 dias.
```

## 05-prenatal-28-semanas (voz natural, 68.3 s, WER 0.01)

- faltou: sulfato ferroso
- ponto para conferir [medio] pendencia: Medicamento novo ouvido com dúvida: 'sulfato ferroso', com orientação de 40 mg de ferro, 1 comprimido por dia, longe do café e do leite.
- ponto para conferir [medio] pendencia: Nome do exame ouvido com dúvida: 'TTG de 75 gramas'.
- ponto para conferir [info] cadastro: Ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere 28 semanas de gestação. Relata bebê mexendo bastante. Refere um pouco de azia à noite. Nega sangramento, perda de líquido e contrações.
O: Pressão arterial 110/70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. Batimentos fetais 144.
A: Gestação com 28 semanas.
P: Orientado parar ácido fólico. Solicitada curva glicêmica. Orientada a tomar vacina DTPA no posto. Orientadas refeições menores e evitar deitar logo após comer para azia. Retorno em 2 semanas.
```

## 06-idoso-queda-desprescricao (voz natural, 74.5 s, WER 0.014)

- faltou: diazepam
- faltou: anlodipino
- fato ausente: sentado + 138
- fato ausente: 2 semanas|duas semanas
- ponto para conferir [alto] numero: PA sentada 138/78 mmHg.
- ponto para conferir [medio] duvida: Relata que levantou para ir ao banheiro e a vista escureceu antes da queda. (ouvido com dúvida: para)
- ponto para conferir [medio] duvida: Queda na última semana após levantar-se para ir ao banheiro, precedida por escurecimento visual. (ouvido com dúvida: para)
- ponto para conferir [medio] inferido: Redução da pressão arterial ao ortostatismo na consulta.
- ponto para conferir [medio] vital_longe: pa_s = 112: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] vital_longe: pa_d = 70: o número está no trecho, mas não junto de PA
- ponto para conferir [medio] pendencia: Nome do medicamento de uso noturno ouvido com dúvida na gravação; consta no cadastro como diazepam.
- ponto para conferir [medio] pendencia: Dose da redução do medicamento de uso noturno não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Manutenção do anlodipino foi ouvida com dúvida na gravação.
- ponto para conferir [info] cadastro: Omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Queda no banheiro de madrugada na semana passada, com trauma no braço. Relata que levantou para ir ao banheiro e a vista escureceu antes da queda. Refere não ter mais sintoma de estômago.
O: PA sentada 138/78 mmHg. PA em pé 112/70 mmHg. FC 72 bpm. Peso 61 kg. Braço com hematoma, sem dor para mexer.
A: Queda na última semana após levantar-se para ir ao banheiro, precedida por escurecimento visual. Redução da pressão arterial ao ortostatismo na consulta. Insônia em acompanhamento. Gastrite sem sintomas no momento. Hipertensão arterial em acompanhamento.
P: Suspenso omeprazol. Mantida sinvastatina. Orientado manter luz baixa à noite, evitar café à tarde e deixar uma luz acesa no caminho do banheiro. Retorno em 1 mês.
```

## 07-depressao-sertralina (voz natural, 62.9 s, WER 0.01)

- avisado: sertralina esperado 100 mg * ajustado / saiu  de manhã ajustado
- fato ausente: 15
- fato ausente: dorme mal|insonia|sono
- ponto para conferir [medio] inferido: Episódio depressivo em acompanhamento, com melhora parcial e sintomas persistentes.
- ponto para conferir [medio] duvida: Ajustada sertralina para uso pela manhã. (ouvido com dúvida: para)
- ponto para conferir [medio] duvida: Encaminhada para psicoterapia. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Dose da sertralina após ajuste não ficou clara na gravação: '100 miligramas' foi ouvida com dúvida.
- ponto para conferir [medio] pendencia: Pontuação exata do questionário de hoje não ficou clara na gravação: 'quinze pontos' foi ouvida com dúvida.

```
S: Refere estar um pouco melhor desde o início da sertralina há dois meses, mas ainda sem vontade de fazer as coisas. Refere dormir mal e chorar com facilidade. Nega pensamentos de se machucar ou de morrer. Refere enjoo no começo do uso da medicação, já resolvido.
O: Questionário de hoje com resultado referido como depressão moderada.
A: Episódio depressivo em acompanhamento, com melhora parcial e sintomas persistentes.
P: Ajustada sertralina para uso pela manhã. Encaminhada para psicoterapia. Orientada a procurar ajuda imediatamente se surgirem pensamentos de se machucar. Orientada que pode ligar no 188 se surgirem pensamentos de se machucar. Retorno em quatro semanas.
```

## 08-asma-crise (voz natural, 68.8 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Asma em manejo na consulta, com falta de ar e sibilância.
- ponto para conferir [medio] pendencia: dose da budesonida com formoterol não foi dita

```
S: Paciente refere falta de ar desde ontem e chiado importante. Relata que o spray não está resolvendo. Informa uso da bombinha cerca de seis vezes hoje. Refere gripe na semana passada.
O: SpO2 inicial de 93%. Frequência respiratória de 24 irpm. Frequência cardíaca de 104 bpm. Sibilos em ambos os pulmões. Após três séries de salbutamol com espaçador, SpO2 de 97% e sibilos bem menores.
A: Asma em manejo na consulta, com falta de ar e sibilância.
P: Realizado salbutamol, quatro jatos a cada vinte minutos, três vezes, com espaçador. Prescrita prednisolona 40 mg uma vez ao dia por 5 dias. Iniciado budesonida com formoterol, dois jatos de 12 em 12 horas, todos os dias. Orientado procurar pronto-socorro se piorar a falta de ar ou se a boca ficar roxa. Retorno em 1 semana.
```

## 09-meio-comprimido-captopril (voz natural, 47.4 s, WER 0.0)

- faltou: hidroclorotiazida
- sinal pa_s: esperado 156.0 / saiu None
- sinal pa_d: esperado 92.0 / saiu None
- ponto para conferir [medio] inferido: Refere pressão arterial em casa sempre alta, com medidas em torno de 150 a 160.
- ponto para conferir [medio] pendencia: Valor da pressão arterial aferida hoje não ficou totalmente claro na gravação: 'cento e cinquenta e seis por noventa e dois'.
- ponto para conferir [medio] pendencia: Medicamento novo ouvido com dúvida: 'hidroclorotiazida'.
- ponto para conferir [medio] pendencia: Dose do medicamento novo ouvida com dúvida: '25 miligramas'.

```
S: Refere pressão arterial em casa sempre alta, com medidas em torno de 150 a 160. Relata que está tomando meio comprimido de captopril, porque foi orientada por terceiros de que seria forte.
O: Frequência cardíaca 78 bpm.
A: Hipertensão arterial em acompanhamento. Uso de captopril em dose diferente da prescrita no cadastro até a consulta.
P: Orientado captopril 25 mg, 1 comprimido, 2 vezes ao dia. Orientado medir a pressão em casa e anotar as medidas. Retorno em 4 semanas com as medidas de pressão.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.022)

- sinal temp: esperado 36.8 / saiu None
- fato ausente: ardencia|disuria
- fato ausente: punho|giordano
- ponto para conferir [medio] pendencia: Sintoma ouvido com dúvida: ardência para urinar.
- ponto para conferir [medio] pendencia: Temperatura e valor medido com dúvida na gravação.

```
S: Refere vontade urinária frequente há dois dias. Nega febre. Nega dor nas costas. Nega sangue na urina. Relata que em outra ocasião recebeu Bactrim e perguntou se poderia tomar novamente.
O: Abdômen sem dor.
A: Alergia a sulfa considerada na escolha do antibiótico.
P: Iniciada nitrofurantoína 100 mg de seis em seis horas por cinco dias. Orientada a beber bastante água. Orientada a retornar se tiver febre ou dor nas costas. Sem necessidade de retorno se houver melhora.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- sem divergências
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] inferido: Quadro de obstrução nasal, dor facial e febre relatada, com piora após início como gripe.

```
S: Paciente refere nariz entupido e dor no rosto há 12 dias. Relata que começou como gripe e voltou a piorar. Refere febre ontem de 38 °C.
O: Temperatura aferida em consulta: 37,6 °C. Dor à palpação em seios maxilares. Secreção amarelada na garganta.
A: Quadro de obstrução nasal, dor facial e febre relatada, com piora após início como gripe.
P: Iniciada amoxicilina 875 mg de 12/12 h por 7 dias. Orientada lavagem nasal com soro 3 vezes ao dia. Orientado retorno se não houver melhora em 3 dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.021)

- sem divergências
- ponto para conferir [medio] pendencia: Dose e posologia da metformina após ajuste não foram ditas.
- ponto para conferir [medio] pendencia: Orientação dietética incluiu termo inaudível após 'cortar refrigerante'.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em acompanhamento, com hemoglobina glicada 7,8, ainda acima.

```
S: Refere que exagerou nas festas.
O: Hemoglobina glicada 7,8. Pressão arterial 124/78 mmHg. Peso 74 kg.
A: Diabetes tipo 2 em acompanhamento, com hemoglobina glicada 7,8, ainda acima.
P: Aumentada metformina. Reforçadas orientações de dieta. Solicitada repetição da hemoglobina glicada em 3 meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.071)

- avisado: paracetamol esperado 750 mg 6/6h iniciado / saiu   iniciado
- faltou: ciclobenzaprina
- fato ausente: lasegue
- fato ausente: 7 dias|sete dias
- ponto para conferir [medio] pendencia: dose e posologia do paracetamol não ficaram claras na gravação
- ponto para conferir [medio] pendencia: medicação ouvida com dúvida: 'Cibor'
- ponto para conferir [medio] pendencia: medicação ouvida com dúvida: 'ciclobenzaprina' e respectivos dose e posologia não ficaram claros na gravação
- ponto para conferir [medio] pendencia: termo ouvido com dúvida: 'Lasegue negativo'

```
LIVRE: Paciente relata travamento nas costas após carregar o filho no sábado. Refere dor restrita à região lombar. Nega dor descendo para a perna, formigamento, perda de força e alteração para urinar.
Força preservada. Quadro definido como lombalgia mecânica. Orientado uso de compressa morna. Orientado retorno se a dor descer para a perna.
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.056)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum por 8 semanas iniciado
- fato ausente: nega + sangue|melena|hematem
- ponto para conferir [medio] pendencia: Resposta sobre vômito com sangue ou fezes pretas não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose do omeprazol não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Piora da queimação ao comer e à noite não ficou clara na gravação.

```
S: Refere queimação no estômago há um mês. Relata uso de ibuprofeno quase todos os dias para dor de cabeça.
O: Dor leve no epigástrio, sem outros achados. Pressão arterial 126/80 mmHg.
A: Queixa de queimação no estômago há um mês. Uso quase diário de ibuprofeno.
P: Orientado suspender ibuprofeno. Iniciado omeprazol em jejum por 8 semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em 8 semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.0)

- avisado: dipirona esperado 1 g 6/6h iniciado / saiu  se dor, até de seis em seis horas iniciado
- ponto para conferir [medio] pendencia: dose da dipirona não ficou clara na gravação

```
S: Refere cefaleia no fim do dia, em aperto, bilateral. Nega náusea, piora com luz, alteração de força e alteração de visão. Relaciona o quadro a estresse no trabalho.
O: Pressão arterial 122/80 mmHg. Exame neurológico normal.
A: Cefaleia tensional.
P: Prescrita dipirona se dor, até de seis em seis horas. Orientados alongamento e pausas no trabalho. Orientado retorno se piorar. Atestado não indicado para o caso.
```

## 16-dpoc-exacerbacao (voz natural, 62.5 s, WER 0.043)

- faltou: azitromicina
- fato ausente: escarro|expector
- ponto para conferir [alto] duvida_grave: budesonida + formoterol: 12 ouvido com dúvida
- ponto para conferir [medio] inferido: DPOC em acompanhamento, com piora recente do cansaço.
- ponto para conferir [medio] duvida: Acrescentada budesonida com formoterol, 1 inalação de 12 em 12 horas. (ouvido com dúvida: 12)
- ponto para conferir [medio] pendencia: Sintoma ouvido com dúvida: escarro com mudança de cor e aumento.
- ponto para conferir [medio] pendencia: Remédio ouvido com dúvida: azitromicina 500 mg 1 vez ao dia por 3 dias.
- ponto para conferir [medio] pendencia: Dose da budesonida com formoterol não ficou clara na gravação.
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere piora do cansaço há quatro dias. Nega febre. Nega inchaço nas pernas.
O: Saturação de oxigênio: 91%. Frequência respiratória: 22 irpm. Frequência cardíaca: 96 bpm. Sibilos esparsos.
A: DPOC em acompanhamento, com piora recente do cansaço.
P: Iniciada prednisona 40 mg 1 vez ao dia por 5 dias. Mantido tiotrópio. Acrescentada budesonida com formoterol, 1 inalação de 12 em 12 horas. Orientado procurar pronto-socorro se a saturação em casa cair abaixo de 88 ou se piorar a falta de ar. Retorno em 1 semana.
```

## 17-hipotireoidismo-levotiroxina (voz natural, 39.9 s, WER 0.0)

- sinal fc: esperado 62.0 / saiu None
- ponto para conferir [medio] pendencia: frequência cardíaca com valor não totalmente claro na gravação: 'sessenta e dois'

```
LIVRE: TSH 8,2 e T4 livre 0,8. Refere cansaço e sentir mais frio. Relata uso diário de levotiroxina em jejum, meia hora antes do café. Peso 70,5 kg. Tireoide sem nódulos à palpação. Ajustada levotiroxina para 75 mcg em jejum. Orientado repetir TSH em seis semanas.
```

## 18-lombalgia-doenca-renal (voz natural, 49.1 s, WER 0.071)

- faltou: paracetamol
- faltou: ciclobenzaprina
- fato ausente: 4 comprimidos|quatro comprimidos
- fato ausente: 7 dias|sete dias
- ponto para conferir [medio] inferido: Dor lombar após esforço.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: Remédio ouvido com dúvida: analgésico provavelmente 'paracetamol', com dose e posologia parcialmente incertas na gravação.
- ponto para conferir [medio] pendencia: Remédio ouvido com dúvida: 'ciclobenzaprina', com dose parcialmente incerta na gravação.
- ponto para conferir [info] cadastro: Doença renal crônica estágio 3 em contexto de filtração referida como 42.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere dor nas costas após carregar caixas. Pergunta se pode usar diclofenaco que tem em casa. Nega irradiação da dor para a perna. Nega febre.
O: Pressão arterial 134/84 mmHg. Dor à palpação da musculatura lombar. Sem déficit.
A: Dor lombar após esforço. Doença renal crônica estágio 3 em contexto de filtração referida como 42. Hipertensão arterial em acompanhamento.
P: Orientado que anti-inflamatório pode piorar a função renal e que não use diclofenaco. Losartana mantida. Prescritos analgésico e relaxante muscular, porém nome e/ou dose não ficaram totalmente claros na gravação.
```

## 19-dislipidemia-atorvastatina (voz natural, 39.3 s, WER 0.0)

- fato ausente: 160
- ponto para conferir [medio] inferido: Dislipidemia em tratamento, com LDL 142 e colesterol total 228.
- ponto para conferir [medio] pendencia: Exame/valor ouvido com dúvida: triglicérides 160.

```
S: Nega dor muscular. Nega fraqueza.
O: LDL 142 e colesterol total 228, em uso de atorvastatina. PA 118/76 mmHg. Peso 63 kg.
A: Dislipidemia em tratamento, com LDL 142 e colesterol total 228.
P: Ajustada atorvastatina para 40 mg à noite. Solicitado repetir perfil lipídico em três meses. Solicitado repetir enzimas do fígado em três meses.
```

## 20-enxaqueca-profilaxia (voz natural, 46.5 s, WER 0.047)

- avisado: propranolol esperado 40 mg 2x/dia iniciado / saiu   iniciado
- avisado: sumatriptana esperado 50 mg * iniciado / saiu  na crise, no máximo dois comprimidos por dia iniciado
- sinal pa_s: esperado 112.0 / saiu None
- sinal pa_d: esperado 72.0 / saiu None
- fato ausente: anticoncep
- ponto para conferir [medio] pendencia: A palavra antes de '112 por 72' foi ouvida com dúvida; medida não registrada em vitals.
- ponto para conferir [medio] pendencia: Dose e posologia do propranolol ficaram com dúvida na gravação.
- ponto para conferir [medio] pendencia: Dose da sumatriptana ficou com dúvida na gravação.

```
LIVRE: Refere enxaqueca cerca de seis vezes por mês, com enjoo e incômodo com luz. Nega asma.
Frequência cardíaca 76 bpm. Exame neurológico normal.
Consulta abordou prevenção de enxaqueca com propranolol. Orientado diário da dor. Retorno em dois meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.0)

- avisado: colchicina esperado 0,5 mg 8/8h iniciado / saiu 0,5 mg  iniciado
- sinal temp: esperado 37.2 / saiu None
- ponto para conferir [medio] inferido: Quadro de artrite aguda na primeira articulação do pé direito.
- ponto para conferir [medio] pendencia: Temperatura ouvida com dúvida: 'trinta e sete vírgula dois'.
- ponto para conferir [medio] pendencia: Posologia da colchicina ouvida com dúvida: 'de oito em oito horas'.
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere inchaço e vermelhidão no dedão do pé direito de início na madrugada, com dor intensa ao toque, a ponto de não conseguir encostar o lençol. Refere que é a primeira vez que apresenta esse quadro. Relata churrasco com cerveja no fim de semana.
O: Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: Quadro de artrite aguda na primeira articulação do pé direito. Hipertensão arterial em uso de hidroclorotiazida até a presente consulta.
P: Orientado gelo no local e repouso. Retorno em duas semanas. Alopurinol será considerado após a crise passar.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.013)

- fato ausente: 35 + 30
- ponto para conferir [medio] inferido: INR acima da meta terapêutica.
- ponto para conferir [medio] cid: CID I48.9 não existe na tabela (descartado)
- ponto para conferir [medio] dose_longe: Varfarina: 0,5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: Resposta sobre sangue na urina não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose prévia da varfarina ficou com áudio duvidoso.
- ponto para conferir [medio] pendencia: Descrição de ritmo cardíaco ficou com áudio duvidoso.
- ponto para conferir [info] cadastro: Varfarina: 5 mg 1x/dia; segunda e quinta, meio comprimido (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Varfarina: 5 mg 1x/dia; segunda e quinta, meio comprimido (dose do cadastro: confirme se não mudou)

```
S: Refere sangramento na gengiva ao escovar os dentes, com resolução espontânea. Nega sangue nas fezes e manchas roxas.
O: INR 3,8. Meta do INR entre 2 e 3. PA 128/76 mmHg. FC 70 bpm.
A: INR acima da meta terapêutica. Fibrilação atrial em uso de varfarina.
P: Ajustada varfarina para 30 por semana. Orientado repetir INR em uma semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.029)

- sem divergências

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Paciente refere menstruação muito forte, com duração de sete dias. Informado que se trata de anemia por falta de ferro.
Prescrito sulfato ferroso, um comprimido de 40 miligramas de ferro, duas vezes ao dia, longe das refeições, com suco de laranja. Orientado que pode haver escurecimento das fezes, considerado normal. Solicitado ultrassom transvaginal para investigar o sangramento. Programada repetição de hemograma e ferritina em dois meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.029)

- fato ausente: 44
- fato ausente: senta
- ponto para conferir [medio] inferido: Peso: 9,2 kg.
- ponto para conferir [medio] duvida: Desenvolvimento referido como ótimo para a idade. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Medida do perímetro cefálico não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Marco do desenvolvimento antes de 'sem apoio' não ficou claro na gravação.
- ponto para conferir [info] cadastro: Manter vitamina D 400 UI 1x/dia.
- ponto para conferir [info] cadastro: Vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Paciente em alimentação com papinha de legumes e fruta e ainda mama no peito.
O: Peso: 9,2 kg. Comprimento: 74 cm. Temperatura: 36,7 °C. Já engatinha. Vacinas em dia.
A: Desenvolvimento referido como ótimo para a idade.
P: Manter vitamina D 400 UI 1x/dia. Orientado oferecer água entre as refeições. Próxima vacina aos 12 meses. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.034)

- fato ausente: crepit
- ponto para conferir [alto] duvida_grave: carvedilol: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [alto] duvida_grave: enalapril: nome do remédio ouvido com dúvida. Confira se foi este o remédio.
- ponto para conferir [medio] inferido: Insuficiência cardíaca em seguimento, com relato de piora de edema em pernas, necessidade de dois travesseiros para dormir e ganho de peso na semana.
- ponto para conferir [medio] inferido: Hipertensão arterial em seguimento.
- ponto para conferir [medio] duvida: Mantido carvedilol 6,25 mg 2x/dia. (ouvido com dúvida: carvedilol)
- ponto para conferir [medio] duvida: Mantido enalapril 10 mg 2x/dia. (ouvido com dúvida: enalapril)
- ponto para conferir [medio] pendencia: Há dúvida de audição na gravação quanto aos nomes carvedilol e enalapril, embora constem no cadastro e tenham sido referidos como mantidos.
- ponto para conferir [info] cadastro: Refere ganho de cerca de 2 kg em 1 semana.
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere que as pernas incharam novamente. Refere dormir com dois travesseiros. Refere ganho de cerca de 2 kg em 1 semana.
O: Peso 78,4 kg. PA 118/72 mmHg. FC 68 bpm. Edema de pernas 2+/4+.
A: Insuficiência cardíaca em seguimento, com relato de piora de edema em pernas, necessidade de dois travesseiros para dormir e ganho de peso na semana. Hipertensão arterial em seguimento.
P: Ajustada furosemida para 40 mg duas vezes ao dia, de manhã e no começo da tarde. Mantido carvedilol 6,25 mg 2x/dia. Mantida espironolactona 25 mg 1x/dia. Mantido enalapril 10 mg 2x/dia. Orientado pesar-se todo dia de manhã. Solicitados potássio e creatinina em 1 semana. Retorno em 2 semanas.
```

## 26-insonia-sem-benzodiazepinico (voz natural, 51.0 s, WER 0.013)

- sem divergências
- ponto para conferir [medio] duvida: Perguntou sobre uso de clonazepam. (ouvido com dúvida: clonazepam)
- ponto para conferir [medio] duvida: Orientado que clonazepam não é recomendado, por risco de dependência e piora da memória. (ouvido com dúvida: clonazepam)
- ponto para conferir [medio] pendencia: medicamento citado com dúvida pela gravação: clonazepam

```
LIVRE: Paciente refere não conseguir dormir há três meses e que deita e fica pensando no trabalho. Relata uso de celular até tarde na cama. Refere ingerir café, cerca de cinco xícaras por dia. Perguntou sobre uso de clonazepam.
Orientado que clonazepam não é recomendado, por risco de dependência e piora da memória. Iniciada trazodona 50 mg à noite. Orientada a deixar o celular fora do quarto. Orientada a consumir café apenas até o almoço. Encaminhada para terapia cognitiva para insônia. Retorno em um mês.
```

## 27-renovacao-de-receita (voz natural, 28.5 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] inferido: Hiperplasia prostática em acompanhamento.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tansulosina: 0,4 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente veio para renovar receitas e refere estar bem. Nega tontura, inchaço e dificuldade para urinar. Refere urinar bem com o remédio da próstata.
O: Pressão arterial 132/80 mmHg. Frequência cardíaca 70 bpm.
A: Hipertensão arterial em acompanhamento. Hiperplasia prostática em acompanhamento.
P: Receitas renovadas nas mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (voz natural, 45.6 s, WER 0.046)

- fato ausente: 180 + 220
- ponto para conferir [medio] pendencia: Valores das glicemias em jejum citados no trecho 1 não ficaram claros na gravação.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em acompanhamento.
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere uso de insulina NPH 20 UI pela manhã e 10 UI à noite até a consulta. Nega hipoglicemia. Nega tremor e suor frio.
O: Hemoglobina glicada 9,4. Pressão arterial 136 por 82.
A: Diabetes tipo 2 em acompanhamento.
P: Ajustada insulina NPH noturna para 14 unidades. Mantida insulina NPH da manhã em 20 unidades. Mantida metformina. Orientado anotar as glicemias em jejum. Retorno em um mês.
```

## 29-micose-cetoconazol (voz natural, 30.6 s, WER 0.1)

- faltou: cetoconazol
- fato ausente: prurido|coca
- ponto para conferir [medio] pendencia: Nome do medicamento/creme orientado ficou duvidoso na gravação.
- ponto para conferir [medio] pendencia: A orientação inicial do trecho 2 ficou parcialmente ininteligível.

```
LIVRE: Refere mancha vermelha pruriginosa em virilha há cerca de três semanas. Relata jogar bola e ficar suado. Descreve placa avermelhada, com borda mais viva, em ambas as virilhas.
Orientado secar bem a região e usar roupa de algodão. Orientado retorno se não houver melhora em quatro semanas.
```

## 30-valor-corrigido (voz natural, 34.5 s, WER 0.038)

- faltou: hidroclorotiazida
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] pendencia: Medicação ouvida com dúvida na orientação de manutenção: 'Hidroclorotiazida 25 mg'.

```
S: Refere que, em casa, a pressão está parecida.
O: PA 140/90 mmHg. FC 76 bpm.
A: Pressão arterial um pouco acima da meta. Hipertensão arterial em acompanhamento.
P: Orientado reduzir o sal. Orientado medir a pressão em casa duas vezes por semana. Retorno em dois meses com as medidas.
```

## 31-exame-em-silencio (voz natural, 78.4 s, WER 0.013)

- fato ausente: raio x|radiografia
- ponto para conferir [medio] inferido: Tosse seca há três semanas.
- ponto para conferir [medio] pendencia: Trecho 2 com áudio pouco claro sobre exame: "Vou deitar ali para o senhor me examinar".

```
S: Paciente relata tosse seca há três semanas. Nega febre. Nega tabagismo. Refere azia às vezes à noite. Nega nariz escorrendo.
O: Pulmões limpos, sem sibilos. Garganta sem alterações. Saturação de oxigênio 98%.
A: Tosse seca há três semanas. Pode ser refluxo.
P: Iniciado omeprazol 20 mg em jejum por 4 semanas. Orientado elevar a cabeceira da cama. Se não melhorar, fazer raio-X do tórax. Retorno em 4 semanas.
```
