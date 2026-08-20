"""Domain F — the MCP server, queried the way a real client would."""

from __future__ import annotations

import json

import pytest

from yangmap.api import Carte
from yangmap.server import INSTRUCTIONS, create_server


@pytest.fixture
def serveur(racine_carte):
    return create_server(Carte(racine_carte))


async def _outils(serveur):
    return {o.name: o for o in await serveur.list_tools()}


@pytest.mark.asyncio
async def test_le_serveur_expose_exactement_trois_outils(serveur):
    """F1. The third tool, `yang_valider`, was added on 2026-08-13.

    It returns no operational data and contacts no equipment:
    it is pure index reading, just like the other two.
    """
    noms = set(await _outils(serveur))
    assert noms == {"yang_chercher", "yang_detail", "yang_valider"}, noms


@pytest.mark.asyncio
async def test_les_descriptions_interdisent_d_inventer(serveur):
    """The most important instruction must be in INSTRUCTIONS."""
    assert "NEVER INVENT" in INSTRUCTIONS.upper()


@pytest.mark.asyncio
async def test_les_descriptions_d_outils_restent_courtes(serveur):
    """F5 — the context budget is a design constraint.

    netlive repeats the equipment inventory in EVERY tool description;
    yangmap must not reproduce that defect.
    """
    for nom, outil in (await _outils(serveur)).items():
        assert len(outil.description) < 600, f"{nom}: {len(outil.description)} chars."


@pytest.mark.asyncio
async def test_chercher_par_le_serveur_rend_du_json_serialisable(serveur):
    r = await serveur.call_tool(
        "yang_chercher", {"sujet": "transceiver", "plateforme": "nokia_sros"}
    )
    charge = r.structured_content if hasattr(r, "structured_content") else r
    json.dumps(charge, ensure_ascii=False, default=str)


@pytest.mark.asyncio
async def test_une_plateforme_inconnue_rend_une_erreur_pas_une_exception(serveur):
    """The model must receive an actionable fact, not a crash."""
    r = await serveur.call_tool(
        "yang_chercher", {"sujet": "route", "plateforme": "inexistante"}
    )
    charge = r.structured_content if hasattr(r, "structured_content") else r
    texte = json.dumps(charge, ensure_ascii=False, default=str)
    assert "error" in texte and "unknown platform" in texte
