"""Transforma o JSON de empréstimo pessoal em linhas planas."""

from __future__ import annotations


def _num(valor: object) -> float | None:
    try:
        return float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


TARIFAS_CONTA = {
    "CADASTRO": "tarifa_cadastro",
    "SAQUE_TERMINAL": "tarifa_saque_terminal",
    "TED_INTERNET": "tarifa_ted",
    "EXTRATO_MES_E": "tarifa_extrato",
    "TRANSF_RECURSO_E": "tarifa_transferencia",
}


def _valor_maximo(servico: dict) -> float | None:
    return _num((servico.get("maximum") or {}).get("value"))


def normalizar_conta(item: dict, fonte: str, coletado_em: str) -> list[dict]:
    """Uma linha por conta. Tarifas = valor máximo em R$ de cada serviço (None se o banco não publica)."""
    part = item.get("participant") or {}
    linha = {
        "cnpj": str(part.get("cnpjNumber") or ""),
        "banco": part.get("brand") or part.get("name") or "",
        "razao_social": part.get("name") or "",
        "tipo": item.get("type") or "",
        "termos_url": item.get("termsConditions") or "",
        "fonte_url": fonte,
        "coletado_em": coletado_em,
    }
    linha.update({coluna: None for coluna in TARIFAS_CONTA.values()})
    for servico in (item.get("fees") or {}).get("priorityServices") or []:
        coluna = TARIFAS_CONTA.get(servico.get("code"))
        if coluna and linha[coluna] is None:
            linha[coluna] = _valor_maximo(servico)
    return [linha]


def normalizar_cartao(item: dict, fonte: str, coletado_em: str) -> list[dict]:
    """Uma linha por cartão. Juros do rotativo = maior `maximumRate` de `interest.rates` (fração ao mês)."""
    part = item.get("participant") or {}
    ident = item.get("identification") or {}
    anuidades = [
        _valor_maximo(s)
        for s in (item.get("fees") or {}).get("services") or []
        if s.get("code") == "ANUIDADE_NACIONAL"
    ]
    anuidades = [a for a in anuidades if a is not None]
    juros = [
        _num(r.get("maximumRate"))
        for r in (item.get("interest") or {}).get("rates") or []
    ]
    juros = [j for j in juros if j is not None]
    return [
        {
            "cnpj": str(part.get("cnpjNumber") or ""),
            "banco": part.get("brand") or part.get("name") or "",
            "razao_social": part.get("name") or "",
            "nome": item.get("name") or "",
            "categoria": (ident.get("product") or {}).get("type") or "",
            "bandeira": (ident.get("creditCard") or {}).get("network") or "",
            "anuidade_max": max(anuidades) if anuidades else None,
            "juros_rotativo_max_mes": max(juros) if juros else None,
            "fonte_url": fonte,
            "coletado_em": coletado_em,
        }
    ]


def normalizar_emprestimo(item: dict, fonte: str, coletado_em: str) -> list[dict]:
    """Uma linha por (produto, indexador). Taxas são mensais, em fração (0.05 = 5% a.m.)."""
    part = item.get("participant") or {}
    garantias = ",".join(item.get("requiredWarranties") or [])
    linhas = []
    for taxa in item.get("interestRates") or [{}]:
        linhas.append(
            {
                "cnpj": str(part.get("cnpjNumber") or ""),
                "banco": part.get("brand") or part.get("name") or "",
                "razao_social": part.get("name") or "",
                "tipo": item.get("type") or "",
                "indexador": taxa.get("referentialRateIndexer") or "",
                "taxa_min_mes": _num(taxa.get("minimumRate")),
                "taxa_max_mes": _num(taxa.get("maximumRate")),
                "garantias": garantias,
                "termos_url": item.get("termsConditions") or "",
                "fonte_url": fonte,
                "coletado_em": coletado_em,
            }
        )
    return linhas
