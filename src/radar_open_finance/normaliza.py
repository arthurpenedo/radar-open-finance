"""Transforma o JSON de empréstimo pessoal em linhas planas."""

from __future__ import annotations


def _num(valor: object) -> float | None:
    try:
        return float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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
