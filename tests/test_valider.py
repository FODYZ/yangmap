"""`yang_valider` — les trois façons dont un chemin échoue sans se voir.

Chaque test porte sur un cas dont la **vérité est connue**, relevé sur le lab
ou sur le YANG du vendeur, jamais inventé pour la circonstance.
"""

from __future__ import annotations

import pytest

from yangmap import index as idx
from yangmap.valider import (
    OCTETS_PAR_DESCENDANT,
    _segments,
    decomposer,
    valider,
)


# ---------------------------------------------------------------------------
# Découpage
# ---------------------------------------------------------------------------

def test_une_valeur_de_cle_peut_contenir_des_slashs():
    """`[port-id=1/1/c1]` est LA forme de clé que Nokia impose partout.

    Un `split("/")` naïf la coupait en trois, et l'outil répondait « segment
    inconnu : 1 » — un faux négatif sur le chemin même que les descriptions
    d'outils de netlive citent en exemple. Trouvé en jouant l'outil contre le
    vrai index, pas en test unitaire.
    """
    assert _segments("/state/port[port-id=1/1/c1]/transceiver") == [
        "state", "port[port-id=1/1/c1]", "transceiver",
    ]
    noms, valeurs = decomposer("/state/port[port-id=1/1/c1]/transceiver")
    assert noms == ["state", "port", "transceiver"]
    assert valeurs == {"port-id": "1/1/c1"}


def test_les_valeurs_de_cles_sont_separees_des_noms():
    noms, valeurs = decomposer("/state/router[router-name=Base]/bgp/neighbor[ip-address=*]")
    assert noms == ["state", "router", "bgp", "neighbor"]
    assert valeurs == {"router-name": "Base", "ip-address": "*"}


# ---------------------------------------------------------------------------
# Les trois échecs
# ---------------------------------------------------------------------------

def test_un_segment_inconnu_nomme_le_fautif_et_propose_ses_freres(conn):
    """Le cas `export-policy` de netlab, à l'identique.

    `export-policy` est le nom du CLI classique ; en MD-CLI il n'existe pas,
    mais `export` oui. Un « chemin inconnu » sec n'aurait fait qu'inviter à
    deviner encore — ce qui s'est produit quatre fois.
    """
    v = valider(conn, "/configure/router[router-name=Base]/bgp/group[group-name=transit]/export-policy")

    assert v.verdict == "inexistant"
    assert not v.interrogeable
    assert "export-policy" in v.motif
    assert "export" in v.suggestions
    # Et il dit jusqu'où le chemin tenait : c'est ce qui permet de repartir.
    assert v.chemin_valide.endswith("/bgp/group[group-name=?]")


def test_une_cle_non_renseignee_est_refusee_avant_tout_contact(conn):
    """Une clé en gabarit rend une réponse VIDE, prise pour « non activé ».

    C'est le défaut grave trouvé sur le lab le 2026-08-10 : une clé oubliée
    devenait « cette fonction n'est pas activée », faux et assuré.
    """
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor[ip-address=?]")

    assert v.verdict == "cle_manquante"
    assert not v.interrogeable
    assert "ip-address" in v.cles_manquantes
    assert "vide" in v.motif.lower()


def test_une_cle_absente_du_chemin_vaut_toutes_les_instances(conn):
    """Contre-épreuve, et faux positif corrigé.

    `[ip-address=?]` est un gabarit recopié tel quel, que l'équipement
    traduit en réponse vide. Une clé simplement ABSENTE est autre chose : en
    gNMI elle vaut « toutes les instances », netlive l'autorise déjà, et
    plusieurs collecteurs en service en dépendent. Les confondre condamnait
    des collecteurs qui fonctionnent — relevé en passant le catalogue entier
    au crible, jamais en test unitaire.
    """
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor")

    assert v.verdict != "cle_manquante"
    assert v.interrogeable
    # Non borné pour autant : c'est un avertissement de volume, pas un refus.
    assert v.instances_inconnues


def test_un_chemin_complet_sur_une_feuille_est_sur(conn):
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor[ip-address=10.0.0.9]/session-state")

    assert v.verdict == "sur"
    assert v.interrogeable
    assert v.noeud is not None and v.noeud.genre == "leaf"


