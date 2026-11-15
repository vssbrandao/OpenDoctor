"""Antes × depois do assistente clínico: as mesmas 10 perguntas de prontuário (fictícias, SEM nome) passam pelo fluxo real
do /ask (server._ask_stream) em duas configurações e saem lado a lado, com as medidas de forma de cada resposta.

  ANTES  = prompts/clinical_answer.v3.md, esforço "low", verbosidade "low", limite de 2000 tokens
  DEPOIS = o prompt atual (synthesize.PROMPT_PATH) com a configuração atual (config.ASK_*; dá para trocar pelas variáveis
           ASK_REASONING_EFFORT, ASK_VERBOSITY e ASK_MAX_TOKENS)

GASTA CRÉDITO da OpenAI (planejamento + embeddings + resposta, 2× por pergunta): rode só com o ok do usuário.
A busca só LÊ a base de artigos; nada é gravado no banco durante a rodada (ver sem_gravar). O log não leva o texto
das perguntas, só o número.

    .venv/bin/python -m scripts.compara_respostas --out /caminho/da/saida            # as 10
    .venv/bin/python -m scripts.compara_respostas --only 1,3 --out /caminho           # um subconjunto
    .venv/bin/python -m scripts.compara_respostas --so-depois --out /caminho          # só o DEPOIS (metade do custo)
    .venv/bin/python -m scripts.compara_respostas --dry-run --out /caminho            # sem OpenAI e sem banco (testa o encanamento)
"""
import argparse
import contextlib
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time

