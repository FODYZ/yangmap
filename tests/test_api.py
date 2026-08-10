"""Domaines D, F — le contrat rendu au modèle."""

from __future__ import annotations

import json

import pytest

from yangmap.api import Carte, en_erreur
from yangmap.errors import IndexError_, ResolutionError


def test_une_plateforme_inconnue_ne_se_replie_sur_aucune_autre(racine_carte):
    """D4 — BLOQUANT. Un repli silencieux rendrait des chemins d'un autre
    vendeur, que le modèle croirait valides."""
    with pytest.raises(ResolutionError, match="plateforme inconnue"):
        Carte(racine_carte).chercher("route", "juniper_junos")


def test_une_plateforme_connue_mais_sans_index_nomme_la_commande(racine_carte):
    """D5."""
    with pytest.raises(IndexError_, match="yangmap fetch"):
        Carte(racine_carte).chercher("route", "arista_eos")


def test_toute_reponse_porte_le_bundle_servi(racine_carte):
    """D6 — BLOQUANT : une réponse ne dissimule jamais sur quoi elle porte."""
    r = Carte(racine_carte).chercher("transceiver", "nokia_sros", "24.3.3")
    assert r["bundle_servi"] == "24.3.3"
    assert r["ecart"] == "exact"
    assert r["avertissement"] is None


def test_un_ecart_de_version_est_declare_dans_la_reponse(racine_carte):
    """D2 + D6 — l'index est en 24.3.3, on demande 24.3.9."""
    r = Carte(racine_carte).chercher("transceiver", "nokia_sros", "24.3.9")
    assert r["ecart"] == "meme_train"
    assert "24.3.9" in r["avertissement"]


def test_aucun_resultat_le_message_interdit_explicitement_d_inventer(racine_carte):
    """E3 — le message est lu par un modèle : il doit lui dire quoi faire."""
    r = Carte(racine_carte).chercher("zorglub", "nokia_sros")
    assert r["resultats"] == []
    assert "inventer" in r["message"].lower()


def test_le_detail_rend_les_enfants_immediats_pas_le_sous_arbre(racine_carte):
    """F2 — rendre le sous-arbre entier reproduirait le problème d'origine."""
    r = Carte(racine_carte).detail(
        "/state/port[port-id=?]/transceiver", "nokia_sros"
    )
    noms = {e["nom"] for e in r["enfants"]}
    assert noms == {"type", "equipped"}, noms


def test_le_detail_rend_les_cles_a_fournir(racine_carte):
    """F3."""
    r = Carte(racine_carte).detail(
        "/state/router[router-name=?]/bgp/neighbor[ip-address=?]", "nokia_sros"
    )
    assert r["noeud"]["cles_a_fournir"] == ["router-name", "ip-address"]


def test_le_detail_accepte_aussi_le_xpath_canonique(racine_carte):
    """Le modèle peut recopier l'une ou l'autre forme ; le punir serait absurde."""
    r = Carte(racine_carte).detail(
        "/nokia-state:state/port[port-id]/transceiver", "nokia_sros"
    )
    assert r["noeud"]["chemin"] == "/state/port[port-id=?]/transceiver"


def test_le_detail_d_un_chemin_inconnu_erre_clairement(racine_carte):
    """F4 — jamais un résultat vide silencieux."""
    with pytest.raises(IndexError_, match="yang_chercher"):
        Carte(racine_carte).detail("/state/inexistant", "nokia_sros")


def test_la_reponse_est_du_json_valide_quelle_que_soit_la_taille(racine_carte):
    """F7."""
    r = Carte(racine_carte).chercher("route", "nokia_sros", limite=50)
    json.dumps(r, ensure_ascii=False)


def test_une_erreur_est_rendue_au_modele_comme_un_fait():
    """Un modèle qui reçoit une exception nue ne sait pas quoi en faire."""
    r = en_erreur(ResolutionError("version illisible"))
    assert r["status"] == "error"
    assert "version illisible" in r["message"]


def test_les_versions_disponibles_sont_listees(racine_carte):
    assert Carte(racine_carte).versions("nokia_sros") == ["24.3.3"]
    assert Carte(racine_carte).plateformes() == {"nokia_sros": ["24.3.3"]}


def test_un_resultat_a_cles_porte_le_rappel_de_substitution(racine_carte):
    """Defaut trouve sur le lab reel : un chemin recopie avec « =? » rendait
    `not_configured`, que le modele lit comme « fonction non activee »."""
    r = Carte(racine_carte).chercher("voisins BGP", "nokia_sros")
    assert any(x["cles"] for x in r["resultats"])
    assert r["action_requise"] is not None
    assert "=?" in r["action_requise"]


def test_sans_cle_aucun_rappel_inutile_n_est_emis(racine_carte):
    """Le rappel ne doit pas devenir du bruit permanent."""
    r = Carte(racine_carte).chercher("zorglub", "nokia_sros")
    assert r["action_requise"] is None
