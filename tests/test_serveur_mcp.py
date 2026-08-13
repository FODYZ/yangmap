"""Domaine F — le serveur MCP, interrogé comme un vrai client le ferait."""

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
    """F1. Le troisième, `yang_valider`, est arrivé le 2026-08-13.

    Il ne rend toujours aucune donnée d'exploitation et ne contacte rien :
    c'est de la lecture d'index, comme les deux autres.
    """
    noms = set(await _outils(serveur))
    assert noms == {"yang_chercher", "yang_detail", "yang_valider"}, noms


@pytest.mark.asyncio
async def test_les_descriptions_interdisent_d_inventer(serveur):
    """La consigne la plus importante doit être dans les instructions."""
    assert "INVENTE JAMAIS" in INSTRUCTIONS.upper() or "n'invente" in INSTRUCTIONS.lower()


@pytest.mark.asyncio
async def test_les_descriptions_d_outils_restent_courtes(serveur):
    """F5 — le budget de contexte est une contrainte de conception.

    netlive répète l'inventaire des équipements dans CHAQUE description
    d'outil ; yangmap ne doit pas reproduire ce défaut.
    """
    for nom, outil in (await _outils(serveur)).items():
        assert len(outil.description) < 600, f"{nom} : {len(outil.description)} car."


@pytest.mark.asyncio
async def test_chercher_par_le_serveur_rend_du_json_serialisable(serveur):
    r = await serveur.call_tool(
        "yang_chercher", {"sujet": "transceiver", "plateforme": "nokia_sros"}
    )
    charge = r.structured_content if hasattr(r, "structured_content") else r
    json.dumps(charge, ensure_ascii=False, default=str)


@pytest.mark.asyncio
async def test_une_plateforme_inconnue_rend_une_erreur_pas_une_exception(serveur):
    """Le modèle doit recevoir un fait exploitable, pas un plantage."""
    r = await serveur.call_tool(
        "yang_chercher", {"sujet": "route", "plateforme": "inexistante"}
    )
    charge = r.structured_content if hasattr(r, "structured_content") else r
    texte = json.dumps(charge, ensure_ascii=False, default=str)
    assert "error" in texte and "plateforme inconnue" in texte
