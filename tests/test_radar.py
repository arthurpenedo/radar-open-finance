from radar_open_finance import banco, cli, coleta, normaliza

DIRETORIO = [
    {
        "OrganisationName": "Banco A",
        "AuthorisationServers": [
            {
                "ApiResources": [
                    {
                        "ApiFamilyType": "opendata-loans_personal-loans",
                        "Status": "Active",
                        "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://a.test/personal-loans"}],
                    },
                    {
                        "ApiFamilyType": "opendata-loans_personal-loans",
                        "Status": "Retired",
                        "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://velho.test/personal-loans"}],
                    },
                    {
                        "ApiFamilyType": "payments-pix",
                        "Status": "Active",
                        "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://a.test/pix"}],
                    },
                ]
            }
        ],
    },
    {
        "OrganisationName": "Banco B",
        "AuthorisationServers": [
            {
                "ApiResources": [
                    {
                        "ApiFamilyType": "opendata-loans_personal-loans",
                        "Status": "Active",
                        "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://b.test/personal-loans"}],
                    }
                ]
            }
        ],
    },
]


def produto(marca, tipo, minima, maxima):
    return {
        "type": tipo,
        "participant": {"brand": marca, "name": marca + " S.A.", "cnpjNumber": "123"},
        "requiredWarranties": ["NAO_EXIGE_GARANTIA"],
        "termsConditions": "https://termos.test",
        "interestRates": [
            {"minimumRate": minima, "maximumRate": maxima, "referentialRateIndexer": "PRE_FIXADO"}
        ],
    }


def falso_buscador(respostas):
    def buscar(url):
        r = respostas[url]
        if isinstance(r, Exception):
            raise r
        return r

    return buscar


def test_descobre_so_endpoints_ativos_da_familia():
    eps = coleta.descobrir_endpoints(DIRETORIO, coleta.FAMILIA_EMPRESTIMO_PESSOAL)
    assert [e["url"] for e in eps] == ["https://a.test/personal-loans", "https://b.test/personal-loans"]


def test_baixa_paginas_seguindo_next_e_evita_laco():
    respostas = {
        "https://x.test/p": {"data": [1], "links": {"next": "https://x.test/p?page=2"}},
        "https://x.test/p?page=2": {"data": [2], "links": {"next": "https://x.test/p"}},
    }
    assert coleta.baixar_paginas("https://x.test/p", falso_buscador(respostas)) == [1, 2]


def test_paginacao_escapa_espaco_no_link_next():
    respostas = {
        "https://x.test/p": {"data": [1], "links": {"next": "/p?page=2&brand=Banco Santander"}},
        "https://x.test/p?page=2&brand=Banco%20Santander": {"data": [2]},
    }
    assert coleta.baixar_paginas("https://x.test/p", falso_buscador(respostas)) == [1, 2]


def test_normaliza_taxas_como_numero():
    linhas = normaliza.normalizar_emprestimo(
        produto("Banco A", "EMPRESTIMO_SEM_CONSIGNACAO", "0.01", "0.0950"), "https://a.test", "2026-10-09"
    )
    assert len(linhas) == 1
    assert linhas[0]["taxa_max_mes"] == 0.095
    assert linhas[0]["banco"] == "Banco A"


def test_normaliza_taxa_invalida_vira_nulo():
    linhas = normaliza.normalizar_emprestimo(produto("X", "T", None, "abc"), "u", "2026-10-09")
    assert linhas[0]["taxa_min_mes"] is None and linhas[0]["taxa_max_mes"] is None


