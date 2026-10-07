"""Chunking por seção/parágrafo, sem cortar recomendação no meio (spec §3.3).

Para abstracts do PubMed: cada seção rotulada (BACKGROUND, METHODS, ...) vira um chunk;
seções longas são quebradas por parágrafo respeitando um teto aproximado de tokens.
"""

# ~4 chars por token (heurística). Teto de ~500 tokens por chunk.
MAX_CHARS = 2000


def _split_long(text):
    """Quebra um texto grande por parágrafos, agrupando até ~MAX_CHARS."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(p) > MAX_CHARS:  # parágrafo gigante: quebra por frase
            if buf:
                chunks.append(buf); buf = ""
            sent, cur = p.replace(". ", ".\n").split("\n"), ""
            for s in sent:
                if len(cur) + len(s) + 1 > MAX_CHARS and cur:
                    chunks.append(cur.strip()); cur = ""
                cur += s + " "
            if cur.strip():
                chunks.append(cur.strip())
            continue
        if len(buf) + len(p) + 2 > MAX_CHARS and buf:
            chunks.append(buf); buf = ""
        buf += (("\n\n" if buf else "") + p)
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


def chunk_article(article):
    """Recebe o dict do pubmed.fetch e devolve [(section_title, text), ...]."""
    out = []
    sections = article.get("sections") or []
    if sections:
        for label, text in sections:
            for piece in _split_long(text):
                out.append((label, piece))
    else:
        for piece in _split_long(article.get("abstract", "")):
            out.append((None, piece))
    # título como primeiro chunk curto ajuda a recuperação por palavra-chave
    title = article.get("title")
    if title:
        out.insert(0, ("Title", title))
    return out
