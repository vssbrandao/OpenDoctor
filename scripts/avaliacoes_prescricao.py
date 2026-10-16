""""Útil / não útil" das possíveis prescrições, para o médico revisor (docs/prescricao.md). Só LÊ o banco do
DATABASE_URL e mostra contagens por versão da IA, ação e remédio, sem médico e sem paciente. Ler produção só com o ok
do usuário.

    .venv/bin/python -m scripts.avaliacoes_prescricao
"""
from app import db


def main():
    rows = db.resumo_avaliacoes()
    if not rows:
        print("nenhuma avaliação")
        return
    ia = None
    for r in rows:
        if r["ia"] != ia:
            ia = r["ia"]
            print(f"\n{ia}\n  {'ação':<10} {'remédio':<32} {'útil':>5} {'não':>5}")
        print(f"  {r['acao']:<10} {r['nome'][:32]:<32} {r['util']:>5} {r['nao_util']:>5}")


if __name__ == "__main__":
    main()
