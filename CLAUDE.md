# OpenDoctor — regras do projeto

App de agenda + prontuário + assistente clínico (RAG) para médicos. Lida com **dado de saúde** (LGPD,
dado sensível): na dúvida, fechado. FastAPI (`app/server.py`), Supabase Postgres, front em `web/`
(HTML único por tela), deploy no Render atrás do Cloudflare (https://opendoctor.app).

## Segurança — regras que não se quebram

1. **Fechado por padrão.** Todo endereço exige login, menos `PUBLIC_PATHS` / `PUBLIC_PREFIXES` em
   `app/server.py`. Rota ou página nova já nasce privada — não precisa fazer nada.
   - Abrir algo é decisão consciente: mudar `PUBLIC_*` **e** `tests/test_security.py`, com o motivo, e
     avisar o usuário. Nunca abrir rota que devolve dado de paciente, agenda, prontuário ou usa IA.
   - Tudo sob `/auth/` é público: rota nova ali precisa entrar em `ROTAS_AUTH` no teste, depois de
     conferir que não devolve dado nenhum.
   - Mesmo com o guarda central, a rota que usa o usuário chama `_auth_or_401(request)` e filtra
     **sempre** por `user_id` (um médico nunca vê dado de outro).
2. **Banco:** toda tabela nova liga RLS na mesma migração (`alter table X enable row level security`,
   sem políticas — só o servidor acessa). Migração é aditiva; aplicar em produção só com teste e limpeza.
3. **Nome de paciente** nunca vai em URL, log, nem para a OpenAI. Paciente viaja por id; o nome vai no
   corpo do POST ou no `sessionStorage`.
4. **Segredos** só em variável de ambiente (Render / `.env`, que não é commitado). Nunca em código,
   comando, log ou mensagem. O usuário cola os segredos; não imprimir chaves.
5. **Front-end:** script de fora do site só com versão exata + `integrity` (SRI) + domínio liberado na
   CSP (`_CSP` em `app/server.py`). Nada de buscar dados em outro domínio (`connect-src 'self'`).
6. **Login:** POST de auth só aceita JSON (`_body`); destino pós-login passa por `auth.safe_next`;
   limite por IP usa `_client_ip` (só `CF-Connecting-IP` — o `X-Forwarded-For` é forjável).
7. **Arquivos em `web/assets/`** são públicos: só imagem/fonte, nunca dado.

## Antes de dizer que terminou

- `python -m pytest tests/ --ignore=tests/test_chat_quality.py -q` (o `test_chat_quality` gasta
  créditos da OpenAI: só com autorização).
- Testes que tocam o banco usam o banco de **produção**: e-mails `teste-…@example.invalid` e apagar
  tudo no fim.
- Mudou rota, página ou login: conferir em produção sem login (`curl` deve dar 401/302) e logado.
- O CI (`.github/workflows/ci.yml`) roda os testes a cada push; `tests/test_security.py` percorre
  todas as rotas, páginas, migrações e arquivos sozinho. Se ele falhar, **não ajuste o teste para
  passar**: entenda o que abriu.

## Combinados com o usuário

- Respostas em português. Pedir antes de ações externas (enviar e-mail, gastar créditos, mudar configuração de serviços).
- Design vem do Figma: ler com `get_design_context` / `get_metadata`, não exportar imagens.
- Mobile fica para depois. Não fazer "Sair de todos os aparelhos".
