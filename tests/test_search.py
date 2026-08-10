"""Domaine E — recherche et classement."""

from __future__ import annotations

from yangmap import search


def test_le_transceiver_bat_le_bruit_dwdm(conn):
    """E7 — le premier des quatre échecs documentés en spec §3.4.

    Une recherche par sous-chaîne rendait `dwdm/coherent/rx-optical-snr…` en
    tête. Le sous-arbre transceiver doit passer devant.
    """
    r = search.chercher(conn, "transceiver", limite=3)
    assert r, "aucun résultat"
    assert "/transceiver" in r[0].noeud.chemin
    assert "dwdm" not in r[0].noeud.chemin


def test_la_table_de_routage_bat_le_telechargeur_radius(conn):
    """E7 — le deuxième échec documenté."""
    r = search.chercher(conn, "table de routage", limite=3)
    assert "route-table" in r[0].noeud.chemin
    assert "radius" not in r[0].noeud.chemin


def test_un_terme_absent_du_chemin_mais_present_dans_la_description_est_trouve(conn):
    """E2 — la recherche porte sur la description, pas seulement sur le chemin.

    « inactive » n'apparaît dans AUCUN segment de chemin de l'échantillon ;
    seule la description d'`available-routes` le porte.
    """
    r = search.chercher(conn, "routes inactives", limite=5)
    chemins = [x.noeud.chemin for x in r]
    assert any("available-routes" in c for c in chemins), chemins


def test_un_terme_present_seulement_dans_le_chemin_est_trouve(conn):
    """E2, l'autre sens : `neighbor` n'est dans aucune description utile."""
    r = search.chercher(conn, "neighbor", limite=5)
    assert any("/bgp/neighbor" in x.noeud.chemin for x in r)


def test_un_terme_absurde_ne_rend_rien_plutot_qu_un_chemin_approximatif(conn):
    """E3 — le point le plus important du domaine.

    Rendre « le moins mauvais » chemin serait pire que ne rien rendre : le
    modèle le prendrait pour une réponse.
    """
    assert search.chercher(conn, "zorglub kryptonite", limite=10) == []


def test_une_question_vide_ne_rend_rien(conn):
    assert search.chercher(conn, "", limite=10) == []
    assert search.chercher(conn, "de la le les", limite=10) == []


def test_la_limite_est_respectee_et_plafonnee(conn):
    """E9."""
    assert len(search.chercher(conn, "route", limite=2)) <= 2
    assert len(search.chercher(conn, "route", limite=999)) <= 50


def test_le_score_est_rendu_et_decroissant(conn):
    """E8 — un résultat faible doit être reconnaissable comme tel."""
    r = search.chercher(conn, "transceiver", limite=5)
    scores = [x.score for x in r]
    assert scores == sorted(scores, reverse=True)


def test_le_pluriel_francais_trouve_le_singulier_anglais(conn):
    """« transceivers » doit mordre sur `transceiver`."""
    assert search.chercher(conn, "transceivers", limite=3)


def test_le_lexique_traduit_le_vocabulaire_reseau(conn):
    """« optique » doit atteindre le transceiver, pas seulement `optical`."""
    mots = search.termes("optique")
    assert "transceiver" in mots


def test_la_correspondance_de_segment_tolere_le_pluriel():
    """Le défaut qui faisait rater `in-errors` avec le terme « error »."""
    assert search._correspond("error", "errors")
    assert search._correspond("counter", "counters")
    assert search._correspond("route", "route")


def test_la_correspondance_de_segment_ne_mord_pas_sur_les_mots_courts():
    """« in » ne doit pas faire correspondre `interface`."""
    assert not search._correspond("in", "interface")


def test_neutraliser_un_signal_inconnu_est_refuse():
    """Le banc d'ablation ne doit pas taire une faute de frappe."""
    import pytest
    with pytest.raises(ValueError):
        search.sans_signal(search.DEFAUT, "signal-imaginaire")


def test_le_signal_feuille_a_bien_ete_retire():
    """E10 — un signal sans effet mesurable ne reste pas dans le code."""
    assert "feuille" not in search.Poids.__dataclass_fields__
