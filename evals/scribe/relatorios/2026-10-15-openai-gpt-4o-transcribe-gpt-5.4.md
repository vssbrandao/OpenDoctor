# Avaliação da gravação — 2026-10-15 · gpt-4o-transcribe + gpt-5.4 · prompt 2026-10-15.4

| Critério | Passou? |
|---|---|
| 2_dose_errada_sem_aviso | sim |
| 3_nada_inventado | sim |
| 4_cobertura_95 | **não** |
| avisos_esperados | sim |
| nome_e_documentos_nao_vazaram | sim |
| todos_os_casos_rodaram | sim |

WER médio 0.116 · remédios {'rem_certo': 39, 'rem_aviso': 16, 'rem_sem_aviso': 0, 'rem_falta': 7, 'rem_inventado': 0} · sinais 46/68 · CID 24/33 · fatos 144/183 · proibidos 0

## 01-has-dm-tontura (voz natural, 111.6 s, WER 0.072)

- sem divergências
- ponto para conferir [medio] duvida: Refere glicemias de jejum entre 110 e 130. (ouvido com dúvida: entre)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 12/12h (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: atorvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Refere uso regular de losartana, metformina e medicação para colesterol. Refere caminhada 4 vezes por semana, cerca de 30 minutos. Relata dois episódios de tontura ao levantar da cama nesta semana. Informa que a tontura passa em menos de 1 minuto ao sentar. Nega desmaio, dor e falta de ar. Refere glicemias de jejum entre 110 e 130. Nega episódio de baixa de açúcar.
O: PA 128/82 mmHg e FC 74 bpm. Peso 86,8 kg. Glicemia no momento 108 mg/dL. Coração e pulmões sem alterações. Pés sem alterações, com pulsos presentes. Sensibilidade preservada ao monofilamento. Hemoglobina glicada 6,9.
A: Diabetes está na meta. Tontura ao levantar pode ser queda da pressão ao ficar em pé, conforme discutido na consulta.
P: Mantidos os três remédios em uso. Orientada a levantar devagar e sentar na cama por 1 minuto antes de ficar em pé. Solicitados exame de urina para os rins e ácido úrico. Retorno em 3 meses com os exames.
```

## 02-ajuste-dose-empagliflozina (voz natural, 71.5 s, WER 0.413)

- avisado: losartana esperado 100 mg 1x/dia ajustado / saiu  1x/dia ajustado
- avisado: empagliflozina esperado 10 mg 1x/dia iniciado / saiu  1 comprimido pela manhã iniciado
- sinal pa_s: esperado 152.0 / saiu None
- sinal pa_d: esperado 94.0 / saiu None
- sinal fc: esperado 80.0 / saiu None
- sinal peso: esperado 92.0 / saiu None
- fato ausente: creatinina + potassio
- fato ausente: 30 dias
- fato ausente: agua|hidrat
- fato ausente: infeccao urinaria|higiene
- fato ausente: 2 meses|dois meses
- ponto para conferir [medio] inferido: Hipertensão arterial em manejo na consulta.
- ponto para conferir [medio] inferido: Diabetes mellitus tipo 2 em manejo na consulta.
- ponto para conferir [medio] pendencia: Dose da losartana não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose da empagliflozina não ficou clara na gravação.

```
S: Paciente trouxe exames e referiu achar que não vieram muito bons.
O: Hemoglobina glicada: 8,1.
A: Hemoglobina glicada acima da meta. Hipertensão arterial em manejo na consulta. Diabetes mellitus tipo 2 em manejo na consulta.
P: Ajustada losartana para uma vez ao dia. Iniciada empagliflozina, um comprimido pela manhã. Mantida metformina 850 mg duas vezes ao dia. Orientado não esquecer a dose da noite da metformina.
```

## 03-fibrilacao-rivaroxabana (voz natural, 80.2 s, WER 0.235)

- faltou: rivaroxabana
- faltou: metoprolol
- sinal pa_s: esperado 138.0 / saiu None
- sinal pa_d: esperado 86.0 / saiu None
- sinal fc: esperado 112.0 / saiu None
- fato ausente: nega + sincope|desmai
- fato ausente: irregular
- fato ausente: jantar
- ponto para conferir [medio] duvida: Refere cansar mais para subir escada. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Resposta sobre desmaio não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre dor no peito não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre falta de ar deitado não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Medicamento ouvido com dúvida: rivaroxabana; dose ouvida com dúvida: 20 mg; posologia dita: uma vez ao dia junto com o jantar.
- ponto para conferir [medio] pendencia: Medicamento ouvido com dúvida: metoprolol suxinato; dose/posologia associadas a esse medicamento ficaram dependentes de nome ouvido com dúvida.
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: AAS: 100 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere coração disparando, com palpitações, há uma semana. Refere cansar mais para subir escada.
O: 
A: Hipertensão arterial em acompanhamento.
P: Orientada suspensão do AAS. Orientada manutenção do anlodipino. Solicitados ecocardiograma, TSH e função dos rins. Orientado procurar pronto-socorro se sangramento não parar, fezes pretas ou urina com sangue. Retorno em quatro semanas.
```

## 04-pediatria-otite (voz natural, 78.9 s, WER 0.222)

- avisado: amoxicilina esperado 8 ml 12/12h iniciado / saiu  12/12 horas, por 10 dias iniciado
- sinal temp: esperado 38.2 / saiu None
- sinal peso: esperado 16.0 / saiu None
- fato ausente: 38,5|38.5|38 e meio
- fato ausente: abaulad
- fato ausente: nega + vomito|diarreia
- ponto para conferir [medio] pendencia: Resposta sobre vômito, diarreia ou falta de ar não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Valor da febre máxima não ficou claro na gravação.
- ponto para conferir [medio] pendencia: Apresentação/concentração da amoxicilina não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Volume da amoxicilina por dose não ficou claro na gravação.

```
S: Mãe refere febre desde ontem. Mãe refere choro com dor no ouvido direito.
O: Ouvido direito vermelho e abalado; ouvido esquerdo normal. Garganta sem alterações. Pulmões sem alterações.
A: Otite média aguda.
P: Iniciada amoxicilina. Prescrito paracetamol em gotas, 16 gotas a cada 6 horas, se precisar, para febre ou dor. Orientado retornar antes se continuar com febre depois de 48 horas de antibiótico ou se ficar prostrado. Retorno em 10 dias.
```

## 05-prenatal-28-semanas (voz natural, 68.3 s, WER 0.02)

- fato ausente: dtpa
- ponto para conferir [medio] inferido: Gestação com 28 semanas, em acompanhamento pré-natal.
- ponto para conferir [medio] pendencia: vacina ouvida com dúvida: 'DTPa'
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: ácido fólico: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Gestante com 28 semanas hoje. Refere bebê mexendo bastante. Refere um pouco de azia à noite. Nega sangramento, perda de líquido e contrações.
O: Pressão arterial 110/70 mmHg. Peso 68,4 kg. Altura uterina 28 cm. Batimentos fetais 144 bpm.
A: Gestação com 28 semanas, em acompanhamento pré-natal. Azia noturna.
P: Iniciado sulfato ferroso 40 miligramas de ferro, um comprimido por dia, longe do café e do leite. Orientado parar ácido fólico. Solicitado TOTG de 75 gramas. Orientadas refeições menores e evitar deitar logo depois de comer por azia. Retorno em duas semanas.
```

## 06-idoso-queda-desprescricao (voz natural, 74.5 s, WER 0.312)

- avisado: diazepam esperado 5 mg * ajustado / saiu   ajustado
- fato ausente: em pe + 112
- fato ausente: sentado + 138
- fato ausente: luz
- fato ausente: 1 mes|um mes
- ponto para conferir [alto] duvida_grave: Anlodipino: 5 ouvido com dúvida
- ponto para conferir [medio] inferido: Queda noturna ao levantar-se para ir ao banheiro, precedida de escurecimento visual.
- ponto para conferir [medio] duvida: Queda noturna ao levantar-se para ir ao banheiro, precedida de escurecimento visual. (ouvido com dúvida: levantar)
- ponto para conferir [medio] pendencia: dose do diazepam na redução inicial não ficou clara na gravação
- ponto para conferir [info] cadastro: Omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Omeprazol: 20 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Anlodipino: 5 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Sinvastatina: 20 mg à noite (dose do cadastro: confirme se não mudou)

```
S: Paciente teve queda no banheiro de madrugada na semana passada e bateu o braço. Relata que, ao ir ao banheiro, a vista escureceu antes da queda. Refere não ter mais sintoma de estômago.
O: PA 112/70 mmHg. FC 72 bpm. Peso 61 kg. Braço com hematoma, sem dor para mexer.
A: Queda noturna ao levantar-se para ir ao banheiro, precedida de escurecimento visual. Diazepam foi relacionado a aumento do risco de queda. Sem sintomas gástricos no momento.
P: Reduzir diazepam por duas semanas e depois suspender. Suspender omeprazol. Manter amlodipino. Manter sinvastatina.
```

## 07-depressao-sertralina (voz natural, 62.9 s, WER 0.019)

- avisado: sertralina esperado 100 mg * ajustado / saiu   ajustado
- fato ausente: dorme mal|insonia|sono
- ponto para conferir [medio] pendencia: Dose da sertralina após ajuste não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Posologia da sertralina após ajuste não ficou clara na gravação.

```
S: Refere melhora parcial desde o início da sertralina há dois meses, porém ainda sem vontade de fazer as coisas. Refere dormir mal e chorar com facilidade. Nega pensamentos de se machucar ou de morrer. Refere enjoo no início do uso da sertralina, já resolvido.
O: Questionário de hoje com 15 pontos.
A: Depressão moderada.
P: Orientado aumento da sertralina. Encaminhamento para psicoterapia. Orientada procura imediata de ajuda se surgirem pensamentos de se machucar, podendo ligar no 188. Retorno em 4 semanas.
```

## 08-asma-crise (voz natural, 68.8 s, WER 0.043)

- avisado: prednisolona esperado 40 mg 1x/dia iniciado / saiu  1 vez ao dia por 5 dias iniciado
- ponto para conferir [medio] inferido: Realizado salbutamol em 3 séries de 4 jatos a cada 20 minutos, com espaçador.
- ponto para conferir [medio] inferido: Asma em acompanhamento, com piora de falta de ar e sibilância na consulta.
- ponto para conferir [medio] pendencia: Dose da prednisolona não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Trecho ouvido com dúvida na orientação final: destino do atendimento em caso de piora.

```
S: Paciente refere falta de ar desde ontem e chiado importante. Refere que o spray não está resolvendo. Relata uso da bombinha seis vezes hoje. Refere gripe na semana passada.
O: Saturação 93%, frequência respiratória 24 irpm e frequência cardíaca 104 bpm. Sibilos em ambos os pulmões. Realizado salbutamol em 3 séries de 4 jatos a cada 20 minutos, com espaçador. Após as 3 séries, saturação 97% e sibilos bem menores.
A: Asma em acompanhamento, com piora de falta de ar e sibilância na consulta.
P: Prescrita prednisolona 1 vez ao dia por 5 dias. Iniciada budesonida com formoterol, 2 jatos de 12/12h. Orientado buscar atendimento se piora da falta de ar ou se a boca ficar roxa. Retorno em 1 semana.
```

## 09-meio-comprimido-captopril (voz natural, 47.4 s, WER 0.0)

- avisado: hidroclorotiazida esperado 25 mg 1x/dia iniciado / saiu  1 comprimido pela manhã iniciado
- ponto para conferir [medio] inferido: Hipertensão arterial em controle inadequado, com medidas elevadas em casa e na consulta.
- ponto para conferir [medio] pendencia: Dose da hidroclorotiazida não ficou clara na gravação: '25 miligramas'.

```
S: Refere pressão arterial em casa sempre alta, com medidas de 160 e 150. Relata estar tomando meio comprimido de captopril, pois foi orientada de que era forte.
O: Pressão arterial hoje: 156/92 mmHg. Frequência cardíaca hoje: 78 bpm.
A: Hipertensão arterial em controle inadequado, com medidas elevadas em casa e na consulta.
P: Orientado captopril 25 mg, 1 comprimido inteiro, duas vezes ao dia. Iniciado hidroclorotiazida, 1 comprimido pela manhã. Orientado medir a pressão arterial em casa e anotar. Retorno em quatro semanas com as medidas de pressão arterial.
```

## 10-cistite-alergia-sulfa (voz natural, 54.9 s, WER 0.011)

- avisado: nitrofurantoina esperado 100 mg 6/6h iniciado / saiu  de 6 em 6 horas por 5 dias iniciado
- ponto para conferir [medio] inferido: Quadro de ardência ao urinar e aumento da frequência urinária há 2 dias, sem febre, dor nas costas ou hematúria relatadas.
- ponto para conferir [medio] pendencia: dose da nitrofurantoína não ficou clara na gravação: "100 mg"

```
S: Paciente relata ardência para urinar há 2 dias e vontade de urinar toda hora. Nega febre, dor nas costas e sangue na urina. Pergunta sobre usar Bactrim novamente; orientada a não usar por alergia a sulfa.
O: Temperatura 36,8 °C. Abdome sem dor. Punho-percussão negativa.
A: Quadro de ardência ao urinar e aumento da frequência urinária há 2 dias, sem febre, dor nas costas ou hematúria relatadas.
P: Iniciada nitrofurantoína, com orientação de uso de 6 em 6 horas por 5 dias. Orientado beber bastante água. Orientado retornar se tiver febre ou dor nas costas. Sem necessidade de retorno se houver melhora.
```

## 11-alergia-penicilina-esquecida (voz natural, 43.5 s, WER 0.0)

- avisado: amoxicilina esperado 875 mg 12/12h iniciado / saiu   iniciado
- fato ausente: 12 dias|doze dias
- fato ausente: 7 dias|sete dias
- ponto para conferir [alto] alergia: amoxicilina com alergia registrada a Penicilina
- ponto para conferir [medio] pendencia: duração dos sintomas foi ouvida com dúvida: 'doze dias'
- ponto para conferir [medio] pendencia: dose da amoxicilina foi ouvida com dúvida
- ponto para conferir [medio] pendencia: posologia da amoxicilina foi ouvida com dúvida

```
S: Paciente refere nariz entupido e dor no rosto. Relata que o quadro começou como gripe e piorou novamente. Refere febre de 38 ontem.
O: Temperatura 37,6 no momento da consulta. Dor à palpação em seios maxilares. Secreção amarelada na garganta.
A: 
P: Prescrita amoxicilina. Orientada lavagem nasal com soro três vezes ao dia. Orientado retorno se não houver melhora em três dias.
```

## 12-metformina-sem-dose (voz natural, 36.4 s, WER 0.0)

- sem divergências
- ponto para conferir [medio] pendencia: Nova dose e posologia da metformina não foram ditas.
- ponto para conferir [info] cadastro: Diabetes tipo 2 em acompanhamento.

```
S: Refere que exagerou na dieta durante as festas.
O: Hemoglobina glicada 7,8. Pressão arterial 124 por 78. Peso 74 quilos.
A: Diabetes tipo 2 em acompanhamento. Hemoglobina glicada ainda acima.
P: Aumentada metformina. Orientada reforço de dieta. Orientado cortar refrigerante e doce. Solicitada repetição da hemoglobina glicada em três meses.
```

## 13-nomes-terceiros-e-cpf (voz natural, 65.8 s, WER 0.071)

- faltou: paracetamol
- faltou: ciclobenzaprina
- fato ausente: 7 dias|sete dias
- fato ausente: compressa|calor
- ponto para conferir [medio] duvida: Nega dor descendo para a perna, formigamento, perda de força e alteração urinária. (ouvido com dúvida: para)
- ponto para conferir [medio] pendencia: Dose e posologia do paracetamol não ficaram seguras na gravação.
- ponto para conferir [medio] pendencia: Dose e posologia da ciclobenzaprina não ficaram seguras na gravação.

```
LIVRE: Paciente refere que travou as costas ao carregar o filho no sábado. Refere que a dor fica apenas na lombar. Nega dor descendo para a perna, formigamento, perda de força e alteração urinária. Lasegue negativo. Força preservada. Quadro definido como lombalgia mecânica. Orientado retorno se a dor descer para a perna.
```

## 14-ruido-alto-gastrite (voz natural, 41.3 s, WER 0.042)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum por 8 semanas iniciado
- fato ausente: epigast
- ponto para conferir [medio] pendencia: dose do omeprazol não ficou clara na gravação
- ponto para conferir [medio] pendencia: localização da dor abdominal no exame não ficou clara na gravação

```
S: Refere queimação no estômago há 1 mês. Relata piora quando come e à noite. Refere uso de ibuprofeno quase todo dia para dor de cabeça. Nega vômito com sangue e fezes pretas.
O: Abdome com dor leve. Pressão arterial 126/80 mmHg.
A: Queixa de queimação no estômago há 1 mês, com piora alimentar e noturna. Uso frequente de ibuprofeno.
P: Orientado a parar o ibuprofeno. Prescrito omeprazol em jejum por 8 semanas. Solicitada pesquisa de Helicobacter pylori nas fezes. Retorno em 8 semanas.
```

## 15-pedido-dentro-da-fala (voz natural, 55.9 s, WER 0.083)

- sem divergências

```
S: Refere dor de cabeça no fim do dia, em aperto, bilateral. Nega náusea, piora com luz, alteração de força e alteração de visão. Refere estresse no trabalho.
O: Pressão arterial 122/80 mmHg. Exame neurológico normal.
A: Cefaleia tensional.
P: Orientado dipirona 1 grama se dor, até de 6 em 6 horas. Orientados alongamento e pausas no trabalho. Retorno se piorar.
```

## 16-dpoc-exacerbacao (voz natural, 62.5 s, WER 0.351)

- faltou: prednisona
- sinal spo2: esperado 91.0 / saiu None
- sinal fr: esperado 22.0 / saiu None
- sinal fc: esperado 96.0 / saiu None
- fato ausente: escarro|expector
- fato ausente: nega + febre
- fato ausente: sibil
- ponto para conferir [medio] inferido: DPOC em manejo nesta consulta.
- ponto para conferir [medio] pendencia: Termo do trecho inicial não ficou claro na gravação: ouvido como 'carro'/'caroço', descrito como esverdeado e aumentado.
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: tiotrópio: 2,5 mcg 2 jatos 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Relata piora do cansaço há quatro dias.
O: 
A: DPOC em manejo nesta consulta.
P: Iniciada azitromicina 500 miligramas, uma vez ao dia, por três dias. Mantido tiotrópio. Acrescentada budesonida com formoterol 12 por 400, uma inalação de 12 em 12 horas. Orientado procurar pronto-socorro se a saturação em casa cair abaixo de 88 ou se houver piora da falta de ar. Retorno em uma semana.
```

## 17-hipotireoidismo-levotiroxina (voz natural, 39.9 s, WER 0.509)

- faltou: levotiroxina
- sinal fc: esperado 62.0 / saiu None
- sinal peso: esperado 70.5 / saiu None
- fato ausente: 6 semanas|seis semanas
- ponto para conferir [medio] pendencia: Não ficou claro na gravação o intervalo entre a levotiroxina e o café da manhã; foi ouvido 'meia ... hora antes do café?' com dúvida.

```
LIVRE: TSH 8,2 e T4 livre 0,8. Refere cansaço e mais frio. Questionado uso de levotiroxina em jejum.
```

## 18-lombalgia-doenca-renal (voz natural, 49.1 s, WER 0.262)

- avisado: paracetamol esperado 750 mg 6/6h iniciado / saiu  de 6/6h se dor, no máximo 4 cp/dia iniciado
- avisado: ciclobenzaprina esperado 5 mg * iniciado / saiu  à noite por 7 dias iniciado
- sinal pa_s: esperado 134.0 / saiu None
- sinal pa_d: esperado 84.0 / saiu None
- fato ausente: nega + febre|irradia
- ponto para conferir [medio] inferido: Dor nas costas após esforço.
- ponto para conferir [medio] inferido: Doença renal crônica estágio 3 em acompanhamento.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [medio] cid: CID N18.3 não existe na tabela (descartado)
- ponto para conferir [medio] pendencia: Resposta sobre irradiação da dor para a perna não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Resposta sobre febre não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose do paracetamol não ficou clara na gravação.
- ponto para conferir [medio] pendencia: Dose da ciclobenzaprina não ficou clara na gravação.
- ponto para conferir [info] cadastro: Doença renal crônica estágio 3 em acompanhamento.
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: losartana: 50 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere dor nas costas após carregar caixas. Perguntou se poderia tomar diclofenaco que tem em casa. Relata última filtração de 42.
O: Sem déficit.
A: Dor nas costas após esforço. Doença renal crônica estágio 3 em acompanhamento. Hipertensão arterial em acompanhamento.
P: Orientado a não usar diclofenaco. Registrado que anti-inflamatório pode piorar a função renal. Prescrito paracetamol se dor, de 6/6h, no máximo 4 comprimidos por dia. Prescrita ciclobenzaprina à noite por 7 dias. Losartana mantida.
```

## 19-dislipidemia-atorvastatina (voz natural, 39.3 s, WER 0.02)

- fato ausente: nega + dor muscular|mialgia
- ponto para conferir [medio] inferido: Dislipidemia em acompanhamento.

```
S: Nega fraqueza e dor.
O: LDL 142, colesterol total 228 e triglicérides 160. Pressão arterial 118/76 mmHg. Peso 63 kg.
A: Dislipidemia em acompanhamento.
P: Ajustada atorvastatina para 40 mg à noite. Repetir perfil lipídico e enzimas do fígado em três meses.
```

## 20-enxaqueca-profilaxia (voz natural, 46.5 s, WER 0.375)

- faltou: propranolol
- sinal pa_s: esperado 112.0 / saiu None
- sinal pa_d: esperado 72.0 / saiu None
- sinal fc: esperado 76.0 / saiu None
- fato ausente: nega + asma
- fato ausente: anticoncep
- ponto para conferir [medio] pendencia: Há menção a medicação de uso regular com dose 'quarenta miligramas duas vezes ao dia', mas o nome do remédio não ficou claro na gravação.

```
LIVRE: Paciente refere enxaqueca cerca de seis vezes por mês, com enjoo e incômodo com a luz.
Orientado fazer diário da dor. Prescrita sumatriptana 50 mg na crise, no máximo dois comprimidos por dia. Retorno em dois meses.
```

## 21-gota-colchicina (voz natural, 60.1 s, WER 0.0)

- avisado: colchicina esperado 0,5 mg 8/8h iniciado / saiu  de 8 em 8 horas, até melhorar, no máximo, por uma semana iniciado
- ponto para conferir [medio] inferido: Quadro agudo em primeira articulação do pé direito, com calor, edema e vermelhidão.
- ponto para conferir [medio] pendencia: Dose da colchicina não ficou clara na gravação.
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere inchaço e vermelhidão no dedão do pé direito desde a madrugada, com dor ao toque, a ponto de não conseguir encostar o lençol. Refere que é a primeira vez que apresenta o quadro. Relata churrasco com cerveja no fim de semana.
O: Temperatura 37,2. Primeira articulação do pé direito com calor, edema e vermelhidão. Ácido úrico do último exame: 9,1.
A: Hipertensão arterial em manejo medicamentoso. Quadro agudo em primeira articulação do pé direito, com calor, edema e vermelhidão.
P: Orientado gelo no local e repouso. Retorno em duas semanas. Médico informou que a hidroclorotiazida aumenta o ácido úrico. Médico informou que vai considerar alopurinol após a crise passar.
```

## 22-varfarina-inr (voz natural, 46.8 s, WER 0.027)

- fato ausente: 35 + 30
- ponto para conferir [medio] inferido: Fibrilação atrial em uso de varfarina.
- ponto para conferir [medio] inferido: INR acima da meta terapêutica.
- ponto para conferir [medio] cid: CID I48.9 não existe na tabela (descartado)
- ponto para conferir [medio] dose_longe: varfarina: 0,5 está no trecho, mas não junto do nome do remédio
- ponto para conferir [medio] pendencia: Resposta sobre sangue na urina não ficou clara na gravação.
- ponto para conferir [info] cadastro: varfarina: 5 mg todos os dias, exceto segunda e quinta com meio comprimido (dose do cadastro: confirme se não mudou)

```
S: Relata sangramento na gengiva ao escovar os dentes, com parada espontânea. Nega sangue nas fezes e manchas roxas.
O: INR 3,8. Meta de INR entre 2 e 3. Frequência cardíaca 70, irregular.
A: Fibrilação atrial em uso de varfarina. INR acima da meta terapêutica.
P: Ajustada varfarina para 30 mg por semana: 5 mg todos os dias, exceto segunda e quinta com meio comprimido. Repetir INR em uma semana.
```

## 23-anemia-ferro-sem-exame-fisico (voz natural, 42.4 s, WER 0.13)

- avisado: sulfato ferroso esperado 40 mg 2x/dia iniciado / saiu  duas vezes ao dia, longe das refeições, com suco de laranja iniciado
- fato ausente: menstrua + 7 dias|sete dias|intensa|forte
- ponto para conferir [medio] pendencia: Dose do sulfato ferroso não ficou clara na gravação: '40 miligramas de ferro'.

```
LIVRE: Hemoglobina 10,2 e ferritina 8. Médico informou que se trata de anemia por falta de ferro.
Orientado que as fezes podem escurecer com o uso do ferro, sendo isso esperado. Solicitado ultrassom transvaginal para investigação de sangramento. Programada repetição de hemograma e ferritina em dois meses.
```

## 24-puericultura-9-meses (voz natural, 46.4 s, WER 0.043)

- sinal peso: esperado 9.2 / saiu None
- fato ausente: 74
- fato ausente: 44
- ponto para conferir [medio] pendencia: peso ouvido com dúvida na gravação
- ponto para conferir [medio] pendencia: perímetro cefálico ouvido com dúvida na gravação
- ponto para conferir [medio] pendencia: comprimento registrado sem dúvida, porém sem unidade explicitada além de 'setenta e quatro centímetros'
- ponto para conferir [info] cadastro: Manter vitamina D 400 UI 1x/dia.
- ponto para conferir [info] cadastro: Vitamina D: 400 UI 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Paciente está comendo papinha de legumes e fruta e mama no peito ainda. Vacinas estão em dia.
O: Temperatura 36,7 °C. Senta sem apoio e já engatinha.
A: Desenvolvimento referido como adequado para a idade.
P: Manter vitamina D 400 UI 1x/dia. Oferecer água entre as refeições. Próxima vacina aos 12 meses. Retorno com 12 meses.
```

## 25-insuficiencia-cardiaca (voz natural, 51.3 s, WER 0.148)

- sinal peso: esperado 78.4 / saiu None
- fato ausente: 2 quilos|dois quilos|2 kg
- fato ausente: crepit
- ponto para conferir [medio] inferido: Insuficiência cardíaca em acompanhamento, com relato de piora de edema em pernas e necessidade de dormir com dois travesseiros.
- ponto para conferir [medio] inferido: Hipertensão arterial em acompanhamento.
- ponto para conferir [info] cadastro: espironolactona: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere que as pernas incharam novamente. Refere estar dormindo com dois travesseiros.
O: Pressão arterial 118/72 mmHg. Frequência cardíaca 68 bpm. Edema de pernas 2+/4+.
A: Insuficiência cardíaca em acompanhamento, com relato de piora de edema em pernas e necessidade de dormir com dois travesseiros. Hipertensão arterial em acompanhamento.
P: Ajustada furosemida para 40 mg, duas vezes ao dia, de manhã e no começo da tarde. Mantido carvedilol 6,25 mg 2x/dia. Mantida espironolactona 25 mg 1x/dia. Mantido enalapril 10 mg 2x/dia. Orientado pesar todo dia de manhã. Solicitados potássio e creatinina em uma semana. Retorno em duas semanas.
```

## 26-insonia-sem-benzodiazepinico (voz natural, 51.0 s, WER 0.039)

- avisado: trazodona esperado 50 mg * iniciado / saiu  à noite iniciado
- ponto para conferir [medio] pendencia: Dose da trazodona não ficou clara na gravação.

```
LIVRE: Paciente refere dificuldade para dormir há três meses, com pensamentos sobre o trabalho ao deitar. Refere uso de café, cerca de cinco xícaras por dia. Perguntou sobre uso de clonazepam, e foi orientada que não é recomendado por causar dependência e piora da memória. Orientada a deixar o celular fora do quarto e restringir café até o almoço. Encaminhada para terapia cognitiva para insônia. Retorno em um mês.
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
S: Veio para renovação de receita e refere estar tudo bem, sem queixas. Nega tontura, inchaço e dificuldade para urinar. Refere urinar bem com o remédio da próstata.
O: Pressão arterial 132/80 mmHg. Frequência cardíaca 70 bpm.
A: Hipertensão arterial em acompanhamento. Hiperplasia prostática em acompanhamento.
P: Renovadas as medicações nas mesmas doses de sempre. Retorno em seis meses.
```

## 28-insulina-nph (voz natural, 45.6 s, WER 0.062)

- fato ausente: 180 + 220
- ponto para conferir [medio] duvida: Nega hipoglicemia, tremor e suor frio. (ouvido com dúvida: tremor)
- ponto para conferir [info] cadastro: Diabetes mellitus tipo 2 em acompanhamento.
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)
- ponto para conferir [info] cadastro: Metformina: 850 mg 2x/dia (dose do cadastro: confirme se não mudou)

