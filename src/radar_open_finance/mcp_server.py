"""Servidor MCP (stdio, JSON-RPC por linha) só leitura sobre o DuckDB do radar.

Sem dependência extra: implementa o mínimo do protocolo MCP (initialize, tools/list, tools/call).
"""

from __future__ import annotations

import json
import sys
from typing import IO

import duckdb

from . import banco

VERSAO_PROTOCOLO = "2024-11-05"
LIMITE_PADRAO = 10
LIMITE_MAXIMO = 50

_LIMITE = {"type": "integer", "minimum": 1, "maximum": LIMITE_MAXIMO, "default": LIMITE_PADRAO}
FERRAMENTAS = [
    {
        "name": "ranking_emprestimos",
        "description": "Empréstimos pessoais com a menor taxa máxima mensal por banco e tipo (sem consignado).",
        "inputSchema": {"type": "object", "properties": {"limite": _LIMITE}},
    },
    {
        "name": "ranking_contas",
        "description": "Contas com a menor cesta de 4 tarifas (saque em terminal, TED, extrato, transferência).",
        "inputSchema": {"type": "object", "properties": {"limite": _LIMITE}},
    },
    {
        "name": "ranking_cartoes",
        "description": "Cartões com o menor juros máximo do rotativo (desempate pela anuidade).",
        "inputSchema": {"type": "object", "properties": {"limite": _LIMITE}},
    },
    {
        "name": "buscar_banco",
        "description": "Tudo que a coleta mais recente tem de um banco (busca parcial pelo nome).",
        "inputSchema": {
            "type": "object",
            "properties": {"nome": {"type": "string", "minLength": 2}},
            "required": ["nome"],
        },
    },
]


def _limite(args: dict) -> int:
    try:
        valor = int(args.get("limite", LIMITE_PADRAO))
    except (TypeError, ValueError):
        valor = LIMITE_PADRAO
    return max(1, min(valor, LIMITE_MAXIMO))


def _buscar_banco(con: duckdb.DuckDBPyConnection, nome: str) -> dict:
    padrao = f"%{nome.lower()}%"
    saida = {}
    consultas = {
        "emprestimos": "SELECT banco, tipo, taxa_min_mes, taxa_max_mes FROM emprestimos",
        "contas": "SELECT banco, tipo, tarifa_saque_terminal, tarifa_ted, tarifa_extrato, tarifa_transferencia FROM contas",
        "cartoes": "SELECT banco, nome, bandeira, anuidade_max, juros_rotativo_max_mes FROM cartoes",
    }
    for tabela, select in consultas.items():
        cur = con.execute(
            f"{select} WHERE coletado_em = (SELECT MAX(coletado_em) FROM {tabela}) "
            "AND lower(banco) LIKE ? ORDER BY 1 LIMIT 100",
            [padrao],
        )
        cols = [d[0] for d in cur.description]
        saida[tabela] = [dict(zip(cols, linha)) for linha in cur.fetchall()]
    return saida


def chamar(con: duckdb.DuckDBPyConnection, nome: str, args: dict):
    if nome == "ranking_emprestimos":
        return [
            {"banco": b, "tipo": t, "taxa_max_mes": x} for b, t, x in banco.mais_baratos(con, _limite(args))
        ]
    if nome == "ranking_contas":
        return [{"banco": b, "tipo": t, "cesta": c} for b, t, c in banco.contas_mais_baratas(con, _limite(args))]
    if nome == "ranking_cartoes":
        return [
            {"banco": b, "cartao": n, "bandeira": bd, "juros_rotativo_max_mes": j, "anuidade_max": a}
            for b, n, bd, j, a in banco.cartoes_mais_baratos(con, _limite(args))
        ]
    if nome == "buscar_banco":
        termo = str(args.get("nome", "")).strip()
        if len(termo) < 2:
            raise ValueError("informe 'nome' com ao menos 2 letras")
        return _buscar_banco(con, termo)
    raise KeyError(nome)


def responder(con: duckdb.DuckDBPyConnection, msg: dict) -> dict | None:
    """Trata uma mensagem JSON-RPC; devolve None para notificações."""
    metodo, id_ = msg.get("method"), msg.get("id")
    if id_ is None:
        return None

    def ok(resultado):
        return {"jsonrpc": "2.0", "id": id_, "result": resultado}

    def erro(codigo, texto):
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": texto}}

    if metodo == "initialize":
        return ok(
            {
                "protocolVersion": VERSAO_PROTOCOLO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "radar-open-finance", "version": "0.1.0"},
            }
        )
    if metodo == "ping":
        return ok({})
    if metodo == "tools/list":
        return ok({"tools": FERRAMENTAS})
    if metodo == "tools/call":
        params = msg.get("params") or {}
        try:
            dados = chamar(con, params.get("name", ""), params.get("arguments") or {})
        except KeyError:
            return erro(-32602, f"ferramenta desconhecida: {params.get('name')}")
        except Exception as e:  # erro de uso volta como resultado, para o modelo poder corrigir
            return ok({"content": [{"type": "text", "text": f"erro: {e}"}], "isError": True})
        texto = json.dumps(dados, ensure_ascii=False)
        return ok({"content": [{"type": "text", "text": texto}], "isError": False})
    return erro(-32601, f"método não suportado: {metodo}")


def servir(db: str, entrada: IO[str] = sys.stdin, saida: IO[str] = sys.stdout) -> None:
    con = duckdb.connect(db, read_only=True)
    try:
        for linha in entrada:
            if not linha.strip():
                continue
            try:
                msg = json.loads(linha)
            except json.JSONDecodeError:
                resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido"}}
            else:
                resp = responder(con, msg) if isinstance(msg, dict) else None
            if resp is not None:
                saida.write(json.dumps(resp, ensure_ascii=False) + "\n")
                saida.flush()
    finally:
        con.close()