def test_coleta_completa_grava_e_tolera_falha(tmp_path):
    respostas = {
        coleta.DIRETORIO_URL: DIRETORIO,
        "https://a.test/personal-loans": {
            "data": [
                produto("Banco A", "EMPRESTIMO_SEM_CONSIGNACAO", "0.01", "0.08"),
                produto("Banco A", "EMPRESTIMO_CONSIGNADO", "0.01", "0.02"),
            ]
        },
        "https://b.test/personal-loans": RuntimeError("fora do ar"),
    }
    db = str(tmp_path / "t.duckdb")
    r = cli.coletar(db, falso_buscador(respostas))
    assert r["endpoints"] == 2 and r["linhas"] == 2 and len(r["falhas"]) == 1
    con = banco.abrir(db)
    assert banco.mais_baratos(con) == [("Banco A", "EMPRESTIMO_SEM_CONSIGNACAO", 0.08)]


def servico(codigo, valor):
    return {"code": codigo, "maximum": {"value": valor, "currency": "BRL"}}


def conta(marca, valores):
    return {
        "type": "CONTA_DEPOSITO_A_VISTA",
        "participant": {"brand": marca, "name": marca + " S.A.", "cnpjNumber": "1"},
        "fees": {"priorityServices": [servico(c, v) for c, v in valores.items()]},
    }


CESTA_BARATA = {"SAQUE_TERMINAL": "0.00", "TED_INTERNET": "5.00", "EXTRATO_MES_E": "0.00", "TRANSF_RECURSO_E": "0.00"}


def cartao(marca, juros, anuidade):
    return {
        "name": "CARTAO",
        "participant": {"brand": marca, "name": marca + " S.A.", "cnpjNumber": "1"},
        "identification": {"product": {"type": "GOLD"}, "creditCard": {"network": "VISA"}},
        "fees": {"services": [servico("ANUIDADE_NACIONAL", anuidade), servico("SAQUE_CARTAO_BRASIL", "9.00")]},
        "interest": {"rates": [{"maximumRate": juros}]},
    }


def test_normaliza_conta_pega_tarifas_da_cesta():
    (linha,) = normaliza.normalizar_conta(conta("A", CESTA_BARATA), "u", "2026-10-09")
    assert linha["tarifa_ted"] == 5.0 and linha["tarifa_saque_terminal"] == 0.0
    assert linha["tarifa_cadastro"] is None


def test_normaliza_cartao_pega_anuidade_e_juros():
    (linha,) = normaliza.normalizar_cartao(cartao("A", "0.1500", "120.00"), "u", "2026-10-09")
    assert linha["anuidade_max"] == 120.0 and linha["juros_rotativo_max_mes"] == 0.15
    assert linha["bandeira"] == "VISA" and linha["categoria"] == "GOLD"


def test_coleta_de_contas_e_cartoes_com_rankings_separados(tmp_path):
    diretorio = [
        {
            "OrganisationName": "Banco A",
            "AuthorisationServers": [
                {
                    "ApiResources": [
                        {
                            "ApiFamilyType": coleta.FAMILIA_CONTAS,
                            "Status": "Active",
                            "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://a.test/contas"}],
                        },
                        {
                            "ApiFamilyType": coleta.FAMILIA_CARTOES,
                            "Status": "Active",
                            "ApiDiscoveryEndpoints": [{"ApiEndpoint": "https://a.test/cartoes"}],
                        },
                    ]
                }
            ],
        }
    ]
    respostas = {
        coleta.DIRETORIO_URL: diretorio,
        "https://a.test/contas": {
            "data": [
                conta("Barato", CESTA_BARATA),
                conta("Caro", {**CESTA_BARATA, "TED_INTERNET": "20.00"}),
                conta("Incompleto", {"TED_INTERNET": "0.00"}),
            ]
        },
        "https://a.test/cartoes": {
            "data": [cartao("Caro", "0.1500", "10.00"), cartao("Barato", "0.0800", "50.00"), cartao("Zero", "0.0", "0.00")]
        },
    }
    db = str(tmp_path / "t.duckdb")
    r = cli.coletar(db, falso_buscador(respostas))
    assert r["por_produto"]["contas"]["linhas"] == 3 and r["por_produto"]["cartoes"]["linhas"] == 3
    con = banco.abrir(db)
    assert [c[0] for c in banco.contas_mais_baratas(con)] == ["Barato", "Caro"]
    assert [c[0] for c in banco.cartoes_mais_baratos(con)] == ["Barato", "Caro"]


