# radar-open-finance

Coleta os dados abertos de produtos do Open Finance Brasil e normaliza num DuckDB.

> **Status: parte 1 de 3.** Hoje coleta empréstimo pessoal. Faltam contas e cartões, painel comparativo e servidor MCP.

## O problema
As taxas de crédito dos bancos estão públicas no Open Finance, mas espalhadas em APIs de dezenas de instituições. Ninguém compara isso de forma simples.

## O que faz
1. Lê o diretório oficial de participantes (`data.directory.openbankingbrasil.org.br`).
2. Descobre os endpoints ativos de `opendata-loans_personal-loans`.
3. Baixa cada um (sem cadastro, sem autenticação), seguindo a paginação.
4. Normaliza taxas mínima e máxima mensais e grava na tabela `emprestimos` do DuckDB.
5. Um banco fora do ar não derruba a coleta: a falha é listada e o resto segue.

## Números medidos (coleta real de 09/10/2026)
- 53 endpoints ativos descobertos no diretório (campo `ApiDiscoveryEndpoints`).
- 161 linhas gravadas; 11 falhas (403, 404, 401, 503 e DNS) de bancos que não respondem a quem não é participante.
- Fonte: APIs públicas de cada instituição, listadas pelo diretório do Open Finance Brasil.

## Como rodar
```
pip install -e .[dev]
radar-open-finance coletar
radar-open-finance baratos --limite 10
pytest
```

## Limites honestos
- As taxas são as **máximas e mínimas declaradas** pelo banco por produto, não a taxa que um cliente recebe.
- O ranking `baratos` ainda mistura tipos de produto (ex.: cheque especial, home equity). Separar por tipo é a próxima parte.
- Alguns valores publicados parecem baixos demais (ex.: 0,23% a.m. num produto); não foram corrigidos, só repassados.
- Os 11 endpoints com erro ficam sem dados até o banco liberar.

## Licença
MIT
