"""Cliente PubMed via E-utilities (gratuito). Busca PMIDs e baixa metadados+abstract."""
import time
import hashlib
import xml.etree.ElementTree as ET

import httpx

from . import config

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _params(extra):
    p = dict(extra)
    if config.NCBI_API_KEY:
        p["api_key"] = config.NCBI_API_KEY
    if config.NCBI_EMAIL:
        p["email"] = config.NCBI_EMAIL
        p["tool"] = "opendoctor"
    return p


def search(query, retmax=20, sort="relevance", mindate=None):
    """Retorna lista de PMIDs para a query.
    sort='relevance' = Best Match do PubMed. O padrão do E-utilities é por DATA
    (mais recentes), o que trazia artigos tangenciais em vez dos mais relevantes
    (ex.: a diretriz AHA/ACC de IC só aparece ordenando por relevância).
    mindate: ano mínimo de publicação (ex.: 2015)."""
    p = {"db": "pubmed", "term": query, "retmax": retmax, "retmode": "json"}
    if sort:
        p["sort"] = sort
    if mindate:
        p.update({"datetype": "pdat", "mindate": str(mindate), "maxdate": "3000"})
    r = httpx.get(f"{EUTILS}/esearch.fcgi", params=_params(p), timeout=30)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])


def _text(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def fetch(pmids):
    """Baixa os artigos (XML) e devolve dicts estruturados."""
    if not pmids:
        return []
    r = httpx.get(
        f"{EUTILS}/efetch.fcgi",
        params=_params({"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}),
        timeout=60,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    out = []
    for art in root.findall(".//PubmedArticle"):
        pmid = _text(art.find(".//PMID"))
        title = _text(art.find(".//ArticleTitle"))
        journal = _text(art.find(".//Journal/Title"))
        year = _text(art.find(".//JournalIssue/PubDate/Year")) or _text(art.find(".//PubDate/Year"))

        # abstract: pode ter seções rotuladas (BACKGROUND, METHODS, ...)
        sections = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label")
            txt = _text(ab)
            if txt:
                sections.append((label, txt))
        abstract = "\n\n".join(
            (f"{lbl}: {txt}" if lbl else txt) for lbl, txt in sections
        )

        # DOI
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _text(aid)
                break

        if not abstract:
            continue  # sem abstract não há conteúdo recuperável nesta fase

        # tipos de publicação (fonte oficial do PubMed p/ o nível de evidência)
        pub_types = [_text(pt) for pt in art.findall(".//PublicationTypeList/PublicationType")]
        if any(pt.lower() in ("retracted publication", "retraction of publication")
               for pt in pub_types):
            continue  # nunca usar artigo retratado

        url = f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        body = (title + "\n\n" + abstract).strip()
        out.append({
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "year": int(year) if year.isdigit() else None,
            "doi": doi,
            "url": url,
            "sections": sections,           # [(label|None, text)]
            "abstract": abstract,
            "pub_types": pub_types,         # ex.: ["Meta-Analysis", "Review"]
            "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        })
    time.sleep(0.34)  # respeitar rate limit do E-utilities
    return out
