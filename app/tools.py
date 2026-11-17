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


# ===== classificações que o modelo errava (IMC 29 chamado de obesidade, TFG 78 chamada de DRC): o código classifica =====
_NUM = r"(\d+(?:[.,]\d+)?)"
_PESO_RE = re.compile(r"\bpeso(?: atual)?\s*(?:de\s*)?[:=]?\s*" + _NUM + r"\s*kg\b", re.I)
_ALTURA_RE = re.compile(r"\baltura\s*(?:de\s*)?[:=]?\s*" + _NUM + r"\s*(m|cm)\b", re.I)
_TFG_RE = re.compile(r"\b(?:tfg|e?gfr|taxa de filtra[cç][aã]o glomerular)(?:\s*estimada)?\s*(?:de\s*)?[:=]?\s*" + _NUM
                     + r"\s*ml", re.I)
_RAC_RE = re.compile(r"(?:\brac\b|albumina/creatinina|albumin[uú]ria)[^0-9]{0,30}?" + _NUM + r"\s*mg/g", re.I)


_K_RE = re.compile(r"\bpot[áa]ssio(?: s[ée]rico)?\s*(?:de\s*)?[:=]?\s*" + _NUM + r"\s*(?:mEq|mmol)", re.I)
_VARFARINA_RE = re.compile(r"\bvarfarina\b|\bwarfarin", re.I)


_ESTATINA_RE = re.compile(r"\b(atorvastatina|rosuvastatina|sinvastatina|pravastatina|lovastatina|fluvastatina|"
                          r"pitavastatina)\s*(\d+(?:[.,]\d+)?)\s*mg", re.I)
_LDL_RE = re.compile(r"\bLDL(?:-?c)?\s*(?:de\s*)?[:=]?\s*(\d+(?:[.,]\d+)?)\s*mg", re.I)
_SULFONIL_RE = re.compile(r"\b(gliclazida|glibenclamida|glimepirida|glipizida)\b", re.I)
_IECA_BRA_RE = re.compile(r"\b(enalapril|captopril|ramipril|lisinopril|perindopril|losartana|valsartana|candesartana|"
                          r"irbesartana|olmesartana|telmisartana|sacubitril)\b", re.I)
_BB_RE = re.compile(r"\b(carvedilol|bisoprolol|metoprolol|nebivolol)\b", re.I)
_CONGESTAO_RE = re.compile(r"acima do peso seco|congest|edema", re.I)
# intensidade das estatinas (SBC Dislipidemias 2025 / ACC-AHA): alta ≥50%, moderada 30–49%, baixa <30%
_REDUCAO = {"alta": (0.50, 0.60, "≥50%"), "moderada": (0.30, 0.49, "30–49%"), "baixa": (0.20, 0.29, "<30%")}
_ESTATINA_DOSES = {   # (dose mínima de alta, dose mínima de moderada) em mg; abaixo da moderada = baixa
    "atorvastatina": (40, 10), "rosuvastatina": (20, 5), "sinvastatina": (None, 20), "pravastatina": (None, 40),
    "lovastatina": (None, 40), "fluvastatina": (None, 80), "pitavastatina": (None, 2),
}


# a menção do remédio não é uso: "posso iniciar varfarina?", "alergia a captopril", "suspendeu a gliclazida"
_NAO_USO_ANTES = re.compile(r"(inici|introdu|come[çc]|associ|adicion|acrescent|prescrev|posso|devo|deveria|alergi|al[ée]rg|"
                            r"intoler|suspen|evit|contraindic|n[ãa]o usa|sem uso|parou|trocar? (?:para|por)|"
                            r"substitu|em vez de|ao inv[ée]s de|ou )[^.;\n]{0,30}$", re.I)
_NAO_USO_DEPOIS = re.compile(r"^[^.;\n]{0,25}\?")
_PRE_TRATAMENTO = re.compile(r"antes d[oa] (?:tratamento|estatina|remédio)|pr[ée]-?tratamento|basal|sem (?:tratamento|estatina)",
                             re.I)
_PESO_NAO = re.compile(r"(perda|ganho|varia[çc][ãa]o|redu[çc][ãa]o|perdeu|ganhou|aumento|meta) de\s*$", re.I)
_K_NAO = re.compile(r"(cloreto|citrato|reposi[çc][ãa]o|suplemento|xarope|KCl)[^.;\n]{0,15}$", re.I)