```
S: Relata glicemias em jejum entre 120 e 182. Refere uso de insulina NPH 20 UI pela manhã e 10 UI à noite. Nega hipoglicemia, tremor e suor frio.
O: Hemoglobina glicada 9,4. Pressão arterial 136/82 mmHg.
A: Diabetes mellitus tipo 2 em acompanhamento.
P: Ajustada insulina NPH da noite para 14 unidades. Mantida insulina NPH 20 UI pela manhã. Mantida metformina. Orientado anotar as glicemias em jejum. Retorno em 1 mês.
```

## 29-micose-cetoconazol (voz natural, 30.6 s, WER 0.033)

- fato ausente: prurido|coca
- ponto para conferir [medio] pendencia: dose do cetoconazol creme não foi dita

```
LIVRE: Paciente refere mancha vermelha pruriginosa em virilha há cerca de três semanas. Relata que joga bola e fica suado. Descreve placa avermelhada com borda mais viva em ambas as virilhas. Informado diagnóstico de micose em virilha.
Prescrito cetoconazol creme, 2 vezes ao dia por 4 semanas, mantendo uso mesmo após sumirem as lesões. Orientado secar bem a região e usar roupa de algodão. Orientado retornar se não houver melhora em 4 semanas.
```

## 30-valor-corrigido (voz natural, 34.5 s, WER 0.019)