# 10 perguntas como as que o prontuário monta (dados fictícios, nenhum nome). A 1ª é a do teste com o ChatGPT (15/11/2026).
PERGUNTAS = [
    ("dm2-has", "Mulher de 58 anos com hipertensão arterial e diabetes tipo 2, em uso de losartana 50 mg 12/12h, metformina "
     "850 mg 2x/dia e atorvastatina 20 mg à noite; alergia a dipirona e penicilina. Últimos sinais vitais: pressão arterial "
     "128/82 mmHg (na referência), peso 86,8 kg, glicemia 108 mg/dL (na referência), frequência cardíaca 74 bpm (na "
     "referência). Exames de acompanhamento atrasados ou sem registro: hemoglobina glicada (HbA1c) (sem registro; a cada 6 "
     "meses), perfil lipídico (sem registro; anual), creatinina e TFG (sem registro; anual), albuminúria (RAC) (sem registro; "
     "anual), potássio (sem registro; anual), ácido úrico (sem registro; anual), TGP (ALT) (sem registro; anual). Todos os "
     "sinais e exames com faixa de referência estão dentro dela. Quais metas e qual rotina de acompanhamento (exames, "
     "rastreamentos e intervalo de retorno) são recomendadas para esse perfil?"),
    ("has-isolada", "Homem de 49 anos com hipertensão arterial, em uso de anlodipino 5 mg 1x/dia; sem alergias conhecidas. "
     "Últimos sinais vitais: pressão arterial 138/88 mmHg (acima da referência), peso 92 kg, altura 1,78 m, frequência "
     "cardíaca 70 bpm (na referência). Exames de acompanhamento atrasados ou sem registro: creatinina e TFG (sem registro; "
     "anual), potássio (sem registro; anual), perfil lipídico (sem registro; anual), glicemia de jejum (sem registro; anual), "
     "urina tipo 1 (sem registro; anual), eletrocardiograma (sem registro; anual). Quais metas e qual rotina de acompanhamento "
     "(exames, rastreamentos e intervalo de retorno) são recomendadas para esse perfil?"),
    ("dislipidemia-primaria", "Mulher de 52 anos com dislipidemia, sem doença cardiovascular conhecida, não fumante, em uso "
     "de rosuvastatina 10 mg à noite; sem alergias conhecidas. Últimos sinais vitais: pressão arterial 122/78 mmHg (na "
     "referência), peso 70 kg, altura 1,63 m. Últimos exames: LDL-c 142 mg/dL (acima da referência), HDL-c 48 mg/dL, "
     "triglicerídeos 168 mg/dL (acima da referência), glicemia de jejum 96 mg/dL (na referência). Exames sem registro: TGP "
     "(ALT) e CK. Quais metas e qual rotina de acompanhamento (exames, estratificação de risco e intervalo de retorno) são "
     "recomendadas para esse perfil em prevenção primária?"),
    ("drc3-dm2", "Homem de 66 anos com diabetes tipo 2 e doença renal crônica estágio 3a, em uso de metformina 500 mg 2x/dia, "
     "enalapril 10 mg 12/12h e sinvastatina 40 mg à noite; alergia a sulfa. Últimos sinais vitais: pressão arterial 136/84 "
     "mmHg (acima da referência), peso 81 kg. Últimos exames: creatinina 1,5 mg/dL, TFG estimada 48 mL/min/1,73 m² (abaixo da "
     "referência), relação albumina/creatinina 120 mg/g (acima da referência), potássio 5,0 mEq/L (na referência), HbA1c "
     "7,4% (acima da referência). Exames sem registro: hemograma, cálcio, fósforo, PTH e vitamina D. Quais metas e qual rotina "
     "de acompanhamento (exames, rastreamentos e intervalo de retorno) são recomendadas para esse perfil?"),
    ("dm2-hba1c-alta", "Mulher de 61 anos com diabetes tipo 2 há 9 anos, em uso de metformina 1000 mg 2x/dia e gliclazida MR "
     "60 mg pela manhã; sem alergias conhecidas. Últimos sinais vitais: pressão arterial 126/80 mmHg (na referência), peso "
     "79 kg, altura 1,60 m, glicemia 186 mg/dL (acima da referência). Últimos exames: HbA1c 9,1% (acima da referência), TFG "
     "estimada 78 mL/min/1,73 m² (na referência), LDL-c 118 mg/dL (acima da referência). Exames sem registro: albuminúria "
     "(RAC), fundo de olho, avaliação dos pés. Qual a meta glicêmica, como intensificar o tratamento e qual rotina de "
     "acompanhamento (exames, rastreamentos e intervalo de retorno) é recomendada para esse perfil?"),
    ("idoso-polifarmacia", "Homem de 81 anos com hipertensão arterial, fibrilação atrial, hiperplasia prostática benigna e "
     "insônia, em uso de losartana 50 mg 12/12h, hidroclorotiazida 25 mg, varfarina 5 mg, tansulosina 0,4 mg, omeprazol 20 "
     "mg, clonazepam 0,5 mg à noite e ácido acetilsalicílico 100 mg; sem alergias conhecidas. Últimos sinais vitais: pressão "
     "arterial 118/70 mmHg sentado, peso 64 kg, frequência cardíaca 78 bpm. Duas quedas nos últimos 6 meses. Exames sem "
     "registro: creatinina e TFG, sódio, potássio, INR recente, hemograma, vitamina B12. Quais metas, que revisão dos "
     "medicamentos e qual rotina de acompanhamento (exames, rastreamentos e intervalo de retorno) são recomendadas para esse "
     "perfil?"),
    ("has-resistente", "Mulher de 57 anos com hipertensão arterial, em uso de losartana 100 mg/dia, anlodipino 10 mg/dia e "
     "clortalidona 25 mg/dia, com boa adesão referida; sem alergias conhecidas. Últimos sinais vitais: pressão arterial "
     "152/94 mmHg no consultório (acima da referência), peso 88 kg, altura 1,62 m, frequência cardíaca 76 bpm. Últimos "
     "exames: potássio 3,6 mEq/L (na referência), creatinina 0,9 mg/dL, TFG estimada 74 mL/min/1,73 m². Exames sem "
     "registro: MAPA, aldosterona e renina, polissonografia, ecocardiograma. Quais metas, que investigação e qual rotina de "
     "acompanhamento (exames e intervalo de retorno) são recomendadas para esse perfil?"),
    ("pos-iam", "Homem de 63 anos com infarto agudo do miocárdio há 4 meses (angioplastia com stent farmacológico), "
     "hipertensão e ex-tabagismo, em uso de ácido acetilsalicílico 100 mg, ticagrelor 90 mg 12/12h, atorvastatina 80 mg, "
     "metoprolol 50 mg 12/12h e ramipril 5 mg; sem alergias conhecidas. Últimos sinais vitais: pressão arterial 124/76 mmHg "
     "(na referência), frequência cardíaca 62 bpm, peso 84 kg. Últimos exames: LDL-c 68 mg/dL (acima da meta), HbA1c 5,9%, "
     "TFG estimada 82 mL/min/1,73 m². Exames sem registro: ecocardiograma de controle, TGP (ALT), CK. Quais metas e qual "
     "rotina de acompanhamento (exames, reabilitação e intervalo de retorno) são recomendadas para esse perfil?"),
    ("obesidade-prediabetes", "Mulher de 44 anos com obesidade e pré-diabetes, sem medicamentos em uso; sem alergias "
     "conhecidas. Últimos sinais vitais: pressão arterial 132/84 mmHg (acima da referência), peso 104 kg, altura 1,65 m, "
     "circunferência abdominal 108 cm. Últimos exames: glicemia de jejum 112 mg/dL (acima da referência), HbA1c 6,1% (acima "
     "da referência), triglicerídeos 190 mg/dL (acima da referência), HDL-c 41 mg/dL, TGP (ALT) 52 U/L (acima da "
     "referência). Exames sem registro: TSH, LDL-c, ultrassonografia de abdome. Quais metas e qual rotina de acompanhamento "
     "(exames, rastreamentos, opções de tratamento e intervalo de retorno) são recomendadas para esse perfil?"),
    ("icc-cronica", "Homem de 70 anos com insuficiência cardíaca crônica de fração de ejeção reduzida (FEVE 32%), classe "
     "funcional NYHA II, em uso de sacubitril/valsartana 49/51 mg 12/12h, carvedilol 12,5 mg 12/12h, espironolactona 25 mg, "
     "dapagliflozina 10 mg e furosemida 40 mg pela manhã; sem alergias conhecidas. Últimos sinais vitais: pressão arterial "
     "108/68 mmHg, frequência cardíaca 72 bpm, peso 77 kg (2 kg acima do peso seco). Últimos exames: potássio 5,2 mEq/L "
     "(acima da referência), creatinina 1,3 mg/dL, TFG estimada 55 mL/min/1,73 m², sódio 136 mEq/L. Exames sem registro: "
     "NT-proBNP, ferritina e saturação de transferrina, ecocardiograma de controle. Quais metas, que otimização do "
     "tratamento e qual rotina de acompanhamento (exames e intervalo de retorno) são recomendadas para esse perfil?"),
]

