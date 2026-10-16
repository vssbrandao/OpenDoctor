"""Teste de qualidade das possíveis prescrições COM a OpenAI e a busca de verdade. GASTA CRÉDITO (≈ US$ 0,05 por
caso): rode só com o ok do usuário. Usa só pacientes fictícios (a Maria de app/exemplo e os casos abaixo); a busca só
LÊ a base de artigos. Mostra o perfil, as fontes, a saída conferida, o tempo e o custo de cada caso.

    .venv/bin/python -m scripts.presc_try            # só a Maria
    .venv/bin/python -m scripts.presc_try todos      # Maria + os outros casos
"""
import datetime as dt
import json
import sys
import time

import httpx

from app import config, exemplo, llm, prescricao as pr

PRECO = {"gpt-5.4": (2.50, 0.25, 15.00), "gpt-5.4-mini": (0.75, 0.075, 4.50)}     # US$ por 1M tokens (entrada, cache, saída)


def maria():
    now = dt.datetime.now()
    notas = [{"event_start": c["start"].isoformat(), "data": c["data"]} for c in exemplo.consultas(now)]
    notas += [{"event_start": e["date"].isoformat(), "data": e["data"]} for e in exemplo.exames(now)]
    return ({"name": exemplo.NAME, "birth_date": "1968-03-14", "sex": "F", "problems": exemplo.PROBLEMS,
             "medications": exemplo.MEDICATIONS, "allergies": exemplo.ALLERGIES}, notas)


def caso(nome, nasc, sexo, problemas, meds, alergias, vit, labs):
    hoje = dt.date.today().isoformat()
    return ({"name": nome, "birth_date": nasc, "sex": sexo, "problems": problemas, "medications": meds, "allergies": alergias},
            [{"event_start": hoje, "data": {"vitals": vit, "labs": {"date": hoje, "v": labs}}}])


CASOS = {
    "maria": maria,
    "drc": lambda: caso("João Teste", "1958-05-02", "M", "Hipertensão arterial\nDiabetes tipo 2\nDoença renal crônica",
                        "Metformina 850 mg 2x/dia\nLosartana 50 mg 12/12h\nGlibenclamida 5 mg 2x/dia", "",
                        {"pa_s": "148", "pa_d": "90", "peso": "82", "altura": "172"}, {"hba1c": "7,8", "creat": "1,9", "rac": "180", "pot": "5,1"}),
    "dm2": lambda: caso("Ana Teste", "1980-11-20", "F", "Diabetes tipo 2\nObesidade grau II",
                        "Metformina 850 mg 2x/dia", "Sulfa",
                        {"pa_s": "128", "pa_d": "80", "peso": "104", "altura": "165"}, {"hba1c": "9,1", "ldl": "142", "creat": "0,8"}),
}


def gerar(p, notas):
    texto, nums = pr.perfil(p, notas)
    t0 = time.monotonic()
    fts = pr.fontes(p, nums["tfg"])
    t1 = time.monotonic()
    body = llm._body(config.OPENAI_PRESC_MODEL, pr.build_messages(texto, fts), 0, 3000, config.REASONING_EFFORT)
    body["response_format"] = {"type": "json_object"}
    r = httpx.post(llm.URL, headers=llm._headers(), json=body, timeout=180)
    r.raise_for_status()
    j = r.json()
    raw, u = j["choices"][0]["message"]["content"], j.get("usage") or {}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    a, c, o = PRECO.get(config.OPENAI_PRESC_MODEL, PRECO["gpt-5.4"])
    usd = ((u.get("prompt_tokens", 0) - cached) * a + cached * c + u.get("completion_tokens", 0) * o) / 1e6
    return texto, fts, pr.finish(raw, p, fts, nums["tfg"]), json.loads(raw), {"busca_s": round(t1 - t0, 1), "modelo_s": round(time.monotonic() - t1, 1),
                                                                    "tokens": u, "usd": round(usd, 4)}


def main(argv):
    nomes = list(CASOS) if argv[1:2] == ["todos"] else ["maria"]
    total = 0
    for n in nomes:
        texto, fts, res, cru, m = gerar(*CASOS[n]())
        total += m["usd"]
        print(f"\n===== {n} =====\n{texto}\n\nfontes:")
        for h in fts:
            print(f"  {h['rotulo']} {str(h.get('publication_date') or '')[:4]} {h.get('evidence') or ''} · {(h.get('title') or '')[:90]}")
        print(f"\nmodelo devolveu {len(cru.get('itens') or [])} itens; conferidos {len(res['itens'])}, descartados {res['descartados']}")
        for it in res["itens"]:
            avisos = (" ⚠ alergia " + ", ".join(it["alergias"]) if it["alergias"] else "") + (f" ⚠ dose fora {it['faixa']}" if it["faixa"] else "") + (f" ⚠ renal: {it['renal']}" if it.get("renal") else "")
            print(f"  [{it['acao']}] {it['nome']} {it['dose']} · {it['posologia']} · {it['quantidade']} {it['fontes']}{avisos}\n      {it['motivo']}")
        if res["observacoes"]:
            print("  obs:", res["observacoes"])
        print(f"  tempo busca {m['busca_s']} s, modelo {m['modelo_s']} s · tokens {m['tokens'].get('prompt_tokens')} + "
              f"{m['tokens'].get('completion_tokens')} · US$ {m['usd']}")
    print(f"\ncusto total: US$ {round(total, 4)}")


if __name__ == "__main__":
    main(sys.argv)
