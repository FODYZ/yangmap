"""Fixtures partagées : un index minuscule, construit sans pyang ni réseau.

La suite doit tourner hors ligne et sans matériel (cahier H5). Les tests qui
exigent un vrai bundle portent la marque `build`, ceux qui exigent le lab la
marque `lab`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yangmap import index as idx
from yangmap.normalize import analyser, arbre_de, mots_de

# Extraits réels de `nokia-state` 24.3.3 et d'OpenConfig : les descriptions
# sont recopiées telles quelles, parce qu'un jeu d'essai inventé ne prouverait
# rien sur le classement.
ECHANTILLON = [
    # Les nœuds intermédiaires font partie de l'échantillon : un index réel
    # les porte tous (pyang émet chaque conteneur et chaque liste), et un
    # arbre troué ne prouverait rien sur `valider`, qui descend segment par
    # segment pour pouvoir dire OÙ un chemin casse.
    ("/nokia-state:state", "container", "", "Enter the state context"),
    ("/nokia-state:state/port[port-id]", "list", "", "Enter the port list instance"),
    ("/nokia-state:state/port[port-id]/dwdm", "container", "", "Enter the dwdm context"),
    ("/nokia-state:state/port[port-id]/dwdm/coherent", "container", "",
     "Enter the coherent context"),
    ("/nokia-state:state/router[router-name]", "list", "",
     "Enter the router list instance"),
    ("/nokia-state:state/router[router-name]/bgp", "container", "",
     "Enter the bgp context"),
    ("/nokia-state:state/router[router-name]/route-table", "container", "",
     "Enter the route-table context"),
    ("/nokia-state:state/router[router-name]/route-table/unicast", "container", "",
     "Enter the unicast context"),
    ("/nokia-state:state/router[router-name]/route-table/unicast/ipv4", "container", "",
     "Enter the ipv4 context"),
    ("/nokia-state:state/router[router-name]/route-table/unicast/ipv4/statistics",
     "container", "", "Enter the statistics context"),
    ("/nokia-state:state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate",
     "container", "", "Enter the aggregate context"),
    ("/nokia-state:state/radius", "container", "", "Enter the radius context"),
    ("/nokia-state:state/radius/route-downloader[name]", "list", "",
     "Enter the route-downloader list instance"),
    ("/nokia-state:state/radius/route-downloader[name]/statistics", "container", "",
     "Enter the statistics context"),
    ("/nokia-conf:configure", "container", "", "Configure system configuration"),
    ("/nokia-conf:configure/router[router-name]", "list", "",
     "Enter the router list instance"),
    ("/nokia-conf:configure/router[router-name]/bgp", "container", "",
     "Enter the bgp context"),
    # --- Feuilles et sous-arbres réels ---
    ("/nokia-state:state/port[port-id]/transceiver", "container", "",
     "Enter the transceiver context"),
    ("/nokia-state:state/port[port-id]/transceiver/type", "leaf", "enumeration",
     "Indicates the type of transceiver for the port."),
    ("/nokia-state:state/port[port-id]/transceiver/equipped", "leaf", "boolean",
     "Indicates whether or not a transceiver is equipped in the port."),
    ("/nokia-state:state/port[port-id]/dwdm/coherent/rx-optical-snr-x-polarization",
     "leaf", "decimal64", "Receive optical signal to noise ratio."),
    ("/nokia-state:state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/active-routes",
     "leaf", "uint32", "Count of routes of a routing protocol active in the FIB."),
    ("/nokia-state:state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/available-routes",
     "leaf", "uint32",
     "Count of routes of a routing protocol, both active in the FIB and inactive in the RIB."),
    ("/nokia-state:state/radius/route-downloader[name]/statistics/routes-received-count",
     "leaf", "uint32", "Number of routes received from the RADIUS server."),
    ("/nokia-state:state/router[router-name]/bgp/neighbor[ip-address]", "list", "",
     "Enter the neighbor list instance"),
    ("/nokia-state:state/router[router-name]/bgp/neighbor[ip-address]/session-state",
     "leaf", "enumeration", "The current state of the BGP session."),
    # --- Arbre de CONFIGURATION (nokia-conf) ---
    # Le sous-arbre exact qui a coûté plusieurs sessions sur `netlab` : quatre
    # recherches yangmap n'avaient rien rendu, non pas parce que le chemin
    # manque au modèle, mais parce qu'aucun `/configure` n'était indexé.
    ("/nokia-conf:configure/router[router-name]/bgp/group[group-name]", "list", "",
     "Enter the group list instance"),
    ("/nokia-conf:configure/router[router-name]/bgp/group[group-name]/export",
     "container", "", "Enable the export context"),
    ("/nokia-conf:configure/router[router-name]/bgp/group[group-name]/export/policy",
     "leaf-list", "union", "BGP export policy name"),
    ("/nokia-conf:configure/router[router-name]/bgp/group[group-name]/import",
     "container", "", "Enable the import context"),
    ("/nokia-conf:configure/router[router-name]/bgp/group[group-name]/import/policy",
     "leaf-list", "union", "BGP import policy name"),
]


def _peupler(chemin: Path, entrees) -> Path:
    conn = idx.ouvrir(chemin, creer=True)
    lot = []
    for xpath, genre, type_, description in entrees:
        c = analyser(xpath)
        lot.append((xpath, c.gnmi, genre, type_, description, c.module,
                    ",".join(c.cles), c.profondeur, mots_de(xpath), arbre_de(xpath)))
    conn.executemany(
        """INSERT OR IGNORE INTO noeuds
           (xpath, chemin, genre, type, description, module, cles, profondeur,
            segments, arbre)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        lot,
    )
    conn.execute(
        "INSERT INTO recherche(rowid, segments, description) "
        "SELECT id, segments, description FROM noeuds"
    )
    idx.ecrire_meta(conn, plateforme="nokia_sros", version="24.3.3")
    conn.commit()
    conn.close()
    return chemin


@pytest.fixture
def index_minimal(tmp_path) -> Path:
    return _peupler(tmp_path / "mini.db", ECHANTILLON)


@pytest.fixture
def conn(index_minimal):
    c = idx.ouvrir(index_minimal)
    yield c
    c.close()


@pytest.fixture
def racine_carte(tmp_path) -> Path:
    """Une arborescence `~/.yangmap` complète, avec un index Nokia."""
    _peupler(tmp_path / "index" / "nokia_sros" / "24.3.3.db", ECHANTILLON)
    return tmp_path
