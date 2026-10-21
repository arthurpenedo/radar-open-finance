"""Página HTML estática com os três rankings da coleta mais recente (para o GitHub Pages)."""

from __future__ import annotations

from html import escape
from pathlib import Path

import duckdb

from . import banco

CSS = (
    "body{font-family:system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}"
    "table{border-collapse:collapse;width:100%;margin-bottom:2rem}"
    "th,td{border-bottom:1px solid #ddd;padding:.4rem .6rem;text-align:left}"
    "th{background:#f4f4f4}td.n{text-align:right;font-variant-numeric:tabular-nums}"
    "small{color:#666}"
)


def _tabela(titulo: str, explicacao: str, cabecalho: list[str], linhas: list[list[str]]) -> str:
    topo = "".join(f"<th>{escape(c)}</th>" for c in cabecalho)
    corpo = "".join(
        "<tr><td class='n'>{}</td>{}</tr>".format(
            i, "".join(f"<td>{escape(c)}</td>" for c in linha)
        )
        for i, linha in enumerate(linhas, 1)
    )
    if not linhas:
        corpo = f"<tr><td colspan='{len(cabecalho) + 1}'>Sem dados na coleta.</td></tr>"
    return (
        f"<h2>{escape(titulo)}</h2><p><small>{escape(explicacao)}</small></p>"
        f"<table><tr><th>#</th>{topo}</tr>{corpo}</table>"
    )


def _data_da_coleta(con: duckdb.DuckDBPyConnection) -> str:
    datas = [
        con.execute(f"SELECT MAX(coletado_em) FROM {t}").fetchone()[0]
        for t in ("emprestimos", "contas", "cartoes")
    ]
    datas = [d for d in datas if d]
    return max(datas) if datas else "sem coleta"


def gerar_html(con: duckdb.DuckDBPyConnection, limite: int = 10) -> str:
    """Monta a página a partir das mesmas consultas do comando `baratos`."""
    emprestimos = [
        [nome, tipo, f"{taxa * 100:.2f}% a.m."] for nome, tipo, taxa in banco.mais_baratos(con, limite)
    ]
    contas = [
        [nome, tipo, f"R$ {cesta:.2f}"] for nome, tipo, cesta in banco.contas_mais_baratas(con, limite)
    ]
    cartoes = [
        [
            nome,
            cartao,
            bandeira or "",
            f"{juros * 100:.2f}% a.m.",
            "sem dado" if anuidade is None else f"R$ {anuidade:.2f}",
        ]
        for nome, cartao, bandeira, juros, anuidade in banco.cartoes_mais_baratos(con, limite)
    ]
    partes = [
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>radar-open-finance</title><style>{CSS}</style></head><body>",
        "<h1>radar-open-finance</h1>",
        f"<p>Os produtos mais baratos declarados no Open Finance Brasil. Coleta de <b>{escape(_data_da_coleta(con))}</b>. "
        "<a href='https://github.com/arthurpenedo/radar-open-finance'>Código no GitHub</a>.</p>",
        _tabela(
            "Empréstimo pessoal",
            "Menor taxa máxima mensal por banco e tipo, sem consignado.",
            ["Banco", "Tipo", "Taxa máxima"],
            emprestimos,
        ),
        _tabela(
            "Contas",
            "Soma das tarifas máximas de 4 serviços (saque em terminal, TED pela internet, extrato, transferência entre contas).",
            ["Banco", "Tipo", "Cesta"],
            contas,
        ),
        _tabela(
            "Cartões de crédito",
            "Menor juros máximo do rotativo (maior que zero), sem consignado; desempata pela anuidade.",
            ["Banco", "Cartão", "Bandeira", "Juros rotativo", "Anuidade"],
            cartoes,
        ),
        "<p><small>Valores máximos declarados pelos bancos, não o que um cliente recebe. "
        "Fonte: APIs públicas listadas pelo diretório do Open Finance Brasil.</small></p>",
        "</body></html>",
    ]
    return "".join(partes)


def gravar(db: str, saida: str, limite: int = 10) -> Path:
    con = banco.abrir(db)
    try:
        html = gerar_html(con, limite)
    finally:
        con.close()
    destino = Path(saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino
