# Rubrica do juiz (LLM-as-judge) — avaliação offline

Usada apenas no eval (nunca em runtime). Avalia uma resposta do assistente contra
os trechos recuperados e os pontos-chave esperados.

Política do assistente: ele USA a evidência recuperada (citando [n]) e PODE
complementar com conhecimento clínico consolidado SEM citação, desde que não
o apresente como vindo de uma fonte e não invente dados específicos.

Pontue de 0.0 a 1.0:

## faithfulness (fidelidade / honestidade das fontes)
- 1.0 — toda afirmação com [n] é sustentada pelo trecho [n]; nenhum número, ensaio,
  estatística ou referência inventado; o conteúdo sem citação é conhecimento clínico
  correto e consolidado.
- 0.5 — majoritariamente fiel, mas ao menos uma afirmação atribuída a [n] não está
  clara no trecho, OU um dado específico sem fonte parece impreciso.
- 0.0 — atribui a um trecho algo que ele não diz, inventa dado/ensaio, ou contém
  afirmação clínica incorreta/perigosa.

## coverage (cobertura dos pontos-chave)
- Fração dos `key_points` esperados que a resposta aborda corretamente.
- 1.0 = todos; 0.0 = nenhum.

Responda SOMENTE um JSON: {"faithfulness": <0-1>, "coverage": <0-1>, "notes": "<=120 chars"}
