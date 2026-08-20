"""`yang_valider` — the three ways a path fails invisibly.

Every test covers a case whose ground truth is known, recorded on the lab
or vendor YANG, never invented for the occasion.
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
# Path splitting
# ---------------------------------------------------------------------------

def test_une_valeur_de_cle_peut_contenir_des_slashs():
    """`[port-id=1/1/c1]` is THE key format Nokia imposes everywhere.

    A naive `split("/")` cut it in three, and the tool answered "unknown
    segment: 1" — a false negative on the exact path cited in netlive tool
    descriptions. Found by testing the tool against a real index.
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
# The three failures
# ---------------------------------------------------------------------------

def test_un_segment_inconnu_nomme_le_fautif_et_propose_ses_freres(conn):
    """The `export-policy` case on netlab, verbatim.

    `export-policy` is the classic CLI name; in MD-CLI it does not exist,
    but `export` does. A dry "unknown path" would only invite more guessing
    — which occurred four times.
    """
    v = valider(conn, "/configure/router[router-name=Base]/bgp/group[group-name=transit]/export-policy")

    assert v.verdict == "inexistant"
    assert not v.interrogeable
    assert "export-policy" in v.motif
    assert "export" in v.suggestions
    # And it indicates how far the path held: this is what allows recovery.
    assert v.chemin_valide.endswith("/bgp/group[group-name=?]")


def test_une_cle_non_renseignee_est_refusee_avant_tout_contact(conn):
    """A template key yields an EMPTY response, mistaken for 'not configured'.

    This is the severe defect found on the lab on 2026-08-10: an omitted key
    became "this feature is not enabled", confidently wrong.
    """
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor[ip-address=?]")

    assert v.verdict == "cle_manquante"
    assert not v.interrogeable
    assert "ip-address" in v.cles_manquantes
    assert "vide" in v.motif.lower()


def test_une_cle_absente_du_chemin_vaut_toutes_les_instances(conn):
    """Counter-test, and corrected false positive.

    `[ip-address=?]` is a template copied verbatim, which equipment
    translates to an empty response. A simply ABSENT key is different: in
    gNMI it represents "all instances", netlive already allows it, and
    several production collectors depend on it. Confusing them rejected
    working collectors — caught when screening the whole catalog.
    """
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor")

    assert v.verdict != "cle_manquante"
    assert v.interrogeable
    # Unbounded nevertheless: this is a volume warning, not a rejection.
    assert v.instances_inconnues


def test_un_chemin_complet_sur_une_feuille_est_sur(conn):
    v = valider(conn, "/state/router[router-name=Base]/bgp/neighbor[ip-address=10.0.0.9]/session-state")

    assert v.verdict == "sur"
    assert v.interrogeable
    assert v.noeud is not None and v.noeud.genre == "leaf"


def test_le_chemin_recommande_pour_les_routes_ne_declenche_pas_d_alerte(conn):
    """Counter-test: the routing table aggregate must pass.

    A volume threshold that rejected the path recommended by documentation
    would be unusable — the operator would learn to ignore the tool.
    """
    v = valider(conn, "/state/router[router-name=Base]/route-table/unicast/ipv4/statistics")
    assert v.verdict == "sur"


def test_un_conteneur_sur_liste_jokerisee_est_declare_volumineux(conn, tmp_path):
    """The `interfaces` defect: whole container instead of leaves.

    Measured on core1: 17,583 characters for 5 interfaces, vs 573 when
    narrowed to useful leaves. The subtree has 518 nodes in nokia-state
    24.3.R3 — hence the ~6.7 characters per descendant per instance ratio.
    """
    # The minimal index does not hold 518 descendants: we synthesize enough to
    # cross the threshold, preserving the real path structure.
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
    # A warning, not a rejection: sometimes you really want the whole tree.
    assert v.interrogeable
    assert v.instances_non_bornees if hasattr(v, "instances_non_bornees") else v.instances_inconnues
    assert v.octets_estimes == int(v.descendants * OCTETS_PAR_DESCENDANT)


def test_la_meme_liste_avec_ses_cles_renseignees_reste_bornee(conn):
    """A real key bounds the instance count — the threshold must use it.

    Otherwise the tool would warn on `interface[interface-name=to-core1]`,
    which returns only one entry.
    """
    v = valider(conn, "/state/port[port-id=1/1/c1]/transceiver")
    assert v.verdict == "sur"
    assert not v.instances_inconnues


# ---------------------------------------------------------------------------
# The two trees
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
    assert trouves, "configuration tree must answer on this topic"
    assert all(r.noeud.chemin.startswith("/configure") for r in trouves)


def test_un_arbre_inconnu_est_refuse_sans_repli(conn):
    from yangmap import search

    with pytest.raises(ValueError):
        search.chercher(conn, "bgp", arbre="configuration")