def test_buscador_manda_user_agent(monkeypatch):
    enviados = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"data": []}'

    def falso_urlopen(req, timeout):
        enviados.update(req.headers)
        return Resp()

    monkeypatch.setattr(coleta.urllib.request, "urlopen", falso_urlopen)
    coleta.buscar_json("https://x.test")
    assert "User-agent" in enviados


def banco_com_dados(tmp_path):
    db = str(tmp_path / "m.duckdb")
    con = banco.abrir(db)
    banco.salvar_emprestimos(
        con, normaliza.normalizar_emprestimo(produto("Banco Alfa", "EMPRESTIMO_SEM_CONSIGNACAO", "0", "0.05"), "u", "2026-10-09")
    )
    banco.salvar_contas(con, normaliza.normalizar_conta(conta("Banco Alfa", CESTA_BARATA), "u", "2026-10-09"))
    banco.salvar_cartoes(con, normaliza.normalizar_cartao(cartao("Banco Beta", "0.08", "10.00"), "u", "2026-10-09"))
    con.close()
    return db


def conversar(db, mensagens):
    import io
    import json

    from radar_open_finance import mcp_server

    entrada = io.StringIO("\n".join(json.dumps(m) for m in mensagens) + "\n")
    saida = io.StringIO()
    mcp_server.servir(db, entrada, saida)
    return [json.loads(linha) for linha in saida.getvalue().splitlines()]


def chamada(id_, ferramenta, **args):
    return {"jsonrpc": "2.0", "id": id_, "method": "tools/call", "params": {"name": ferramenta, "arguments": args}}


def test_mcp_lista_ferramentas_e_ignora_notificacao(tmp_path):
    respostas = conversar(
        banco_com_dados(tmp_path),
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
    )
    assert len(respostas) == 2
    assert respostas[0]["result"]["serverInfo"]["name"] == "radar-open-finance"
    assert {t["name"] for t in respostas[1]["result"]["tools"]} >= {"ranking_emprestimos", "buscar_banco"}


def test_mcp_rankings_e_busca_por_banco(tmp_path):
    import json

    r = conversar(
        banco_com_dados(tmp_path),
        [chamada(1, "ranking_emprestimos"), chamada(2, "ranking_cartoes", limite=1), chamada(3, "buscar_banco", nome="ALFA")],
    )
    assert json.loads(r[0]["result"]["content"][0]["text"])[0]["taxa_max_mes"] == 0.05
    assert json.loads(r[1]["result"]["content"][0]["text"])[0]["banco"] == "Banco Beta"
    achados = json.loads(r[2]["result"]["content"][0]["text"])
    assert len(achados["emprestimos"]) == 1 and len(achados["contas"]) == 1 and achados["cartoes"] == []


def test_mcp_erros_de_uso_e_somente_leitura(tmp_path):
    db = banco_com_dados(tmp_path)
    r = conversar(db, [chamada(1, "buscar_banco", nome="a"), chamada(2, "nao_existe"), {"jsonrpc": "2.0", "id": 3, "method": "x"}])
    assert r[0]["result"]["isError"] is True
    assert r[1]["error"]["code"] == -32602
    assert r[2]["error"]["code"] == -32601
    import duckdb
    import pytest

    con = duckdb.connect(db, read_only=True)
    with pytest.raises(duckdb.Error):
        con.execute("DELETE FROM emprestimos")


def test_recoleta_no_mesmo_dia_nao_duplica(tmp_path):
    con = banco.abrir(str(tmp_path / "t.duckdb"))
    linhas = normaliza.normalizar_emprestimo(produto("A", "T", "0", "0.05"), "u", "2026-10-09")
    banco.salvar_emprestimos(con, linhas)
    banco.salvar_emprestimos(con, linhas)
    assert con.execute("SELECT COUNT(*) FROM emprestimos").fetchone()[0] == 1
