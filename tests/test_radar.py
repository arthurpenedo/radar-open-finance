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


def test_recoleta_no_mesmo_dia_nao_duplica(tmp_path):
    con = banco.abrir(str(tmp_path / "t.duckdb"))
    linhas = normaliza.normalizar_emprestimo(produto("A", "T", "0", "0.05"), "u", "2026-10-09")
    banco.salvar_emprestimos(con, linhas)
    banco.salvar_emprestimos(con, linhas)
    assert con.execute("SELECT COUNT(*) FROM emprestimos").fetchone()[0] == 1