K = 6                     # o mesmo k padrão do /ask
ANTES = {"rotulo": "ANTES", "prompt": "clinical_answer.v3.md", "reasoning": "low", "verbosity": "low", "max_tokens": 2000}


# ===== medidas de forma (iguais nas duas versões) =====
_CITA = re.compile(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]")
_CERCA = re.compile(r"^\s*(```|~~~)")


def _fora_das_cercas(texto):
    """Linhas fora dos blocos ``` (o ```plano usa "## Prazo | …" por dentro: não conta como seção)."""
    dentro, fora = False, []
    for ln in texto.splitlines():
        if _CERCA.match(ln):
            dentro = not dentro
            continue
        if not dentro:
            fora.append(ln)
    return fora


def medidas(texto):
    linhas = _fora_das_cercas(texto or "")
    tabelas, em_tabela = 0, False
    for ln in linhas:
        if ln.lstrip().startswith("|"):
            if not em_tabela:
                tabelas += 1
            em_tabela = True
        else:
            em_tabela = False
    citas = _CITA.findall(texto or "")
    ns = {int(n) for c in citas for n in re.findall(r"\d+", c)}
    return {
        "palavras": len(re.findall(r"\w+", texto or "")),
        "secoes": sum(1 for ln in linhas if ln.startswith("## ")),
        "tabelas": tabelas,
        "planos": len(re.findall(r"^\s*```plano\b", texto or "", re.M)),
        "citacoes": len(citas),
        "fontes_citadas": len(ns),
    }


# ===== leitura do fluxo SSE do /ask =====
def _evento(raw):
    ev, data = None, None
    for ln in raw.splitlines():
        if ln.startswith("event: "):
            ev = ln[7:].strip()
        elif ln.startswith("data: "):
            data = json.loads(ln[6:])
    return ev, data or {}


def coletar(stream):
    """Consome o gerador do _ask_stream: texto final (frases concatenadas, como o cliente faz), fontes, fim e tempos."""
    t0 = time.monotonic()
    frases, fontes, recomendados, fim, aviso, primeira = [], [], [], {}, None, None
    for raw in stream:
        ev, d = _evento(raw)
        if ev == "sentence":
            if primeira is None:
                primeira = time.monotonic() - t0
            frases.append(d.get("text") or "")
        elif ev == "sources":
            fontes, recomendados = d.get("sources") or [], d.get("recommended") or []
        elif ev in ("insufficient", "failed"):
            aviso = {"tipo": ev, "texto": d.get("text") or d.get("message") or ""}
        elif ev == "done":
            fim = {k: v for k, v in d.items() if k != "sig"}
    texto = "".join(frases) or (aviso or {}).get("texto", "")
    return {"texto": texto, "fontes": fontes, "recomendados": recomendados, "fim": fim, "aviso": aviso,
            "segundos": round(time.monotonic() - t0, 2),
            "primeira_frase_s": round(primeira, 2) if primeira is not None else None}