- sem divergências
- ponto para conferir [alto] duvida_grave: hidroclorotiazida: 25 ouvido com dúvida
- ponto para conferir [info] cadastro: hidroclorotiazida: 25 mg 1x/dia (dose do cadastro: confirme se não mudou)

```
S: Refere pressão arterial em casa parecida com a medida da consulta.
O: Pressão arterial: 140/90 mmHg. Frequência cardíaca: 76 bpm.
A: Pressão arterial um pouco acima da meta. Hipertensão arterial em acompanhamento.
P: Mantida hidroclorotiazida. Orientada redução do sal. Orientada aferição da pressão arterial em casa duas vezes por semana. Retorno em dois meses com as medidas.
```

## 31-exame-em-silencio (voz natural, 78.4 s, WER 0.038)

- avisado: omeprazol esperado 20 mg * iniciado / saiu  em jejum por quatro semanas iniciado
- sinal spo2: esperado 98.0 / saiu None
- fato ausente: raio x|radiografia
- ponto para conferir [medio] pendencia: valor da saturação não ficou claro na gravação
- ponto para conferir [medio] pendencia: dose do omeprazol não ficou clara na gravação
- ponto para conferir [medio] pendencia: achado de garganta não ficou claro na gravação

```
S: Paciente refere tosse seca há três semanas. Nega febre. Nega tabagismo. Refere azia às vezes à noite. Nega nariz escorrendo.
O: Pulmões limpos, sem sibilos.
A: Possibilidade de refluxo considerada na consulta.
P: Iniciado omeprazol em jejum por quatro semanas. Orientado elevar a cabeceira da cama. Se não melhorar, considerar raio-x de tórax. Retorno em quatro semanas.
```
