# web — front-end do OpenDoctor (protótipo)

Tela da **agenda** com o painel do assistente (Figma 946-31168), **ligada ao backend RAG**:
o painel usa `GET /ask` (SSE) — mostra as fontes antes da resposta, faz streaming das
frases validadas e deixa as citações `[n]` clicáveis. Sem evidência nas fontes, consulta
o PubMed ao vivo antes de responder.

## Rodar

O FastAPI (`app/`) serve a própria agenda — um servidor só:

```bash
cd opendoctor-assistant
source .venv/bin/activate
uvicorn app.server:app --port 8000
# abra http://127.0.0.1:8000/opendoctor-agenda.html
```

Usa a `OPENAI_API_KEY` do `.env` da raiz do projeto (`../.env`).

## Conteúdo
- `opendoctor-agenda.html` — a tela (SVGs inline; fontes em `assets/fonts/`)
- `assets/fonts/` — Helvetica Now Display (Regular/Medium/Bold)