# ===== nada gravado no banco durante a rodada =====
@contextlib.contextmanager
def sem_gravar(registro=None):
    """Caminhos de escrita do _ask_stream, neutralizados enquanto roda:
      - server._bg_enrich (thread que busca no PubMed e chama ingest.persist) → não roda;
      - server._safe_persist (thread que grava o resultado do PubMed ao vivo, o "cacheable") → não grava;
      - ingest.persist (grava documentos e trechos) → não grava;
      - db.upsert_document(s_bulk) / db.insert_chunks(_bulk) → erro, se algo chegar lá por outro caminho.
    O resto do _ask_stream só lê (search.search, ingest.fetch_and_embed = PubMed + embeddings em memória)."""
    from app import server, ingest, db
    registro = registro if registro is not None else []

    def _anota(nome):
        def f(*a, **k):
            registro.append(nome)
        return f

    def _proibido(nome):
        def f(*a, **k):
            registro.append(nome)
            raise RuntimeError(f"compara_respostas: escrita no banco bloqueada ({nome})")
        return f

    trocas = [(server, "_bg_enrich", _anota("_bg_enrich")), (server, "_safe_persist", _anota("_safe_persist")),
              (ingest, "persist", _anota("ingest.persist"))]
    trocas += [(db, n, _proibido("db." + n)) for n in ("upsert_document", "upsert_documents_bulk",
                                                       "insert_chunks", "insert_chunks_bulk")]
    velhos = [(m, n, getattr(m, n)) for m, n, _ in trocas]
    try:
        for m, n, f in trocas:
            setattr(m, n, f)
        yield registro
    finally:
        for m, n, f in velhos:
            setattr(m, n, f)


@contextlib.contextmanager
def configuracao(prompt, reasoning, verbosity, max_tokens):
    """Troca o prompt e o esforço/verbosidade/limite da resposta; devolve tudo como estava ao sair."""
    from app import config, synthesize
    velho = (synthesize.PROMPT_PATH, config.ASK_REASONING_EFFORT, config.ASK_VERBOSITY, config.ASK_MAX_TOKENS)
    try:
        synthesize.PROMPT_PATH = os.path.join(config.ROOT, "prompts", prompt)
        config.ASK_REASONING_EFFORT, config.ASK_VERBOSITY, config.ASK_MAX_TOKENS = reasoning, verbosity, max_tokens
        yield
    finally:
        synthesize.PROMPT_PATH, config.ASK_REASONING_EFFORT, config.ASK_VERBOSITY, config.ASK_MAX_TOKENS = velho


def configs(so_depois=False):
    from app import config, synthesize
    depois = {"rotulo": "DEPOIS", "prompt": os.path.basename(synthesize.PROMPT_PATH),
              "reasoning": config.ASK_REASONING_EFFORT, "verbosity": config.ASK_VERBOSITY,
              "max_tokens": config.ASK_MAX_TOKENS}
    return [depois] if so_depois else [dict(ANTES), depois]


def _ask_falso(query, k, history=None, contexto=None):
    """--dry-run: o formato do _ask_stream sem OpenAI e sem banco. A resposta muda com o prompt e o limite em uso."""
    from app import server, synthesize, config
    v4 = not synthesize.PROMPT_PATH.endswith("v3.md")
    yield server._sse("status", {"stage": "searched", "best_sim": 0.5})
    yield server._sse("sources", {"sources": [{"n": 1, "title": "Diretriz fictícia", "url": "https://exemplo.org/1",
                                               "evidence": "Diretriz", "year": 2024}], "recommended": []})
    partes = ["**A avaliação atual é favorável:** resposta de teste [1].\n\n"]
    if v4:
        partes += ["## 1. Metas\n\n", "| Parâmetro | Meta |\n|---|---|\n| HbA1c | < 7% [1] |\n\n",
                   "## 2. Plano\n\n", "```plano\n## Agora | Exames\n- HbA1c.\n```\n\n"]
    partes.append(f"**Minha recomendação:** teste ({config.ASK_REASONING_EFFORT}, {config.ASK_MAX_TOKENS}).")
    for p in partes:
        yield server._sse("sentence", {"text": p})
    yield server._sse("done", {"insufficient": False, "cited": [1], "sig": "x"})


