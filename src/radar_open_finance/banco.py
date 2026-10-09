"""Armazenamento em DuckDB."""

from __future__ import annotations

from pathlib import Path

import duckdb

COLUNAS = [
    "cnpj", "banco", "razao_social", "tipo", "indexador", "taxa_min_mes",
    "taxa_max_mes", "garantias", "termos_url", "fonte_url", "coletado_em",
]

DDL = """
CREATE TABLE IF NOT EXISTS emprestimos (
    cnpj VARCHAR, banco VARCHAR, razao_social VARCHAR, tipo VARCHAR,
    indexador VARCHAR, taxa_min_mes DOUBLE, taxa_max_mes DOUBLE,
    garantias VARCHAR, termos_url VARCHAR, fonte_url VARCHAR, coletado_em VARCHAR
)
"""


def abrir(caminho: str) -> duckdb.DuckDBPyConnection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(caminho)
    con.execute(DDL)
    return con


def salvar_emprestimos(con: duckdb.DuckDBPyConnection, linhas: list[dict]) -> int:
    """Insere as linhas; recoleta no mesmo dia substitui a anterior."""
    if not linhas:
        return 0
    datas = sorted({linha["coletado_em"] for linha in linhas})
    for data in datas:
        con.execute("DELETE FROM emprestimos WHERE coletado_em = ?", [data])
    con.executemany(
        f"INSERT INTO emprestimos VALUES ({','.join('?' * len(COLUNAS))})",
        [[linha[c] for c in COLUNAS] for linha in linhas],
    )
    return len(linhas)


def mais_baratos(con: duckdb.DuckDBPyConnection, limite: int = 10) -> list[tuple]:
    """Menor taxa máxima mensal por banco na coleta mais recente (sem consignado)."""
    return con.execute(
        """
        SELECT banco, tipo, MIN(taxa_max_mes) AS taxa
        FROM emprestimos
        WHERE coletado_em = (SELECT MAX(coletado_em) FROM emprestimos)
          AND taxa_max_mes IS NOT NULL AND taxa_max_mes > 0
          AND tipo NOT LIKE '%CONSIGNADO%'
        GROUP BY banco, tipo
        ORDER BY taxa
        LIMIT ?
        """,
        [limite],
    ).fetchall()
