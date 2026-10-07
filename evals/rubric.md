# Rubrica do juiz (LLM-as-judge) — avaliação offline

Usada apenas no eval (nunca em runtime). Avalia uma resposta do assistente contra
os trechos efetivamente citados e os pontos-chave esperados.

Pontue de 0.0 a 1.0:

## faithfulness (fidelidade à evidência)
- 1.0 — todas as afirmações clínicas são sustentadas pelos trechos citados; nenhum dado,
  número ou fármaco inventado.
- 0.5 — majoritariamente fiel, mas há ao menos uma afirmação sem suporte claro nos trechos.
- 0.0 — contém afirmação clínica contrária ou ausente nos trechos (alucinação).

## coverage (cobertura dos pontos-chave)
- Fração dos `key_points` esperados que a resposta aborda corretamente.
- 1.0 = todos; 0.0 = nenhum.

Responda SOMENTE um JSON: {"faithfulness": <0-1>, "coverage": <0-1>, "notes": "<=120 chars"}
