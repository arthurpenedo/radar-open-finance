"""Armazenamento em DuckDB."""

from __future__ import annotations

from pathlib import Path

import duckdb

COLUNAS = [
    "cnpj", "banco", "razao_social", "tipo", "indexador", "taxa_min_mes",
    "taxa_max_mes", "garantias", "termos_url", "fonte_url", "coletado_em",
]
COLUNAS_CONTAS = [
    "cnpj", "banco", "razao_social", "tipo", "tarifa_cadastro", "tarifa_saque_terminal",
    "tarifa_ted", "tarifa_extrato", "tarifa_transferencia", "termos_url", "fonte_url", "coletado_em",
]
COLUNAS_CARTOES = [
    "cnpj", "banco", "razao_social", "nome", "categoria", "bandeira", "anuidade_max",
    "juros_rotativo_max_mes", "fonte_url", "coletado_em",
]

DDL = [
    """
    CREATE TABLE IF NOT EXISTS emprestimos (
        cnpj VARCHAR, banco VARCHAR, razao_social VARCHAR, tipo VARCHAR,
        indexador VARCHAR, taxa_min_mes DOUBLE, taxa_max_mes DOUBLE,
        garantias VARCHAR, termos_url VARCHAR, fonte_url VARCHAR, coletado_em VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contas (
        cnpj VARCHAR, banco VARCHAR, razao_social VARCHAR, tipo VARCHAR,
        tarifa_cadastro DOUBLE, tarifa_saque_terminal DOUBLE, tarifa_ted DOUBLE,
        tarifa_extrato DOUBLE, tarifa_transferencia DOUBLE,
        termos_url VARCHAR, fonte_url VARCHAR, coletado_em VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cartoes (
        cnpj VARCHAR, banco VARCHAR, razao_social VARCHAR, nome VARCHAR,
        categoria VARCHAR, bandeira VARCHAR, anuidade_max DOUBLE,
        juros_rotativo_max_mes DOUBLE, fonte_url VARCHAR, coletado_em VARCHAR
    )
    """,
]


def abrir(caminho: str) -> duckdb.DuckDBPyConnection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(caminho)
    for ddl in DDL:
        con.execute(ddl)
    return con


def _salvar(con: duckdb.DuckDBPyConnection, tabela: str, colunas: list[str], linhas: list[dict]) -> int:
    """Insere as linhas; recoleta no mesmo dia substitui a anterior."""
    if not linhas:
        return 0
    for data in sorted({linha["coletado_em"] for linha in linhas}):
        con.execute(f"DELETE FROM {tabela} WHERE coletado_em = ?", [data])
    con.executemany(
        f"INSERT INTO {tabela} VALUES ({','.join('?' * len(colunas))})",
        [[linha[c] for c in colunas] for linha in linhas],
    )
    return len(linhas)


def salvar_emprestimos(con: duckdb.DuckDBPyConnection, linhas: list[dict]) -> int:
    return _salvar(con, "emprestimos", COLUNAS, linhas)


def salvar_contas(con: duckdb.DuckDBPyConnection, linhas: list[dict]) -> int:
    return _salvar(con, "contas", COLUNAS_CONTAS, linhas)


def salvar_cartoes(con: duckdb.DuckDBPyConnection, linhas: list[dict]) -> int:
    return _salvar(con, "cartoes", COLUNAS_CARTOES, linhas)


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


def contas_mais_baratas(con: duckdb.DuckDBPyConnection, limite: int = 10) -> list[tuple]:
    """Cesta de 4 serviços (saque em terminal, TED pela internet, extrato mensal, transferência
    entre contas): soma das tarifas máximas. Só entram contas que publicam as quatro."""
    return con.execute(
        """
        SELECT banco, tipo,
               tarifa_saque_terminal + tarifa_ted + tarifa_extrato + tarifa_transferencia AS cesta
        FROM contas
        WHERE coletado_em = (SELECT MAX(coletado_em) FROM contas)
          AND tarifa_saque_terminal IS NOT NULL AND tarifa_ted IS NOT NULL
          AND tarifa_extrato IS NOT NULL AND tarifa_transferencia IS NOT NULL
        ORDER BY cesta, banco
        LIMIT ?
        """,
        [limite],
    ).fetchall()


def cartoes_mais_baratos(con: duckdb.DuckDBPyConnection, limite: int = 10) -> list[tuple]:
    """Menor juros do rotativo (taxa máxima mensal > 0) na coleta mais recente, sem cartão consignado;
    desempata pela anuidade."""
    return con.execute(
        """
        SELECT banco, nome, bandeira, juros_rotativo_max_mes, anuidade_max
        FROM cartoes
        WHERE coletado_em = (SELECT MAX(coletado_em) FROM cartoes)
          AND juros_rotativo_max_mes IS NOT NULL AND juros_rotativo_max_mes > 0
          AND upper(nome) NOT LIKE '%CONSIGNADO%'
        ORDER BY juros_rotativo_max_mes, anuidade_max NULLS LAST, banco
        LIMIT ?
        """,
        [limite],
    ).fetchall()
