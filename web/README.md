# web — front-end do OpenDoctor (protótipo)

Tela da **agenda** com o painel do assistente (Figma 946-31168). O painel direito
conversa via `POST /api/chat`, servido pelo `proxy.py` (passa a pergunta à OpenAI,
mantendo a chave só no servidor).

A agenda está **ligada ao backend RAG**: o painel usa `GET /ask` (SSE) — mostra as fontes
antes da resposta, faz streaming das frases validadas e deixa as citações `[n]` clicáveis.

## Rodar (RAG — recomendado)

O FastAPI serve a própria agenda, então é um servidor só:

```bash
cd opendoctor-assistant
source .venv/bin/activate
uvicorn app.server:app --port 8000
# abra http://127.0.0.1:8000/opendoctor-agenda.html
```

Respostas vêm das fontes ingeridas (PubMed); fora do corpus, o assistente recusa.
Para cobrir mais temas, ingira mais artigos (ver README da raiz, `app.ingest`).

## Rodar (proxy GPT simples — alternativo, sem RAG)

`proxy.py` ainda existe para usar o GPT puro (sem busca em fontes), com respostas
mais "livres" e diagramas Mermaid:

```bash
cd opendoctor-assistant/web && python3 proxy.py
# http://127.0.0.1:8899/opendoctor-agenda.html
```

Ambos usam a `OPENAI_API_KEY` do `.env` da raiz (`../.env`).

## Conteúdo
- `opendoctor-agenda.html` — a tela (SVGs inline; fontes em `assets/fonts/`)
- `assets/fonts/` — Helvetica Now Display (Regular/Medium/Bold)
- `proxy.py` — servidor estático + proxy `/api/chat` (OpenAI), sem dependências
