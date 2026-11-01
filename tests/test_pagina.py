from test_radar import CESTA_BARATA, cartao, conta, produto

from radar_open_finance import banco, cli, normaliza, pagina


def _db(tmp_path):
    db = str(tmp_path / "p.duckdb")
    con = banco.abrir(db)
    banco.salvar_emprestimos(
        con, normaliza.normalizar_emprestimo(produto("Banco <Alfa>", "EMPRESTIMO_SEM_CONSIGNACAO", "0", "0.05"), "u", "2026-10-09")
    )
    banco.salvar_contas(con, normaliza.normalizar_conta(conta("Banco Alfa", CESTA_BARATA), "u", "2026-10-09"))
    banco.salvar_cartoes(con, normaliza.normalizar_cartao(cartao("Banco Beta", "0.08", "10.00"), "u", "2026-10-09"))
    con.close()
    return db


def test_pagina_traz_os_tres_rankings_e_escapa_html(tmp_path):
    con = banco.abrir(_db(tmp_path))
    html = pagina.gerar_html(con)
    assert "5.00% a.m." in html and "R$ 5.00" in html and "8.00% a.m." in html
    assert "Banco &lt;Alfa&gt;" in html and "<Alfa>" not in html
    assert "2026-10-09" in html


def test_pagina_sem_coleta_nao_quebra(tmp_path):
    con = banco.abrir(str(tmp_path / "vazio.duckdb"))
    html = pagina.gerar_html(con)
    assert "sem coleta" in html and html.count("Sem dados na coleta.") == 3


def test_comando_pagina_grava_o_arquivo(tmp_path):
    saida = tmp_path / "site" / "index.html"
    assert cli.main(["pagina", "--db", _db(tmp_path), "--saida", str(saida)]) == 0
    assert saida.read_text(encoding="utf-8").startswith("<!doctype html>")
