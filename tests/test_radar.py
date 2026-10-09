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


def test_recoleta_no_mesmo_dia_nao_duplica(tmp_path):
    con = banco.abrir(str(tmp_path / "t.duckdb"))
    linhas = normaliza.normalizar_emprestimo(produto("A", "T", "0", "0.05"), "u", "2026-10-09")
    banco.salvar_emprestimos(con, linhas)
    banco.salvar_emprestimos(con, linhas)
    assert con.execute("SELECT COUNT(*) FROM emprestimos").fetchone()[0] == 1
