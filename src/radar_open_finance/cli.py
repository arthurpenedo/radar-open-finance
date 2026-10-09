"""Linha de comando: `radar-open-finance coletar` e `radar-open-finance baratos`."""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import banco, coleta, normaliza

# produto -> (família da API, normalizador, função que grava)
PRODUTOS = {
    "emprestimos": (coleta.FAMILIA_EMPRESTIMO_PESSOAL, normaliza.normalizar_emprestimo, banco.salvar_emprestimos),
    "contas": (coleta.FAMILIA_CONTAS, normaliza.normalizar_conta, banco.salvar_contas),
    "cartoes": (coleta.FAMILIA_CARTOES, normaliza.normalizar_cartao, banco.salvar_cartoes),
}


def coletar(db: str, buscar: coleta.Buscador = coleta.buscar_json, produtos: list[str] | None = None) -> dict:
    hoje = dt.date.today().isoformat()
    participantes = buscar(coleta.DIRETORIO_URL)
    con = banco.abrir(db)
    resumo = {"endpoints": 0, "linhas": 0, "falhas": [], "por_produto": {}}
    for nome in produtos or list(PRODUTOS):
        familia, normalizar, salvar = PRODUTOS[nome]
        endpoints = coleta.descobrir_endpoints(participantes, familia)
        linhas: list[dict] = []
        falhas: list[str] = []
        for ep in endpoints:
            for tentativa in (1, 2):  # leituras cortadas pela metade (Sicoob) costumam passar na 2ª
                try:
                    itens = coleta.baixar_paginas(ep["url"], buscar)
                except Exception as erro:  # um banco fora do ar não derruba a coleta
                    if tentativa == 2:
                        falhas.append(f"{nome} / {ep['organizacao']}: {erro}")
                    continue
                for item in itens:
                    linhas.extend(normalizar(item, ep["url"], hoje))
                break
        gravadas = salvar(con, linhas)
        resumo["por_produto"][nome] = {"endpoints": len(endpoints), "linhas": gravadas, "falhas": len(falhas)}
        resumo["endpoints"] += len(endpoints)
        resumo["linhas"] += gravadas
        resumo["falhas"].extend(falhas)
    con.close()
    return resumo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar-open-finance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coletar", help="baixa empréstimos, contas e cartões e grava no DuckDB")
    c.add_argument("--db", default="data/radar.duckdb")
    c.add_argument("--produto", choices=list(PRODUTOS), action="append", help="repetível; padrão: todos")
    b = sub.add_parser("baratos", help="rankings separados por tipo de produto")
    b.add_argument("--db", default="data/radar.duckdb")
    b.add_argument("--limite", type=int, default=10)
    b.add_argument("--produto", choices=list(PRODUTOS), default="emprestimos")
    args = ap.parse_args(argv)

    if args.cmd == "coletar":
        r = coletar(args.db, produtos=args.produto)
        for nome, p in r["por_produto"].items():
            print(f"{nome}: {p['endpoints']} endpoints, {p['linhas']} linhas, {p['falhas']} falhas")
        for f in r["falhas"]:
            print("  falha:", f, file=sys.stderr)
        return 0
    con = banco.abrir(args.db)
    if args.produto == "emprestimos":
        for nome, tipo, taxa in banco.mais_baratos(con, args.limite):
            print(f"{taxa * 100:6.2f}% a.m.  {nome}  ({tipo})")
    elif args.produto == "contas":
        for nome, tipo, cesta in banco.contas_mais_baratas(con, args.limite):
            print(f"R$ {cesta:7.2f} na cesta  {nome}  ({tipo})")
    else:
        for nome, cartao, bandeira, juros, anuidade in banco.cartoes_mais_baratos(con, args.limite):
            anu = "sem dado" if anuidade is None else f"R$ {anuidade:.2f}"
            print(f"{juros * 100:6.2f}% a.m. rotativo  {nome} - {cartao} {bandeira}  (anuidade {anu})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
