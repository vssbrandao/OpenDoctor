"""Filhos falsos para app/pdf_texto.extrai (tests/test_anexos.py): um que trava e um que morre sem responder. Ficam em
um módulo próprio porque o processo filho ('spawn') precisa importá-los."""
import os
import time


def trava(conn, b):
    time.sleep(60)


def morre(conn, b):
    os._exit(3)


def estoura(conn, b):
    from app import pdf_texto
    pdf_texto._limita()
    x = bytearray(1024 ** 3)            # 1 GB: acima do teto de 512 MB, o filho morre (MemoryError)
    conn.send(("ok", str(len(x))))


def lixo(conn, b):
    conn.send("isto não é a resposta")
    conn.close()
