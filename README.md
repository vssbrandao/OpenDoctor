# OpenDoctor — Assistente clínico (RAG)

Backend do assistente clínico do OpenDoctor. RAG com fontes verificadas: o LLM é **redator**,
não fonte; todo conteúdo clínico vem de trechos recuperados (PubMed, PCDTs). Sem evidência
suficiente, o assistente **recusa** em vez de inventar.

Spec: ver `../docs/rag-plan.md` (diff estado atual × spec) e a spec enxuta original.

## Status

- **F0 — Fundação** ✔ git dedicado, schema Postgres/pgvector aplicado no Supabase, config por env.
- **F1 — Ingestão PubMed** ✔ `app/` com cliente E-utilities, chunking, embeddings e CLI `ingest`.
- A construir: busca híbrida (F2), síntese com streaming (F3).

## Rodar a ingestão (F1)

```bash
cd opendoctor-assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # preencha DATABASE_URL e OPENAI_API_KEY

# ingere artigos do PubMed para uma busca
python -m app.ingest --source pubmed --query "heart failure preserved ejection fraction SGLT2" --retmax 20
```

- Idempotente: reexecutar não duplica (dedup por `content_hash`).
- `DATABASE_URL`: use a string do Supabase (Project Settings → Database). Para o app, porta 6543 (pooler); para rodar scripts/migração, 5432 (direct) funciona bem.
- Embeddings custam por token na OpenAI; `text-embedding-3-small` é barato.

## Stack

| Componente | Decisão |
|---|---|
| Banco + busca | Postgres (Supabase) com **pgvector** + full-text nativo |
| Embeddings | API gerenciada — `text-embedding-3-small` (1536 dims), multilíngue |
| Rerank | Só entra se o eval mostrar que vale (atrás de interface trocável) |
| LLM | OpenAI `gpt-4o-mini` (provedor atual) — exige DPA p/ dado de paciente (LGPD) |

## Setup do Supabase

1. Criar um projeto em https://supabase.com (região mais próxima do Brasil — ex.: `sa-east-1`).
2. Pegar a connection string em **Project Settings → Database** e a Service Role key em
   **Project Settings → API**. Preencher no `.env` (copiado de `.env.example`).
3. Aplicar a migração (uma das opções):
   - **SQL Editor (mais simples):** colar o conteúdo de `supabase/migrations/0001_init.sql` e rodar.
   - **psql:** `psql "$DATABASE_URL" -f supabase/migrations/0001_init.sql`
   - **Supabase CLI:** `supabase link` + `supabase db push`
4. Conferir: `select extname from pg_extension where extname='vector';` deve retornar `vector`.

> `pgvector` já vem disponível no Supabase; a migração faz `create extension if not exists vector`.

## Segurança

- `.env` nunca vai para o git (ver `.gitignore`).
- LGPD: de-identificar dados de paciente **antes** de enviar ao LLM (fase F0/F4) e manter logs sem PII.