def rodar(selecao, out, ask=None, log=print, so_depois=False):
    """Roda cada pergunta escolhida (1-based) nas duas configurações; grava um .md por pergunta e o resumo.json."""
    from app import server
    ask = ask or server._ask_stream
    os.makedirs(out, exist_ok=True)
    cfgs = configs(so_depois)
    resumo = {"quando": dt.datetime.now().isoformat(timespec="seconds"), "k": K, "configs": cfgs, "perguntas": []}
    for i in selecao:
        slug, q = PERGUNTAS[i - 1]
        item = {"n": i, "id": slug, "resultados": {}}
        md = [f"# {i:02d}. {slug}\n", "## Pergunta\n", q + "\n"]
        for c in cfgs:
            bloqueios = []
            with configuracao(c["prompt"], c["reasoning"], c["verbosity"], c["max_tokens"]), sem_gravar(bloqueios):
                r = coletar(ask(q, K))
            m = medidas(r["texto"])
            item["resultados"][c["rotulo"]] = {**m, "segundos": r["segundos"], "primeira_frase_s": r["primeira_frase_s"],
                                               "fontes": len(r["fontes"]), "aviso": (r["aviso"] or {}).get("tipo"),
                                               "fim": r["fim"], "escritas_bloqueadas": bloqueios}
            log(f"[compara] pergunta {i} {c['rotulo']}: {m['palavras']} palavras, {r['segundos']} s "
                f"(1ª frase {r['primeira_frase_s']} s)"
                + (f", bloqueado: {sorted(set(bloqueios))}" if bloqueios else ""))
            md += [f"\n---\n\n## {c['rotulo']} — {c['prompt']} · esforço {c['reasoning']} · verbosidade {c['verbosity']} · "
                   f"limite {c['max_tokens']}\n",
                   f"_{m['palavras']} palavras · {m['secoes']} seções · {m['tabelas']} tabelas · {m['planos']} planos · "
                   f"{m['citacoes']} citações · {r['segundos']} s_\n", r["texto"] + "\n", "\n### Fontes\n"]
            # como a tela: só as fontes citadas no texto (as outras foram ao modelo, mas não aparecem para o médico)
            ns_cit = {int(n) for n in re.findall(r"\[(\d+)\]", r["texto"])}
            cit = [s for s in r["fontes"] if s.get("n") in ns_cit]
            md += [f"- [{s.get('n')}] {s.get('title') or ''} ({s.get('evidence') or s.get('source_type') or ''}, "
                   f"{s.get('year') or 's/d'}) {s.get('url') or ''}" for s in cit] or ["- (nenhuma citada)"]
            if len(cit) < len(r["fontes"]):
                md.append(f"- _(mais {len(r['fontes']) - len(cit)} enviadas ao modelo e não citadas: "
                          + "; ".join((s.get("title") or "")[:70] for s in r["fontes"] if s not in cit) + ")_")
        with open(os.path.join(out, f"{i:02d}-{slug}.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")
        resumo["perguntas"].append(item)
    with open(os.path.join(out, "resumo.json"), "w", encoding="utf-8") as fh:
        json.dump(resumo, fh, ensure_ascii=False, indent=2)
    return resumo


def tabela(resumo):
    cols = ("palavras", "secoes", "tabelas", "planos", "citacoes", "primeira_frase_s", "segundos")
    linhas = ["  n  " + "".join(f"{c[:8]:>18}" for c in cols)]
    for p in resumo["perguntas"]:
        a, d = p["resultados"].get("ANTES", {}), p["resultados"].get("DEPOIS", {})
        linhas.append(f"{p['n']:>3}  " + "".join(f"{str(a.get(c, '-')) + ' → ' + str(d.get(c, '-')):>18}" for c in cols))
    return "\n".join(linhas)


def _selecao(only):
    if not only:
        return list(range(1, len(PERGUNTAS) + 1))
    ns = [int(x) for x in re.split(r"[,\s]+", only.strip()) if x]
    if not ns or any(n < 1 or n > len(PERGUNTAS) for n in ns):
        raise SystemExit(f"--only: números de 1 a {len(PERGUNTAS)}")
    return ns


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "opendoctor-compara",
                                                  dt.datetime.now().strftime("%Y%m%d-%H%M%S")))
    ap.add_argument("--only", help="pergunta(s) a rodar, ex.: 1 ou 1,4,7 (padrão: todas)")
    ap.add_argument("--dry-run", action="store_true", help="sem OpenAI e sem banco: só o encanamento")
    ap.add_argument("--so-depois", action="store_true", help="roda só a configuração atual (metade do custo)")
    a = ap.parse_args(argv)
    sel = _selecao(a.only)
    if a.dry_run:
        # antes de importar o app: sem chave e sem banco, um acesso esquecido dá erro em vez de gastar ou gravar
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DATABASE_URL"] = ""
    resumo = rodar(sel, a.out, ask=_ask_falso if a.dry_run else None, so_depois=a.so_depois)
    print(tabela(resumo))
    print("saída:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
