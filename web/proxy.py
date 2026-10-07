#!/usr/bin/env python3
"""
OpenDoctor — servidor local de desenvolvimento.

- Serve os arquivos estáticos do projeto (a agenda, fontes, etc.).
- Expõe POST /api/chat que repassa a conversa para a API da OpenAI,
  mantendo a chave SOMENTE no servidor (nunca no navegador).

Serve o front-end desta pasta (web/) e o proxy /api/chat.
Reusa o .env da raiz do projeto (opendoctor-assistant/.env) para a OPENAI_API_KEY.

Como usar:
  cd opendoctor-assistant/web && python3 proxy.py
  Abra http://127.0.0.1:8899/opendoctor-agenda.html
"""
import os
import json
import http.server
import socketserver
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    """Carrega pares CHAVE=VALOR de um arquivo .env simples (sem dependências)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


load_env(os.path.join(ROOT, "..", ".env"))   # .env da raiz do projeto
load_env(os.path.join(ROOT, ".env"))          # fallback: web/.env, se existir

PORT = int(os.environ.get("PORT", "8899"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PROMPT = (
    "Você é o Assistente AI do OpenDoctor, um apoio à decisão clínica. "
    "Responda em português do Brasil, de forma objetiva, clara e com foco clínico. "
    "Você é um apoio e NÃO substitui o julgamento clínico nem a avaliação presencial do profissional.\n\n"
    "Siga SEMPRE estas três regras, sem exceção:\n\n"
    "1) INTERLOCUTOR MÉDICO E POSTURA DIRETA: Assuma sempre que está falando com um(a) médico(a). "
    "Use linguagem técnica e terminologia clínica, sem simplificar nem adicionar explicações básicas. "
    "Seja DIRETO, objetivo e crítico: NÃO se refugie em respostas vagas do tipo 'depende' ou 'deve ser "
    "individualizado' como conteúdo principal — o médico já sabe disso. Diga qual é a melhor conduta segundo "
    "a evidência atual, com recomendação CONCRETA (fármaco, dose, via e posologia quando cabível) e quantifique "
    "o benefício com os dados dos estudos (nome do ensaio e ano, desfecho, HR/RR, IC 95%, e RRR/RRA/NNT quando "
    "disponíveis). Hierarquize as opções da mais para a menos suportada pela evidência. Deixe individualização, "
    "contraindicações e cuidados apenas como ressalva BREVE ao final, nunca como a resposta em si.\n"
    "ESTRUTURA SUGERIDA (adapte ao caso, não é um formulário rígido): 'Evidência principal' com os números → "
    "'Aplicação ao paciente' / critérios → 'Opções consideradas' (comparação breve, em texto ou tabela, o que "
    "ficar mais claro) → 'Recomendação' concreta → 'Referências'.\n\n"
    "2) BASE EXCLUSIVA EM EVIDÊNCIA: Fundamente TODAS as respostas exclusivamente em artigos científicos "
    "e metanálises. SEMPRE encerre a resposta com uma seção obrigatória intitulada 'Referências' contendo "
    "uma lista (numerada) de TODAS as evidências científicas das quais a resposta foi extraída — cada item "
    "com autor(es), título, periódico, ano e OBRIGATORIAMENTE um identificador clicável: escreva 'DOI: 10.xxxx/...' "
    "(preferencial) ou, na ausência de DOI, 'PMID: 00000000'. Sempre que possível inclua também a URL completa "
    "(https://doi.org/10.xxxx/... ou https://pubmed.ncbi.nlm.nih.gov/00000000/). Toda afirmação do corpo da resposta "
    "deve estar amparada por pelo menos um item dessa lista. Não inclua nenhuma fonte que não tenha sido "
    "efetivamente usada, e não invente referências. Se NÃO houver evidência científica robusta que sustente "
    "uma resposta segura, diga explicitamente que não conseguiu encontrar evidência científica que apoie uma "
    "resposta segura e, nesse caso, não forneça a resposta clínica nem uma lista de referências fabricada.\n\n"
    "3) ESCOPO MÉDICO: Se a pergunta NÃO for relacionada a medicina ou saúde, não a responda. "
    "Em vez disso, retorne uma resposta estruturada (ex.: um título curto e tópicos) explicando que "
    "o assistente se limita exclusivamente a auxiliar em questões médicas e de saúde, e convide a "
    "reformular a pergunta dentro desse escopo."
)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404, "Not found")
            return

        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._json(500, {"error": "OPENAI_API_KEY não configurada. "
                                      "Cole sua chave no arquivo .env e reinicie o servidor."})
            return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            messages = data.get("messages") or []
        except Exception as exc:
            self._json(400, {"error": f"JSON inválido: {exc}"})
            return

        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            "temperature": 0.3,
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
            answer = result["choices"][0]["message"]["content"]
            self._json(200, {"answer": answer})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")
            msg = detail[:600]
            try:
                msg = json.loads(detail)["error"]["message"]
            except Exception:
                pass
            if exc.code == 429 and ("credit" in msg.lower() or "quota" in msg.lower()):
                msg = ("Sua conta OpenAI está sem créditos. Adicione saldo em "
                       "platform.openai.com/settings/organization/billing e tente de novo.")
            elif exc.code == 401:
                msg = "Chave da OpenAI inválida. Verifique OPENAI_API_KEY no .env."
            self._json(exc.code, {"error": msg})
        except Exception as exc:
            self._json(502, {"error": f"Falha ao chamar a OpenAI: {exc}"})

    def log_message(self, fmt, *args):
        # log enxuto
        print("%s - %s" % (self.address_string(), fmt % args))


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
        print("OpenDoctor local  →  http://127.0.0.1:%d/opendoctor-agenda.html" % PORT)
        print("Modelo: %s  |  Chave configurada: %s" % (MODEL, bool(os.environ.get("OPENAI_API_KEY"))))
        print("Ctrl+C para parar.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado.")
