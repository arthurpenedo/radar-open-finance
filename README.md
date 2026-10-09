# radar-open-finance

Coleta os dados abertos de produtos do Open Finance Brasil (empréstimo pessoal, contas e cartões) e normaliza num DuckDB.

> **Status: parte 3 de 3.** Coleta de três produtos, rankings por tipo, servidor MCP e coleta semanal no GitHub Actions.

## O problema
As taxas e tarifas dos bancos estão públicas no Open Finance, mas espalhadas em APIs de dezenas de instituições. Ninguém compara isso de forma simples.

## O que faz
1. Lê o diretório oficial de participantes (`data.directory.openbankingbrasil.org.br`).
2. Descobre os endpoints ativos de `opendata-loans_personal-loans`, `opendata-accounts_personal-accounts` e `opendata-creditcards_personal-credit-cards`.
3. Baixa cada um (sem cadastro, sem autenticação), seguindo a paginação e tentando de novo uma vez se a leitura falhar.
4. Normaliza e grava as tabelas `emprestimos`, `contas` e `cartoes` do DuckDB.
5. Um banco fora do ar não derruba a coleta: a falha é listada e o resto segue.

## Números medidos (coleta real de 09/10/2026)
Fonte: APIs públicas de cada instituição, listadas pelo diretório do Open Finance Brasil.

| Produto | Endpoints | Linhas | Falhas |
|---|---|---|---|
| Empréstimo pessoal | 53 | 176 | 6 |
| Contas pessoais | 51 | 375 | 6 |
| Cartões de crédito | 41 | 1129 | 2 |

- Na parte 1, o empréstimo tinha 11 falhas. Mandar um `User-Agent` recuperou BMG, Carrefour (Atacadão, Sam's Club) e PicPay, que não respondiam sem ele, e escapar o espaço no link `next` do Santander resolveu a paginação dele.
- Falhas que sobraram: DNS que não resolve (ASA, QI, Celcoin), 404 (Inter, Sicoob no empréstimo, Itaú e PagSeguro nos cartões), 502 (Guanabara), 401 (Shopee) e 403 (Pan, nas contas). O Sicoob já cortou a resposta de contas no meio numa das execuções; a segunda tentativa resolveu.

## Como rodar
```
pip install -e .[dev]
radar-open-finance coletar                      # os três produtos
radar-open-finance coletar --produto cartoes    # só um (repetível)
radar-open-finance baratos --produto emprestimos
radar-open-finance baratos --produto contas
radar-open-finance baratos --produto cartoes
pytest
```

## Servidor MCP
`radar-open-finance mcp --db data/radar.duckdb` sobe um servidor MCP por stdio, **só leitura** (o DuckDB abre em `read_only`). Sem dependência extra: o protocolo mínimo (`initialize`, `tools/list`, `tools/call`) está em `mcp_server.py`. Ferramentas:
- `ranking_emprestimos`, `ranking_contas`, `ranking_cartoes` (parâmetro `limite`, 1 a 50);
- `buscar_banco` (`nome`, busca parcial): o que a coleta mais recente tem daquele banco nas três tabelas.

Exemplo de configuração num cliente MCP (rode `coletar` antes):
```json
{ "mcpServers": { "radar": { "command": "radar-open-finance", "args": ["mcp", "--db", "data/radar.duckdb"] } } }
```
Testado com mensagens JSON-RPC simuladas nos testes; não testei contra um cliente MCP real.

## Coleta semanal
`.github/workflows/coleta-semanal.yml` roda toda segunda (e sob demanda): testes, coleta, rankings no resumo do job e o `radar.duckdb` como artefato por 90 dias. Não grava nada no repositório.

## Como cada ranking é calculado
- **Empréstimos:** menor taxa máxima mensal por banco e tipo, sem consignado.
- **Contas:** soma das tarifas máximas de uma cesta de 4 serviços (saque em terminal, TED pela internet, extrato mensal, transferência entre contas). Só entram contas que publicam as quatro tarifas.
- **Cartões:** menor juros máximo do rotativo (maior que zero), sem cartões consignados; desempata pela anuidade nacional.

## Limites honestos
- Os valores são os **máximos e mínimos declarados** pelo banco por produto, não o que um cliente recebe.
- A cesta de contas é uma escolha minha de 4 serviços, não um custo mensal real; só 109 das 375 contas publicam as quatro tarifas.
- Cartões: 847 dos 1129 registros trazem juros do rotativo zero (não declarado ou sem rotativo); entram no ranking só os 282 com valor. Em vários dos mais baratos a anuidade não vem na API.
- Alguns valores publicados parecem baixos demais (ex.: 0,23% a.m. num empréstimo); foram repassados, não corrigidos.
- Recoletar no mesmo dia substitui a coleta anterior daquele dia.

## Licença
MIT
