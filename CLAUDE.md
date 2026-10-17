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
   - Exceção aprovada (gravação da consulta, com autorização do paciente): o **áudio** de cada trecho vai
     só para a transcrição (`/v1/audio/transcriptions`, que não retém conteúdo) e pode conter o nome falado.
     Junto vão, como contexto, o fim do trecho anterior (sem CPF, telefone e e-mail: `scribe.mask_docs`; o nome
     fica, o áudio já o tem) e os nomes de remédios, problemas e alergias do cadastro. Todo outro **texto** que vai
     a um modelo passa antes por `scribe.mask` (nome → `[PACIENTE]`, CPF, telefone, e-mail) — inclusive a
     transcrição e a evolução anterior. O áudio nunca é gravado em disco, banco ou log;
     o log da gravação só leva números. Mudar isso (outro provedor, guardar áudio) pede revisão do
     `docs/ripd-gravacao.md` e da Política de Privacidade.
   - Possíveis prescrições (aba Prescrições, contas da gravação): vai ao modelo o perfil sem nome (sexo, idade, cadastro
     clínico, remédios das receitas anteriores, últimos sinais e exames; ainda por `scribe.mask`) e trechos da base do
     assistente. Como funciona e as
     pendências (médico revisor, RIPD): `docs/prescricao.md`.
4. **Segredos** só em variável de ambiente (Render / `.env`, que não é commitado). Nunca em código,
   comando, log ou mensagem. O usuário cola os segredos; não imprimir chaves.
5. **Front-end:** a CSP só roda os `<script>` escritos nas páginas (hash calculado ao subir o servidor)
   — **nunca** `onclick=`/`on*=` no HTML nem `javascript:`; use `addEventListener` (ou `data-href` no
   menu). Script de fora do site só com versão exata + `integrity` (SRI) + domínio liberado em `_CSP`.
   Nada de buscar dados em outro domínio (`connect-src 'self'`).
6. **Login:** POST de auth só aceita JSON (`_body`); destino pós-login passa por `auth.safe_next`;
   limite por IP usa `_client_ip` (só `CF-Connecting-IP` — o `X-Forwarded-For` é forjável).
7. **Arquivos em `web/assets/`** são públicos: só imagem/fonte, nunca dado.
   Bibliotecas de terceiros ficam em `web/vendor/<nome>-<versão>/` (só com login), copiadas do pacote
   oficial com o hash conferido e a LICENSE junto — nunca carregadas de fora em tempo de execução.
8. **Retenção** (`db.RETENTION`, limpeza diária no servidor): códigos de e-mail 1 dia, registro de
   acessos 1 ano. Prontuário, pacientes e `access_log` nunca entram na limpeza.

## Antes de dizer que terminou

- `python -m pytest tests/ -q`. O `tests/conftest.py` zera `DATABASE_URL`, `OPENAI_API_KEY` e
  `RESEND_API_KEY` durante os testes: eles nunca tocam produção, nunca gastam crédito, nunca mandam e-mail.
- **Banco de testes:** projeto Supabase separado (`TEST_DATABASE_URL` no `.env`), montado com
  `python -m scripts.setup_test_db` (rode de novo a cada migração). Teste de banco usa a fixture `test_db`
  (`tests/test_db_integration.py`). **Nunca** gravar em produção para testar; migração nova é aplicada
  primeiro no banco de testes.
- Mudou rota, página ou login: conferir em produção sem login (`curl` deve dar 401/302) e logado.
- Mudou a gravação da consulta (gravador na página, rotas `/prontuario/transcribe|scribe|recordings`, `app/stt.py`,
  `app/scribe.py`, `app/data/`): rodar o teste ponta a ponta `node tests/e2e/gravacao.mjs` contra o preview local
  (`.venv/bin/uvicorn scripts.preview_gravacao:app --port 8770`; `PREVIEW=` se a porta for outra). Como a gravação
  funciona e as decisões tomadas: `docs/gravacao.md` (manter em dia junto com o código).
- Mudou as possíveis prescrições (`app/prescricao.py`, `app/data/prescricao_prompt.txt`, `ajuste_renal.tsv`): `tests/test_prescricao.py`
  roda sem crédito; a qualidade de verdade é `python -m scripts.presc_try`, que **gasta crédito** — só com o ok do usuário.
- Mudou as receitas (aba Prescrições, rotas `/prontuario/receitas*`, `/me/medico`, `app/data/controlados.tsv`,
  `antimicrobianos.tsv`): rodar `node tests/e2e/prescricoes.mjs` contra um preview SÓ DELE (`PREVIEW=`, outra porta —
  ele limpa os dados do preview). Como funciona: `docs/prescricao.md`.
- O CI (`.github/workflows/ci.yml`) roda os testes a cada push; `tests/test_security.py` percorre
  todas as rotas, páginas, migrações e arquivos sozinho. Se ele falhar, **não ajuste o teste para
  passar**: entenda o que abriu.

## Combinados com o usuário

- Respostas em português. Pedir antes de ações externas (enviar e-mail, gastar créditos, mudar configuração de serviços).
- Design vem do Figma: ler com `get_design_context` / `get_metadata`, não exportar imagens.
- Mobile fica para depois. Não fazer "Sair de todos os aparelhos".