# ===== avisos de dose (16/11/2026): só remédio EM USO, a partir do perfil/pergunta; o modelo recebe o aviso pronto =====
_FREQ = ((re.compile(r"\b4\s*x|\b6/6\s*h|4 vezes", re.I), 4), (re.compile(r"\b3\s*x|\b8/8\s*h|3 vezes", re.I), 3),
         (re.compile(r"\b2\s*x|\b12/12\s*h|2 vezes|duas vezes", re.I), 2))
# dose diária máxima habitual (bula/diretriz): no máximo, não há como subir — intensificar é associar ou trocar
_DOSE_MAX = {"losartana": 100, "valsartana": 320, "candesartana": 32, "olmesartana": 40, "telmisartana": 80,
             "irbesartana": 300, "enalapril": 40, "ramipril": 10, "lisinopril": 40, "captopril": 150, "anlodipino": 10,
             "atorvastatina": 80, "rosuvastatina": 40, "sinvastatina": 40, "metformina": 2550, "bisoprolol": 10,
             "carvedilol": 50}
_SULFONAMIDAS = ("hidroclorotiazida", "clortalidona", "indapamida", "furosemida", "bumetanida", "glibenclamida",
                 "gliclazida", "glimepirida", "glipizida", "celecoxibe", "acetazolamida")
_ALERGIA_SULFA = re.compile(r"alergi[ao]s?[^.\n]{0,60}\b(sulfa|sulfonamida|sulfametoxazol|bactrim)", re.I)
_IDADE_RE = re.compile(r"\b(\d{2,3})\s*anos\b", re.I)
_ICFER_RE = re.compile(r"\bICFEr\b|\bIC ?FEr\b|insufici[êe]ncia card[ií]aca[^.;\n]{0,70}?(?:fra[cç][ãa]o de eje[cç][ãa]o reduzida|"
                       r"FE(?:VE)?\s*(?:reduzida|de\s*)?\s*(?:[1-3]\d|40)\s*%)", re.I)
_ATEROSCLEROSE_RE = re.compile(r"infarto|\bIAM\b|doen[çc]a arterial coronari|\bDAC\b|coronariopatia|angina|angioplastia|"
                               r"\bstent|revasculariza|ponte de safena|\bAVC\b|acidente vascular|\bAIT\b|doen[çc]a arterial "
                               r"perif[ée]rica|\bDAP\b|claudica[çc]|aterosclero|cardiopatia isqu[êe]mica|placa", re.I)
_GESTA_RE = re.compile(r"gesta[çc][ãa]o de (\d{1,2})\s*semanas|(\d{1,2})\s*semanas de gesta|\bIG\s*[:=]?\s*(\d{1,2})\s*s|"
                       r"gr[áa]vida de (\d{1,2})\s*semanas|\bgestante\b|\bgr[áa]vida\b|\bgesta[çc][ãa]o\b", re.I)
_GESTA_NAO = re.compile(r"(?:pr[ée]vi[ao]|anterior|passad[ao]|[úu]ltim[ao]|ap[óo]s a|depois da|p[óo]s)\s*$", re.I)
_ALERGIAS_RE = re.compile(r"\balergias?\s*:\s*([^.\n]{2,80})", re.I)
_PA_TEMA = re.compile(r"\bPA\b|press[ãa]o|hipertens|anti-?hipertens|pr[ée]-?ecl", re.I)
_VACINA_TEMA = re.compile(r"vacin|imuniza", re.I)
_LIPIDIO_TEMA = re.compile(r"statina|colesterol|ezetimib|\bLDL|lip[íi]d|dislipid", re.I)
_TSH_RE = re.compile(r"\bTSH\s*(?:de\s*)?[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:mUI|µUI|uUI|mU)", re.I)
_HB_RE = re.compile(r"\bhemoglobina\s*(?:de\s*)?[:=]?\s*(\d+(?:[.,]\d+)?)\s*g/dL|\bHb\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*g/dL", re.I)
_URO_POS_RE = re.compile(r"urocultura[^.;\n]{0,40}?(?:positiva|>\s*100\.?000|≥\s*10\^?5|10\^5|\bE\. ?coli\b|klebsiella|proteus)", re.I)
_HOMEM_RE = re.compile(r"\bhomem\b|sexo masculino|\bmasculino\b", re.I)
_ITU_RE = re.compile(r"infec[çc][ãa]o (?:do trato )?urin[áa]ria|\bITU\b|cistite", re.I)
_DIURETICO_RE = re.compile(r"\b(hidroclorotiazida|clortalidona|indapamida|furosemida|bumetanida|espironolactona)\b", re.I)