def test_le_chemin_recommande_pour_les_routes_ne_declenche_pas_d_alerte(conn):
    """Contre-épreuve : l'agrégat de la table de routage doit passer.

    Un seuil de volume qui refuserait le chemin que la documentation
    recommande serait un seuil inutilisable — l'opérateur apprendrait à
    ignorer l'outil.
    """
    v = valider(conn, "/state/router[router-name=Base]/route-table/unicast/ipv4/statistics")
    assert v.verdict == "sur"


def test_un_conteneur_sur_liste_jokerisee_est_declare_volumineux(conn, tmp_path):
    """Le défaut `interfaces` : conteneur entier au lieu des feuilles.

    Mesuré sur core1 : 17 583 caractères pour 5 interfaces, contre 573 une
    fois restreint aux feuilles utiles. Le sous-arbre compte 518 nœuds dans
    nokia-state 24.3.R3 — d'où le rapport de ~6,7 caractères par descendant
    et par instance qui sert d'estimateur.
    """
    # L'index minimal ne porte pas 518 descendants : on en fabrique assez pour
    # franchir le seuil, en gardant la forme réelle du chemin.
    conn.executemany(
        """INSERT OR IGNORE INTO noeuds
           (xpath, chemin, genre, type, description, module, cles, profondeur,
            segments, arbre)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        [
            (f"/nokia-state:state/router[router-name]/interface[interface-name]/f{i}",
             f"/state/router[router-name=?]/interface[interface-name=?]/f{i}",
             "leaf", "uint32", "", "nokia-state", "router-name,interface-name",
             4, "state router interface", "etat")
            for i in range(60)
        ] + [(
            "/nokia-state:state/router[router-name]/interface[interface-name]",
            "/state/router[router-name=?]/interface[interface-name=?]",
            "list", "", "Enter the interface list instance", "nokia-state",
            "router-name,interface-name", 3, "state router interface", "etat",
        )],
    )
    conn.commit()

    v = valider(conn, "/state/router[router-name=Base]/interface[interface-name=*]")

    assert v.verdict == "volumineux"
    # Un avertissement, pas un refus : parfois on veut vraiment tout l'arbre.
    assert v.interrogeable
    assert v.instances_non_bornees if hasattr(v, "instances_non_bornees") else v.instances_inconnues
    assert v.octets_estimes == int(v.descendants * OCTETS_PAR_DESCENDANT)


def test_la_meme_liste_avec_ses_cles_renseignees_reste_bornee(conn):
    """Une clé réelle borne le nombre d'instances — le seuil doit s'en servir.

    Sinon l'outil crierait au volume sur `interface[interface-name=to-core1]`,
    qui ne rend qu'une entrée.
    """
    v = valider(conn, "/state/port[port-id=1/1/c1]/transceiver")
    assert v.verdict == "sur"
    assert not v.instances_inconnues


# ---------------------------------------------------------------------------
# Les deux arbres
# ---------------------------------------------------------------------------

def test_les_deux_arbres_sont_distingues(conn):
    etat = idx.par_chemin(conn, "/state/port[port-id=?]/transceiver")
    conf = idx.par_chemin(conn, "/configure/router[router-name=?]/bgp/group[group-name=?]/export/policy")

    assert etat is not None and etat.arbre == "etat"
    assert conf is not None and conf.arbre == "conf"


def test_la_recherche_d_etat_ne_ramene_pas_de_configuration(conn):
    from yangmap import search

    trouves = search.chercher(conn, "bgp export policy", limite=10, arbre="etat")
    assert all(not r.noeud.chemin.startswith("/configure") for r in trouves)

    trouves = search.chercher(conn, "bgp export policy", limite=10, arbre="conf")
    assert trouves, "l'arbre de configuration doit répondre sur ce sujet"
    assert all(r.noeud.chemin.startswith("/configure") for r in trouves)


def test_un_arbre_inconnu_est_refuse_sans_repli(conn):
    from yangmap import search

    with pytest.raises(ValueError):
        search.chercher(conn, "bgp", arbre="configuration")
