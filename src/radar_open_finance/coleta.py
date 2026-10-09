"""Descoberta dos endpoints no diretório de participantes e download paginado."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from urllib.parse import urljoin

DIRETORIO_URL = "https://data.directory.openbankingbrasil.org.br/participants"
FAMILIA_EMPRESTIMO_PESSOAL = "opendata-loans_personal-loans"
MAX_PAGINAS = 50

Buscador = Callable[[str], dict | list]


def buscar_json(url: str, timeout: int = 60) -> dict | list:
    """GET simples, sem autenticação (os dados abertos são públicos)."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def descobrir_endpoints(participantes: list[dict], familia: str) -> list[dict]:
    """Lista {organizacao, url} dos recursos ativos de uma família de API."""
    achados: dict[str, dict] = {}
    for org in participantes:
        for servidor in org.get("AuthorisationServers", []):
            for recurso in servidor.get("ApiResources", []):
                if recurso.get("ApiFamilyType") != familia or recurso.get("Status") != "Active":
                    continue
                for ep in recurso.get("ApiDiscoveryEndpoints", []):
                    url = ep.get("ApiEndpoint", "")
                    if url and "{" not in url:
                        achados.setdefault(url, {"organizacao": org.get("OrganisationName", ""), "url": url})
    return sorted(achados.values(), key=lambda e: e["url"])


def baixar_paginas(url: str, buscar: Buscador = buscar_json) -> list[dict]:
    """Segue links.next até acabar, devolvendo todos os itens de `data`."""
    itens: list[dict] = []
    atual: str | None = url
    vistos: set[str] = set()
    while atual and atual not in vistos and len(vistos) < MAX_PAGINAS:
        vistos.add(atual)
        resposta = buscar(atual)
        if not isinstance(resposta, dict):
            raise ValueError(f"resposta inesperada de {atual}")
        itens.extend(resposta.get("data", []))
        proxima = (resposta.get("links") or {}).get("next")
        atual = urljoin(atual, proxima) if proxima else None
    return itens
