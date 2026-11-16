"""Extração do texto de um PDF em um PROCESSO separado (usado por app/anexos.py).

Um PDF pode ser uma bomba de descompressão (um fluxo pequeno que vira gigabytes) ou travar o leitor. Por isso o pypdf
roda em um processo filho ('spawn': não herda as threads nem as conexões do servidor) com teto de memória (RLIMIT_AS) e
de CPU, e o pai espera no máximo PDF_TIMEOUT segundos: estourou, travou ou morreu → None (o chamador responde
"anexo_invalido"). O filho é sempre encerrado. Este módulo só importa a biblioteca padrão e o pypdf, para o filho
subir rápido; nada aqui grava em disco nem em log.
"""
import io
import multiprocessing

PDF_TIMEOUT = 15                   # segundos para ler o PDF inteiro
PDF_MEMORIA = 512 * 1024 * 1024    # teto de memória do filho (RLIMIT_AS)
PDF_PAGINAS = 30                   # só as primeiras páginas são lidas
PDF_CHARS = 20000                  # e o texto para de ser lido depois disso


def _limita():
    """Teto de memória e de CPU no filho. No macOS o RLIMIT_AS pode falhar: segue só com o tempo do pai."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (PDF_MEMORIA, PDF_MEMORIA))
    except Exception:
        pass
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (PDF_TIMEOUT + 5, PDF_TIMEOUT + 5))
    except Exception:
        pass


def filho(conn, b):
    """Roda no processo filho: manda ("ok", texto), ("senha", None) ou ("erro", None) pelo cano."""
    try:
        _limita()
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(b))
        del b
        if r.is_encrypted and not r.decrypt(""):
            conn.send(("senha", None))
            return
        n = len(r.pages)                                   # o número de páginas antes de ler: só as primeiras
        partes, total = [], 0
        for i in range(min(n, PDF_PAGINAS)):
            t = r.pages[i].extract_text() or ""
            partes.append(t)
            total += len(t)
            if total >= PDF_CHARS:
                break
        conn.send(("ok", "\n".join(partes)[:PDF_CHARS * 2]))   # folga para o pai ainda juntar os espaços
    except BaseException:                                  # MemoryError inclusive
        try:
            conn.send(("erro", None))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def extrai(b, alvo=None, timeout=None):
    """Texto cru do PDF ou None (inválido, com senha, estourou a memória, travou ou o filho morreu).
    alvo e timeout: só para os testes (um filho que trava ou morre)."""
    ctx = multiprocessing.get_context("spawn")
    receb, envia = ctx.Pipe(duplex=False)
    p = ctx.Process(target=alvo or filho, args=(envia, b), daemon=True)
    try:
        p.start()
        envia.close()                                      # só o filho escreve: se ele morrer, o pai lê EOF
        if not receb.poll(PDF_TIMEOUT if timeout is None else timeout):
            return None
        try:
            tipo, texto = receb.recv()
        except (EOFError, OSError, ValueError, TypeError):
            return None
        return texto if tipo == "ok" and isinstance(texto, str) else None
    except Exception:
        return None
    finally:
        try:
            if p.is_alive():
                p.kill()
            p.join(5)
        except Exception:
            pass
        try:
            receb.close()
        except Exception:
            pass
        try:
            p.close()
        except Exception:
            pass
