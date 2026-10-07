# OpenDoctor — Assistente clínico (RAG)

Backend do assistente clínico do OpenDoctor. RAG com fontes verificadas: o LLM é **redator**,
não fonte; todo conteúdo clínico vem de trechos recuperados (PubMed, PCDTs). Sem evidência
suficiente, o assistente **recusa** em vez de inventar.

Spec: ver `../docs/rag-plan.md` (diff estado atual × spec) e a spec enxuta original.

## Status

Fase **F0 — Fundação**. Entregue até aqui:
- Projeto git dedicado (só OpenDoctor; os demais protótipos ficam fora).
- Schema do Postgres/pgvector: `supabase/migrations/0001_init.sql` (`documents`, `chunks`, índices HNSW+GIN).
- Config trocável por env (`.env.example`): LLM, embeddings e rerank atrás de variáveis.

A construir (próximas fatias): ingestão PubMed (F1), busca híbrida (F2), síntese com streaming (F3).

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
