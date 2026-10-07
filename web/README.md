# web — front-end do OpenDoctor (protótipo)

Tela da **agenda** com o painel do assistente (Figma 946-31168). O painel direito
conversa via `POST /api/chat`, servido pelo `proxy.py` (passa a pergunta à OpenAI,
mantendo a chave só no servidor).

> Este é o protótipo de UI. O assistente **com RAG** (busca em fontes + citações) é o
> backend em `../app/` (servidor `uvicorn app.server:app`). Ligar a agenda ao backend RAG
> é um passo futuro; hoje o painel usa o proxy simples.

## Rodar

```bash
cd opendoctor-assistant/web
python3 proxy.py
# abra http://127.0.0.1:8899/opendoctor-agenda.html
```

Usa a `OPENAI_API_KEY` (e `OPENAI_MODEL`) do `.env` da raiz do projeto (`../.env`).

## Conteúdo
- `opendoctor-agenda.html` — a tela (SVGs inline; fontes em `assets/fonts/`)
- `assets/fonts/` — Helvetica Now Display (Regular/Medium/Bold)
- `proxy.py` — servidor estático + proxy `/api/chat` (OpenAI), sem dependências