def _dose_em_uso(nome, t):
    """(mg por dose, doses por dia, mg/dia) do remédio em uso, ou None. Ex.: "metformina 850 mg 2x/dia" → (850, 2, 1700)."""
    rx = re.compile(r"\b(" + nome + r")\b[^;\n]{0,20}?(\d+(?:[.,]\d+)?)\s*mg\b([^;\n]{0,25})", re.I)
    m = _primeira_em_uso(rx, t)
    if not m:
        return None
    mg, resto = _f(m.group(2)), m.group(3)
    vezes = next((n for r, n in _FREQ if r.search(resto)), 1)
    return mg, vezes, mg * vezes


def _avisos_dose(t, tfg, k):
    """Linhas dos avisos de dose (sem nada a dizer, lista vazia). tfg e k: números já lidos (ou None)."""
    out = []
    idade = _IDADE_RE.search(t)
    idade = int(idade.group(1)) if idade and 18 <= int(idade.group(1)) <= 110 else None
    met = _dose_em_uso("metformina", t)
    if met and tfg is not None:
        dia = _br(met[2], 0)
        if tfg < 30:
            out.append(f"- ALERTA: Metformina {dia} mg/dia com TFG {_br(tfg, 0)} (<30): CONTRAINDICADA → suspender (KDIGO 2022)")
        elif tfg < 45:
            acima = met[2] > 1000
            out.append(f"- {'ALERTA: ' if acima else ''}Metformina {dia} mg/dia com TFG {_br(tfg, 0)} (30–44): dose máxima 1.000 mg/dia e não iniciar "
                       f"nessa faixa (KDIGO 2022)" + (f" → a dose atual está ACIMA: reduzir para ≤1.000 mg/dia" if acima else ""))
        elif tfg < 60:
            out.append(f"- Metformina com TFG {_br(tfg, 0)} (45–59): manter a dose e reavaliar a TFG a cada 3–6 meses (KDIGO 2022)")
    if _primeira_em_uso(re.compile(r"\bglibenclamida\b", re.I), t) and ((tfg is not None and tfg < 60) or (idade and idade >= 65)):
        out.append("- ALERTA: Glibenclamida com " + ("TFG <60" if tfg is not None and tfg < 60 else f"{idade} anos") + ": evitar (hipoglicemia "
                   "prolongada; Beers/SBD) → trocar por gliclazida ou por remédio sem hipoglicemia")
    if _primeira_em_uso(re.compile(r"\bespironolactona\b", re.I), t):
        if k is not None and k > 5.5:
            out.append(f"- ALERTA: Espironolactona com K {_br(k)} (>5,5): reduzir à metade ou suspender e repetir o K em poucos dias")
        elif k is not None and k > 5.0:
            out.append(f"- Espironolactona com K {_br(k)} (>5,0): não aumentar a dose; repetir K e creatinina em 1–2 semanas")
        if tfg is not None and tfg < 30:
            out.append(f"- ALERTA: Espironolactona com TFG {_br(tfg, 0)} (<30): evitar (risco de hipercalemia grave)")
    if _primeira_em_uso(_IECA_BRA_RE, t) and _primeira_em_uso(_DIURETICO_RE, t):
        out.append("- Em uso de IECA/BRA + diurético: AINE (ibuprofeno, naproxeno, diclofenaco, cetoprofeno, celecoxibe) fecha a "
                   "\"tríade\" de lesão renal aguda → evitar; se inevitável, o menor tempo e creatinina/K em poucos dias")
    if tfg is not None and tfg < 30:
        out.append(f"- TFG {_br(tfg, 0)} (<30): AINE sistêmico contraindicado")
    if tfg is not None and tfg < 60 and _LIPIDIO_TEMA.search(t):
        out.append(f"- Estatina com TFG {_br(tfg, 0)}: rosuvastatina no máximo 20 mg/dia com ClCr <60 (40 mg contraindicado em "
                   "bula)" + ("; com ClCr <30 a bula brasileira contraindica (fora dela, no máximo 10 mg/dia)" if tfg < 30 else "") +
                   "; atorvastatina não precisa de ajuste renal")
    # DRC e estatina (KDIGO Lipídios 2013, 1A): ≥50 anos com TFG <60 sem diálise → estatina indicada, qualquer LDL
    if tfg is not None and tfg < 60 and idade and idade >= 50:
        if re.search(r"di[áa]lise", t, re.I):
            out.append("- Em diálise: não INICIAR estatina (KDIGO Lipídios); se já usava ao entrar em diálise, pode manter")
        else:
            out.append(f"- {idade} anos com TFG {_br(tfg, 0)} (<60, sem diálise): estatina (ou estatina + ezetimiba) INDICADA pela "
                       "DRC, independentemente do LDL (KDIGO Lipídios 2013) — o lipidograma serve de base e para a adesão, não "
                       "para decidir se trata")
    # gestação (16/11/2026): o que muda em remédio, meta e vacina; o ALERTA entra em toda resposta, o resto só no assunto
    g = next((m for m in _GESTA_RE.finditer(t) if not _GESTA_NAO.search(t[max(0, m.start() - 20):m.start()])
              and not re.match(r"\s*(?:pr[ée]vias?|anteriore?s?|passadas?|em \d{4}|h[áa] \d)", t[m.end():m.end() + 20], re.I)), None)
    if g:
        sem = next((int(x) for x in g.groups() if x), None)
        sem = sem if sem and 4 <= sem <= 42 else None
        ig = f"de {sem} semanas" if sem else "(idade gestacional não informada)"
        tema = t.split("\nPaciente:")[0]          # o assunto é o da pergunta (o perfil escolhido vem depois, com "Paciente:")
        out.append(f"- ALERTA: Gestante {ig}: remédio, dose, meta e vacina são os da gestação. Contraindicados: estatina, "
                   "IECA/BRA/aliscireno, varfarina, tetraciclinas, misoprostol, isotretinoína; evitar AINE a partir de 20 "
                   "semanas (oligoidrâmnio; canal arterial no 3º trimestre), quinolonas, e SMX-TMP no 1º trimestre e no fim")
        # o que o perfil da gestante já mostra fora da meta: entra em toda resposta (os revisores viram que ficava de fora)
        tsh = _TSH_RE.search(t)
        if tsh and re.search(r"levotiroxina|hipotireoid", t, re.I):
            v = _f(tsh.group(1))
            if 2.5 < v <= 100:
                out.append(f"- ALERTA: Gestante em tratamento de hipotireoidismo com TSH {_br(v)} (>2,5, acima do alvo da gestação): "
                           "aumentar a levotiroxina (ex.: +25–50 mcg/dia) e repetir o TSH em 4 semanas (ATA 2017); tomar longe do "
                           "ferro e do cálcio (4 h)")
        hb = _HB_RE.search(t)
        if hb:
            v = _f(hb.group(1) or hb.group(2))
            limite = 10.5 if sem and 14 <= sem <= 27 else 11.0
            if 4 <= v < limite:
                out.append(f"- ALERTA: Anemia na gestação: Hb {_br(v)} g/dL (<{_br(limite)} " +
                           ("no 2º trimestre" if limite == 10.5 else "no 1º/3º trimestre") + "): ferritina e adesão; ferro "
                           "elementar de tratamento 60–120 mg/dia (a dose de profilaxia não basta); sem resposta ou ferritina muito "
                           "baixa no 2º/3º trimestre, ferro endovenoso")
        if _URO_POS_RE.search(t):
            out.append("- ALERTA: Urocultura positiva na gestação (bacteriúria, mesmo sem sintomas): TRATAR já, guiado pelo "
                       "antibiograma (fosfomicina 3 g dose única, cefalexina ou nitrofurantoína 5–7 dias), e urocultura de "
                       "controle 1–2 semanas depois e periódica até o parto")
        if _PA_TEMA.search(tema):
            out.append("- PA na gestação: ≥140/90 = hipertensão (nova, a partir de 20 semanas: investigar pré-eclâmpsia — "
                       "proteinúria/relação proteína-creatinina, plaquetas, creatinina, TGO/TGP e sintomas); ≥160/110 = GRAVE → "
                       "tratar em até 30–60 min (nifedipino, hidralazina ou labetalol) e avaliar internação. Tratar a partir de "
                       "140/90 com alvo <140/90 e PAD em torno de 85 (CHAP, CHIPS); remédios: metildopa, nifedipino, labetalol. "
                       "160/110 é o limite do grave, NUNCA a meta")
        if _VACINA_TEMA.search(tema):
            out.append("- Vacinas na gestação (PNI/MS, Febrasgo): dTpa a partir de 20 semanas em toda gestação (pode já fazer "
                       "nesse marco); VSR (vírus sincicial respiratório, protege o bebê contra bronquiolite): dose única a partir de 28 "
                       "semanas, no SUS desde dez/2025 (PNI/MS; Abrysvo) — não é só no particular nem só de 32 a 36 semanas; "
                       "influenza em qualquer fase; covid-19; hepatite B se não vacinada; vacinas de vírus vivo "
                       "(tríplice viral, varicela; febre amarela salvo risco alto) contraindicadas")
        if _LIPIDIO_TEMA.search(tema):
            out.append("- Lipídios na gestação: o LDL sobe 25–50% no 2º–3º trimestres (fisiológico) → não interpretar nem tratar "
                       "agora; estatina contraindicada (também na amamentação); reavaliar o perfil lipídico depois do parto e da "
                       "amamentação")
        if _ITU_RE.search(tema) or re.search(r"urocultura|bacteri[úu]ria", tema, re.I):
            out.append("- Bacteriúria/ITU na gestação: tratar SEMPRE, inclusive a assintomática (fosfomicina 3 g dose única, "
                       "cefalexina 5–7 dias ou nitrofurantoína 5–7 dias, esta evitada a partir de 38 semanas); urocultura de "
                       "controle 1–2 semanas depois; evitar quinolonas e SMX-TMP no 1º trimestre e no fim")
    al = _ALERGIAS_RE.search(t)
    if al and not re.match(r"\s*(nenhum|nega|sem\b|n[ãa]o)", al.group(1), re.I):
        out.append(f"- Alergia registrada: {al.group(1).strip()} → não prescrever nem sugerir como alternativa (nem da mesma "
                   "classe, se houver risco cruzado)")
    # dados que valem quando o assunto é aquele (não são ALERTA: não entram em toda resposta)
    if _primeira_em_uso(_VARFARINA_RE, t):
        out.append("- Em uso de varfarina: AINE contraindicado (sangramento); paracetamol regular >2 g/dia por vários dias sobe o "
                   "INR → prefira ≤2 g/dia e, se usar por mais de alguns dias, INR em 3–5 dias; antibióticos (sobretudo "
                   "SMX-TMP, metronidazol, fluconazol, quinolonas, macrolídeos) também sobem o INR → INR em 3–5 dias")
    if _ICFER_RE.search(t):
        out.append("- IC com FE reduzida: evitar AINE, corticoide sistêmico (retenção de sódio e água; se inevitável, o menor "
                   "tempo e vigiar peso/congestão), glitazona e diltiazem/verapamil (pioram a IC) — ESC/SBC IC")
        if not _ATEROSCLEROSE_RE.search(t):
            out.append("- IC com FE reduzida sem doença aterosclerótica no cadastro: estatina não reduz desfechos na IC (CORONA, "
                       "GISSI-HF) → a IC sozinha não indica estatina; a indicação vem de outra condição (DRC — veja a linha da "
                       "KDIGO, se houver —, diabetes, risco aterosclerótico), com lipidograma antes; se já usa, pode manter")
    if _HOMEM_RE.search(t) and _ITU_RE.search(t):
        out.append("- ITU em homem é sempre complicada: tratar por 7 dias (não os esquemas de 3–5 dias da cistite da mulher; "
                   "fosfomicina em dose única não serve); urocultura antes; pensar em prostatite se houver febre ou sintomas "
                   "prostáticos (aí 2–4 semanas de quinolona/SMX-TMP conforme a cultura)")
    if _ALERGIA_SULFA.search(t):
        em_uso = [n for n in _SULFONAMIDAS if _primeira_em_uso(re.compile(r"\b" + n + r"\b", re.I), t)]
        txt = "- ALERTA: Alergia a sulfa registrada: sulfametoxazol-trimetoprima (sulfonamida antibiótica) CONTRAINDICADO"
        if em_uso:
            txt += ("; em uso de " + ", ".join(em_uso) + " (sulfonamida NÃO antibiótica): reação cruzada é rara — se já usa "
                    "sem reação, pode manter (confirme e registre a tolerância); ao trocar, prefira opção sem sulfonamida")
        out.append(txt)
    for nome, teto in _DOSE_MAX.items():
        d = _dose_em_uso(nome, t)
        if d and d[2] >= teto:
            out.append(f"- ALERTA: {nome.capitalize()} {_br(d[2], 0)} mg/dia = dose máxima habitual ({_br(teto, 0)} mg/dia): não há como "
                       "subir → para intensificar, associe outro remédio ou troque")
    return out


