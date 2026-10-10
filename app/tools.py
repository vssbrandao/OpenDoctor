"""Ferramentas clínicas DETERMINÍSTICAS (código, não o LLM).

O LLM erra aritmética com potências (ex.: CKD-EPI). Aqui os valores são
calculados de forma exata e injetados no prompt; o modelo só explica.
"""
import re
import json

from . import llm, config

# palavras que indicam pedido de função renal
_RENAL_RE = re.compile(r"\b(e?gfr|tfg|taxa de filtra[cç][aã]o|filtra[cç][aã]o glomerular|"
                       r"clearance|clear?ance de creatinina|ckd-?epi|cockcroft|fun[cç][aã]o renal)\b",
                       re.IGNORECASE)


def egfr_ckd_epi_2021(scr_mg_dl, age, sex):
    """eGFR CKD-EPI 2021 (creatinina, sem fator de raça), mL/min/1,73 m²."""
    female = sex == "F"
    k = 0.7 if female else 0.9
    a = -0.241 if female else -0.302
    r = scr_mg_dl / k
    v = 142 * (min(r, 1) ** a) * (max(r, 1) ** -1.200) * (0.9938 ** age)
    if female:
        v *= 1.012
    return round(v, 1)


def ckd_stage(egfr):
    if egfr >= 90:
        return "G1"
    if egfr >= 60:
        return "G2"
    if egfr >= 45:
        return "G3a"
    if egfr >= 30:
        return "G3b"
    if egfr >= 15:
        return "G4"
    return "G5"


def cockcroft_gault(scr_mg_dl, age, sex, weight_kg):
    """Clearance de creatinina estimado (mL/min) — usado p/ ajuste de dose."""
    v = (140 - age) * weight_kg / (72 * scr_mg_dl)
    if sex == "F":
        v *= 0.85
    return round(v, 1)


def _extract_renal_inputs(text):
    """Extrai creatinina/idade/sexo/peso da pergunta (LLM só EXTRAI, não calcula)."""
    try:
        out = llm.chat([
            {"role": "system", "content":
             "Extraia da pergunta os dados para calcular função renal. Responda APENAS um "
             "JSON válido, sem texto extra: {\"scr\": creatinina em mg/dL ou null, "
             "\"age\": idade em anos ou null, \"sex\": \"M\" ou \"F\" ou null, "
             "\"weight\": peso em kg ou null}. Se a creatinina vier em µmol/L, divida por 88,4. "
             "Aceite vírgula decimal."},
            {"role": "user", "content": text[:1500]}],
            temperature=0, max_tokens=60, model=config.OPENAI_FAST_MODEL, json_mode=True)
        m = re.search(r"\{.*\}", out, re.DOTALL)
        return json.loads(m.group(0)) if m else {}
    except Exception:
        return {}


def renal_note(text):
    """Se a pergunta pede função renal, devolve um bloco de texto com os valores
    calculados (ou com os dados faltantes). Senão, None."""
    if not _RENAL_RE.search(text or ""):
        return None
    d = _extract_renal_inputs(text)
    try:
        scr = float(d["scr"]) if d.get("scr") is not None else None
        age = float(d["age"]) if d.get("age") is not None else None
        weight = float(d["weight"]) if d.get("weight") is not None else None
    except (TypeError, ValueError):
        scr = age = weight = None
    sex = d.get("sex") if d.get("sex") in ("M", "F") else None

    missing = [n for n, v in (("creatinina sérica", scr), ("idade", age), ("sexo", sex)) if v is None]
    if missing:
        return ("CÁLCULO DETERMINÍSTICO: dados insuficientes para calcular a função renal — "
                "falta: " + ", ".join(missing) + ". Peça esses dados ao médico; não estime valores.")
    if not (0.1 <= scr <= 25 and 1 <= age <= 120):
        return "CÁLCULO DETERMINÍSTICO: valores fora da faixa plausível; confirme os dados com o médico."

    egfr = egfr_ckd_epi_2021(scr, age, sex)
    lines = [
        "CÁLCULO DETERMINÍSTICO (feito pelo sistema — use EXATAMENTE estes valores, não recalcule):",
        f"- Dados: creatinina {scr:g} mg/dL, idade {age:g} anos, sexo {'feminino' if sex == 'F' else 'masculino'}"
        + (f", peso {weight:g} kg" if weight else ""),
        f"- eGFR CKD-EPI 2021 = {str(egfr).replace('.', ',')} mL/min/1,73 m² → estágio {ckd_stage(egfr)} (KDIGO)",
        "- A equação CKD-EPI 2021 NÃO usa raça/etnia (usa só creatinina, idade e sexo).",
    ]
    if weight and 20 <= weight <= 300:
        cg = cockcroft_gault(scr, age, sex, weight)
        lines.append(f"- Clearance de creatinina (Cockcroft-Gault) = {str(cg).replace('.', ',')} mL/min "
                     "(útil para ajuste de dose de fármacos)")
    lines.append("Explique a fórmula em texto simples (sem LaTeX) e as implicações clínicas.")
    return "\n".join(lines)
