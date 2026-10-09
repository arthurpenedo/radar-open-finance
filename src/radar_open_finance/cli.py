"""Linha de comando: `radar-open-finance coletar` e `radar-open-finance baratos`."""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import banco, coleta, normaliza


def coletar(db: str, buscar: coleta.Buscador = coleta.buscar_json) -> dict:
    hoje = dt.date.today().isoformat()
    participantes = buscar(coleta.DIRETORIO_URL)
    endpoints = coleta.descobrir_endpoints(participantes, coleta.FAMILIA_EMPRESTIMO_PESSOAL)
    linhas: list[dict] = []
    falhas: list[str] = []
    for ep in endpoints:
        try:
            for item in coleta.baixar_paginas(ep["url"], buscar):
                linhas.extend(normaliza.normalizar_emprestimo(item, ep["url"], hoje))
        except Exception as erro:  # um banco fora do ar não derruba a coleta
            falhas.append(f"{ep['organizacao']}: {erro}")
    con = banco.abrir(db)
    gravadas = banco.salvar_emprestimos(con, linhas)
    con.close()
    return {"endpoints": len(endpoints), "falhas": falhas, "linhas": gravadas}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar-open-finance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coletar", help="baixa empréstimos pessoais e grava no DuckDB")
    c.add_argument("--db", default="data/radar.duckdb")
    b = sub.add_parser("baratos", help="menores taxas máximas por banco")
    b.add_argument("--db", default="data/radar.duckdb")
    b.add_argument("--limite", type=int, default=10)
    args = ap.parse_args(argv)

    if args.cmd == "coletar":
        r = coletar(args.db)
        print(f"{r['endpoints']} endpoints, {r['linhas']} linhas gravadas, {len(r['falhas'])} falhas")
        for f in r["falhas"]:
            print("  falha:", f, file=sys.stderr)
        return 0
    con = banco.abrir(args.db)
    for nome, tipo, taxa in banco.mais_baratos(con, args.limite):
        print(f"{taxa * 100:6.2f}% a.m.  {nome}  ({tipo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