def _primeira_em_uso(rx, t):
    """1ª menção de rx que parece USO (não pergunta sobre iniciar, alergia, suspensão, troca, alternativa)."""
    for m in rx.finditer(t):
        antes, depois = t[max(0, m.start() - 45):m.start()], t[m.end():m.end() + 30]
        if _NAO_USO_ANTES.search(antes) or _NAO_USO_DEPOIS.search(depois):
            continue
        return m
    return None


def _primeira_sem(rx, t, nao):
    for m in rx.finditer(t):
        if not nao.search(t[max(0, m.start() - 25):m.start()]):
            return m
    return None


def estatina_intensidade(nome, mg):
    alta, mod = _ESTATINA_DOSES.get(nome.lower(), (None, None))
    if mod is None:
        return None
    if alta is not None and mg >= alta:
        return "alta"
    return "moderada" if mg >= mod else "baixa"


def _f(x):
    return float(x.replace(",", "."))


def _br(x, casas=1):
    return f"{x:.{casas}f}".replace(".", ",")


def imc_classe(imc):
    """Classificação do IMC em adultos (OMS / ABESO)."""
    if imc < 18.5:
        return "baixo peso"
    if imc < 25:
        return "eutrofia"
    if imc < 30:
        return "sobrepeso (pré-obesidade)"
    if imc < 35:
        return "obesidade grau I"
    if imc < 40:
        return "obesidade grau II"
    return "obesidade grau III"


