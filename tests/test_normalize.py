"""Domaine C — normalisation des chemins."""

from __future__ import annotations

from yangmap.normalize import analyser, mots_de


def test_le_prefixe_de_module_du_premier_segment_est_retire():
    """C1 — `/nokia-state:state/...` devient `/state/...`."""
    c = analyser("/nokia-state:state/router[router-name]/interface")
    assert c.gnmi.startswith("/state/router")
    assert c.module == "nokia-state"


def test_un_prefixe_en_milieu_de_chemin_est_retire_mais_pas_perdu():
    """C2 — cas OpenConfig.

    Le chemin gNMI conventionnel ne porte pas les préfixes de module, mais le
    xpath canonique les conserve : rien n'est perdu, et un consommateur qui
    aurait besoin de la forme qualifiée peut la reconstruire.
    """
    x = "/openconfig-interfaces:interfaces/interface[name]/state/openconfig-platform-transceiver:transceiver"
    c = analyser(x)
    assert c.gnmi == "/interfaces/interface[name=?]/state/transceiver"
    assert c.xpath == x, "le xpath canonique doit rester intact"


def test_les_cles_attendent_une_valeur():
    """C3 — `[router-name]` devient `[router-name=?]`."""
    c = analyser("/nokia-state:state/router[router-name]/bgp/neighbor[ip-address]")
    assert c.gnmi == "/state/router[router-name=?]/bgp/neighbor[ip-address=?]"
    assert c.cles == ("router-name", "ip-address")


def test_une_liste_a_cles_multiples_les_conserve_toutes():
    """C4 — le cas réel `[ip-address][mac-address][pppoe-session-id]`."""
    c = analyser(
        "/nokia-state:state/router[router-name]/igmp/"
        "host[ip-address][mac-address][pppoe-session-id]"
    )
    assert c.cles == ("router-name", "ip-address", "mac-address", "pppoe-session-id")
    assert "[ip-address=?][mac-address=?][pppoe-session-id=?]" in c.gnmi


def test_une_cle_deja_valuee_est_laissee_intacte():
    """Un appelant qui sait ce qu'il veut ne doit pas être corrigé."""
    c = analyser("/state/router[router-name=Base]/interface")
    assert c.gnmi == "/state/router[router-name=Base]/interface"


def test_la_profondeur_compte_les_segments():
    assert analyser("/a/b/c").profondeur == 3
    assert analyser("/nokia-state:state").profondeur == 1


def test_la_normalisation_est_pure():
    """C6 — mêmes entrées, mêmes sorties, sans état."""
    x = "/nokia-state:state/router[router-name]/route-table"
    assert analyser(x) == analyser(x)


def test_les_segments_sont_eclates_en_mots_pour_l_indexation():
    """`route-table` doit être trouvable par « route » comme par « table »."""
    mots = mots_de("/nokia-state:state/router[router-name]/route-table").split()
    assert "route-table" in mots
    assert "route" in mots
    assert "table" in mots


def test_un_chemin_racine_ne_casse_pas():
    c = analyser("/")
    assert c.gnmi == "/"
    assert c.profondeur == 0
