"""Domaine D — résolution de version et mode dégradé."""

from __future__ import annotations

import pytest

from yangmap.errors import ResolutionError
from yangmap.resolve import Ecart, analyser_version, resoudre


@pytest.mark.parametrize(
    "brut,attendu",
    [
        ("24.3.R3", (24, 3, 3)),      # Nokia
        ("17.3.4a", (17, 3, 4)),      # Cisco
        ("4.32.11M", (4, 32, 11)),    # Arista
        ("sros_24.3.r3", (24, 3, 3)),
        ("24.3", (24, 3, 0)),
        ("17", (17, 0, 0)),
    ],
)
def test_les_formes_reelles_des_trois_vendeurs_sont_lues(brut, attendu):
    v = analyser_version(brut)
    assert (v.majeur, v.mineur, v.patch) == attendu


def test_une_version_illisible_est_refusee():
    with pytest.raises(ResolutionError):
        analyser_version("indéterminée")


def test_version_exacte_disponible_ecart_nul():
    """D1 — le cas Nokia."""
    r = resoudre("24.3.3", ["24.3.3", "24.7.1"])
    assert r.ecart is Ecart.EXACT
    assert r.message is None


def test_meme_train_l_ecart_est_declare():
    """D2 — le cas Cisco : 17.3.4a demandé, 17.3.1 publié."""
    r = resoudre("17.3.4", ["17.3.1", "16.12.1"])
    assert r.ecart is Ecart.MEME_TRAIN
    assert str(r.version) == "17.3.1"
    assert "17.3.4" in r.message and "17.3.1" in r.message


def test_train_absent_l_avertissement_est_plus_fort():
    """D3 — le cas Arista quand aucun 4.32 n'est publié."""
    r = resoudre("4.32.11", ["4.28.0", "4.30.2"])
    assert r.ecart is Ecart.AUTRE_TRAIN
    assert "ATTENTION" in r.message


def test_aucun_bundle_installe_le_message_nomme_la_commande():
    """D5 — une erreur qui n'oriente pas fait perdre du temps."""
    with pytest.raises(ResolutionError, match="yangmap fetch"):
        resoudre("24.3.3", [])


def test_sans_version_demandee_le_choix_est_annonce():
    """Servir la plus récente est un choix : il ne doit pas être silencieux."""
    r = resoudre(None, ["24.3.3", "24.7.1"])
    assert str(r.version) == "24.7.1"
    assert r.message is not None


def test_le_patch_le_plus_proche_du_train_est_prefere():
    r = resoudre("17.3.9", ["17.3.1", "17.3.8", "17.6.1"])
    assert str(r.version) == "17.3.8"
