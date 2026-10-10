"""Temas clínicos de alta relevância por especialidade — base do corpus curado.

Cada tema vira uma busca no PubMed (ordenada por relevância, últimos ~10 anos,
só diretrizes / metanálises / revisões sistemáticas; revisões como reforço).
Para ampliar a cobertura, acrescente temas aqui e rode:
    python -m app.bulk_ingest
"""

TOPICS = {
    "cardiologia": [
        "heart failure", "atrial fibrillation", "acute coronary syndrome",
        "chronic coronary syndrome", "hypertension", "dyslipidemia statin",
        "aortic stenosis", "infective endocarditis", "pulmonary embolism",
        "deep vein thrombosis", "peripheral artery disease", "syncope",
        "ventricular arrhythmia", "acute pericarditis", "cardiogenic shock",
        "hypertrophic cardiomyopathy",
    ],
    "endocrinologia": [
        "type 2 diabetes", "type 1 diabetes", "diabetic ketoacidosis",
        "hypothyroidism", "hyperthyroidism Graves", "thyroid nodule",
        "osteoporosis", "adrenal insufficiency", "Cushing syndrome",
        "primary aldosteronism", "hyponatremia", "hypercalcemia",
        "obesity pharmacotherapy", "polycystic ovary syndrome", "hypoglycemia",
    ],
    "nefrologia": [
        "chronic kidney disease", "acute kidney injury", "hyperkalemia",
        "nephrotic syndrome", "IgA nephropathy", "kidney stones",
        "dialysis initiation", "metabolic acidosis", "polycystic kidney disease",
        "lupus nephritis", "contrast-induced nephropathy",
    ],
    "pneumologia": [
        "asthma", "COPD", "community-acquired pneumonia",
        "hospital-acquired pneumonia", "idiopathic pulmonary fibrosis",
        "obstructive sleep apnea", "pulmonary hypertension", "bronchiectasis",
        "pleural effusion", "lung cancer screening", "sarcoidosis",
        "chronic cough",
    ],
    "infectologia": [
        "sepsis", "urinary tract infection", "cellulitis", "HIV antiretroviral therapy",
        "HIV pre-exposure prophylaxis", "tuberculosis", "latent tuberculosis",
        "hepatitis B", "hepatitis C", "COVID-19 treatment", "influenza antiviral",
        "Clostridioides difficile infection", "bacterial meningitis", "osteomyelitis",
        "dengue", "malaria", "syphilis", "candidemia", "febrile neutropenia",
        "Staphylococcus aureus bacteremia", "diabetic foot infection",
    ],
    "gastroenterologia_hepatologia": [
        "gastroesophageal reflux disease", "Helicobacter pylori eradication",
        "upper gastrointestinal bleeding", "Crohn disease", "ulcerative colitis",
        "irritable bowel syndrome", "cirrhosis", "hepatic encephalopathy",
        "acute pancreatitis", "metabolic dysfunction-associated steatotic liver disease",
        "celiac disease", "colorectal cancer screening", "acute cholecystitis",
        "Wilson disease", "autoimmune hepatitis", "ascites spontaneous bacterial peritonitis",
        "chronic constipation",
    ],
    "neurologia": [
        "acute ischemic stroke", "intracerebral hemorrhage", "epilepsy",
        "status epilepticus", "migraine", "Parkinson disease", "Alzheimer disease",
        "multiple sclerosis", "myasthenia gravis", "Guillain-Barre syndrome",
        "peripheral neuropathy", "subarachnoid hemorrhage",
        "transient ischemic attack", "secondary stroke prevention", "headache tension-type",
    ],
    "psiquiatria": [
        "major depressive disorder", "generalized anxiety disorder", "bipolar disorder",
        "schizophrenia", "attention deficit hyperactivity disorder adults",
        "alcohol use disorder", "opioid use disorder", "insomnia",
        "post-traumatic stress disorder", "delirium", "anorexia nervosa",
        "suicide prevention", "panic disorder",
    ],
    "hematologia": [
        "iron deficiency anemia", "venous thromboembolism anticoagulation",
        "sickle cell disease", "immune thrombocytopenia",
        "heparin-induced thrombocytopenia", "multiple myeloma", "diffuse large B-cell lymphoma",
        "acute myeloid leukemia", "myelodysplastic syndromes",
        "red blood cell transfusion threshold", "hemophilia", "vitamin B12 deficiency",
        "thrombotic thrombocytopenic purpura",
    ],
    "oncologia": [
        "breast cancer", "prostate cancer", "colorectal cancer treatment",
        "non-small cell lung cancer", "cancer pain", "chemotherapy-induced nausea vomiting",
        "tumor lysis syndrome", "immune checkpoint inhibitor adverse events",
        "cancer-associated thrombosis", "melanoma", "pancreatic cancer",
        "hepatocellular carcinoma", "cervical cancer",
    ],
    "reumatologia": [
        "rheumatoid arthritis", "gout", "systemic lupus erythematosus", "osteoarthritis",
        "giant cell arteritis", "polymyalgia rheumatica", "axial spondyloarthritis",
        "psoriatic arthritis", "ANCA-associated vasculitis", "fibromyalgia",
        "systemic sclerosis", "Sjogren syndrome",
    ],
    "emergencia_terapia_intensiva": [
        "cardiac arrest", "anaphylaxis", "acute respiratory distress syndrome",
        "septic shock vasopressors", "traumatic brain injury", "hemorrhagic shock",
        "mechanical ventilation", "sedation intensive care unit", "acute asthma exacerbation",
        "acetaminophen poisoning", "opioid overdose naloxone", "heat stroke",
        "burns management", "fluid resuscitation", "acute agitation emergency",
        "stress ulcer prophylaxis",
    ],
    "pediatria": [
        "acute otitis media", "bronchiolitis", "febrile infant", "neonatal jaundice",
        "pediatric acute gastroenteritis dehydration", "pediatric asthma", "croup",
        "Kawasaki disease", "childhood obesity", "pediatric urinary tract infection",
        "febrile seizures", "pediatric sepsis", "attention deficit hyperactivity disorder children",
        "streptococcal pharyngitis children", "pediatric pain management",
    ],
    "ginecologia_obstetricia": [
        "preeclampsia", "postpartum hemorrhage", "gestational diabetes", "preterm labor",
        "hyperemesis gravidarum", "ectopic pregnancy", "endometriosis",
        "menopause hormone therapy", "contraception", "abnormal uterine bleeding",
        "cervical cancer screening", "recurrent pregnancy loss", "induction of labor",
        "hypertension in pregnancy", "anemia in pregnancy",
    ],
    "dermatologia": [
        "atopic dermatitis", "psoriasis", "acne vulgaris", "chronic urticaria",
        "herpes zoster", "hidradenitis suppurativa", "onychomycosis", "scabies",
        "rosacea", "pressure injury", "seborrheic dermatitis",
    ],
    "urologia": [
        "benign prostatic hyperplasia", "erectile dysfunction", "urinary incontinence women",
        "overactive bladder", "recurrent urinary tract infection women",
        "chronic prostatitis",
    ],
    "oftalmologia_otorrino": [
        "glaucoma", "age-related macular degeneration", "diabetic retinopathy",
        "acute bacterial rhinosinusitis", "sudden sensorineural hearing loss",
        "benign paroxysmal positional vertigo", "allergic rhinitis", "conjunctivitis",
    ],
    "geriatria_atencao_primaria": [
        "falls prevention older adults", "frailty", "deprescribing polypharmacy",
        "behavioral and psychological symptoms of dementia", "low back pain",
        "neck pain", "smoking cessation", "adult vaccination",
        "aspirin primary prevention", "chronic pain opioid prescribing",
        "vitamin D supplementation", "sarcopenia",
    ],
    "ortopedia": [
        "hip fracture", "rotator cuff tear", "ankle sprain", "carpal tunnel syndrome",
        "knee osteoarthritis", "fragility fracture",
    ],
    "perioperatorio_anestesia": [
        "perioperative anticoagulation management", "postoperative nausea vomiting",
        "preoperative cardiovascular evaluation noncardiac surgery",
        "multimodal postoperative analgesia", "venous thromboembolism prophylaxis hospitalized",
        "perioperative glucose management",
    ],
    "nutricao": [
        "enteral nutrition critically ill", "malnutrition hospitalized adults",
        "refeeding syndrome",
    ],
    "alergia_imunologia": [
        "food allergy", "penicillin allergy", "hereditary angioedema",
    ],
}


def all_topics():
    """Lista única (especialidade, tema), sem repetir temas."""
    seen, out = set(), []
    for spec, items in TOPICS.items():
        for t in items:
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append((spec, t))
    return out