def albuminuria_stage(rac_mg_g):
    if rac_mg_g < 30:
        return "A1"
    if rac_mg_g <= 300:
        return "A2"
    return "A3"


def clinical_facts(text):
    """IMC e classe (se houver peso e altura) e categoria G/A da KDIGO (se houver TFG e/ou RAC) da pergunta; None se
    não houver nada. Só regex: nada sai do servidor."""
    t = text or ""
    lines = []
    peso, alt = _primeira_sem(_PESO_RE, t, _PESO_NAO), _ALTURA_RE.search(t)
    if peso and alt:
        try:
            kg, h = _f(peso.group(1)), _f(alt.group(1))
            h = h / 100 if alt.group(2).lower() == "cm" else h
            if 20 <= kg <= 350 and 1.0 <= h <= 2.3:
                imc = kg / (h * h)
                lines.append(f"- IMC = {_br(kg)} kg / ({_br(h, 2)} m)² = {_br(imc)} kg/m² → {imc_classe(imc)}")
        except ValueError:
            pass
    tfg, rac = _TFG_RE.search(t), _RAC_RE.search(t)
    g = a = None
    if tfg:
        try:
            v = _f(tfg.group(1))
            if 1 <= v <= 200:
                g = ckd_stage(v)
                lines.append(f"- TFG informada {_br(v, 0)} mL/min/1,73 m² → categoria {g} (KDIGO)")
        except ValueError:
            pass
    if rac:
        try:
            v = _f(rac.group(1))
            if 0 <= v <= 20000:
                a = albuminuria_stage(v)
                lines.append(f"- Relação albumina/creatinina {_br(v, 0)} mg/g → categoria {a} (KDIGO)")
        except ValueError:
            pass
    if g and a:
        dr = g in ("G3a", "G3b", "G4", "G5") or a in ("A2", "A3")
        lines.append(f"- Categoria KDIGO {g}/{a}" + (" → doença renal crônica (se persistir por mais de 3 meses)" if dr
                                                     else " → sem critério de doença renal crônica por esses dois valores"))
    elif g in ("G1", "G2") and not a:
        lines.append(f"- {g} sozinho não define doença renal crônica: precisa de marcador de lesão (ex.: albuminúria)")
    # regras que o modelo (raciocínio baixo) às vezes não aplicava sozinho: vão como dado do caso
    k = _primeira_sem(_K_RE, t, _K_NAO)
    if k:
        try:
            v = _f(k.group(1))
            if 1.5 <= v <= 9 and v >= 5.0:
                lines.append(f"- Potássio {_br(v)} mEq/L (≥5,0) → risco alto de hipercalemia: creatinina e potássio em 1–2 "
                             "semanas (não 2–4) após qualquer início/ajuste de IECA/BRA, sacubitril/valsartana ou "
                             "antagonista mineralocorticoide; com K >5,0, não subir esses remédios antes de reduzir o K")
        except ValueError:
            pass
    est = _primeira_em_uso(_ESTATINA_RE, t)
    if est:
        nome, mg = est.group(1).lower(), _f(est.group(2))
        inten = estatina_intensidade(nome, mg)
        if inten:
            faixa = _REDUCAO[inten]
            txt = f"- {nome.capitalize()} {_br(mg, 0)} mg = estatina de intensidade {inten} (redução esperada do LDL {faixa[2]})"
            ldl = _LDL_RE.search(t)
            if ldl and _PRE_TRATAMENTO.search(t[max(0, ldl.start() - 40):ldl.end() + 40]):
                ldl = None       # o LDL informado é o de antes do remédio: não há o que estimar
            if ldl:
                v = _f(ldl.group(1))
                if 20 <= v <= 600:
                    lo, hi = v / (1 - faixa[0]), v / (1 - faixa[1])
                    txt += (f". SE o LDL-c {_br(v, 0)} foi medido já em uso dela, com boa adesão (confirme as duas coisas e "
                            f"peça o valor de antes do tratamento), o LDL antes do tratamento estaria em ~{_br(lo, 0)}–"
                            f"{_br(hi, 0)} mg/dL")
                    if lo >= 190:
                        txt += " → nesse caso, provável LDL basal ≥190: risco ALTO (meta <70, redução ≥50%) e suspeita de hipercolesterolemia familiar"
                    elif hi >= 190:
                        txt += " → nesse caso, o LDL basal pode ter sido ≥190 (risco alto e suspeita de hipercolesterolemia familiar)"
            lines.append(txt)
            if inten != "alta":
                lines.append("- Se o risco for alto, muito alto ou extremo (ou LDL basal ≥190/HF): trocar JÁ por estatina de alta "
                             "intensidade (atorvastatina 40–80 mg ou rosuvastatina 20–40 mg) + ezetimiba 10 mg desde o início — não "
                             "esperar novo LDL nem a falha da estatina isolada (SBC Dislipidemias 2025)")
    if _primeira_em_uso(_IECA_BRA_RE, t):
        lines.append("- Em uso de IECA/BRA/sacubitril-valsartana: se associar espironolactona ou eplerenona, o risco de "
                     "hipercalemia é alto → creatinina e potássio em 1–2 semanas (não 2–4), depois a cada 3–6 meses")
    if _primeira_em_uso(_SULFONIL_RE, t):
        lines.append("- Em uso de sulfonilureia: ao iniciar insulina, reduza a dose dela (ex.: à metade) ou suspenda — não espere "
                     "hipoglicemia; ao associar GLP-1 ou iSGLT2 com HbA1c perto da meta, também reduza; oriente hipoglicemia")
    if _primeira_em_uso(_BB_RE, t) and _CONGESTAO_RE.search(t):
        lines.append("- Betabloqueador com congestão (acima do peso seco/edema): não suba a dose do betabloqueador até voltar ao "
                     "peso seco; primeiro ajuste o diurético e reavalie em 1–2 semanas")
    if _primeira_em_uso(_VARFARINA_RE, t):
        lines.append("- Em uso de varfarina: na troca por DOAC, suspender a varfarina e iniciar o DOAC só com INR <2,0 "
                     "(apixabana, dabigatrana), ≤2,5 (edoxabana) ou ≤3,0 (rivaroxabana) — diga o número, nunca sobreponha")
    try:
        v_tfg = _f(tfg.group(1)) if tfg else None
        v_tfg = v_tfg if v_tfg is not None and 1 <= v_tfg <= 200 else None
        v_k = _f(k.group(1)) if k else None
        v_k = v_k if v_k is not None and 1.5 <= v_k <= 9 else None
        lines += _avisos_dose(t, v_tfg, v_k)
    except ValueError:
        pass
    if not lines:
        return None
    return ("DADOS CALCULADOS (use exatamente estas classificações; não as altere):\n" + "\n".join(lines))


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
