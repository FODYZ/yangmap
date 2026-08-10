"""Domaine G — usage réel par netlive, contre le containerlab.

Ces tests sont la raison d'être du projet : un chemin bien classé qui serait
refusé par la policy, ou qui ne rendrait rien sur du vrai matériel, ne vaudrait
rien. Ils exigent netlive installé et les tunnels ouverts.

    NETLIVE_POLICIES=/chemin/vers/netlive/policies \
    YANGMAP_LAB_USER=admin YANGMAP_LAB_PASSWORD=admin \
    pytest -m lab
"""

from __future__ import annotations

import os
import socket

import pytest

from yangmap.api import Carte

pytestmark = pytest.mark.lab

netlive_policy = pytest.importorskip("netlive.policy", reason="netlive absent")
pygnmi = pytest.importorskip("pygnmi.client", reason="pygnmi absent")

from netlive.floor import check_floor  # noqa: E402
from netlive.policy import PolicySet  # noqa: E402

# Les deux équipements gNMI joignables : le Nokia du cœur et l'Arista, dont
# gNMI a été activé pour cette campagne.
CIBLES = {
    "nokia_sros": ("127.0.0.1", 57400, "24.3.R3"),
    "arista_eos": ("127.0.0.1", 6030, "4.32.11M"),
}
# Aucun chemin ni identifiant en dur : ce depot est public, et il doit servir
# a d'autres labs que celui de son auteur.
POLICIES = os.environ.get("NETLIVE_POLICIES", "../net-ai-copilot/policies")
UTILISATEUR = os.environ.get("YANGMAP_LAB_USER", "admin")
MOT_DE_PASSE = os.environ.get("YANGMAP_LAB_PASSWORD", "admin")


def _joignable(hote: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((hote, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.fixture(scope="module")
def policies():
    from pathlib import Path
    return PolicySet.load_dir(Path(POLICIES))


@pytest.fixture(scope="module")
def carte():
    return Carte()


def _valuer(chemin: str, valeurs: dict[str, str]) -> str:
    """Remplace les `=?` par de vraies valeurs de clés."""
    for cle, valeur in valeurs.items():
        chemin = chemin.replace(f"[{cle}=?]", f"[{cle}={valeur}]")
    return chemin


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plateforme", sorted(CIBLES))
def test_les_chemins_rendus_sont_acceptes_par_la_policy_netlive(
    carte, policies, plateforme
):
    """G1 — BLOQUANT.

    Un chemin bien classé mais refusé par netlive serait inutilisable. La
    policy netlive autorise les chemins gNMI sauf sous-arbre bloqué : encore
    faut-il que la FORME produite par yangmap soit reconnue comme un chemin.
    """
    _, _, version = CIBLES[plateforme]
    policy = policies.for_platform(plateforme)

    sujets = ["transceiver", "voisins BGP", "etat des interfaces", "table de routage"]
    verifies = 0
    for sujet in sujets:
        for r in carte.chercher(sujet, plateforme, version, limite=5)["resultats"]:
            # Les clés doivent être renseignées : un chemin porteur de `=?`
            # n'est pas destiné à partir tel quel.
            chemin = r["chemin"].replace("=?]", "=X]")
            verdict = policy.evaluate_request(chemin, "gnmi")
            assert verdict.decision.value == "allow", (
                f"{plateforme} : {chemin} refusé — {verdict.reason}"
            )
            verifies += 1
    assert verifies > 10, "échantillon trop maigre pour conclure"


@pytest.mark.parametrize("plateforme", sorted(CIBLES))
def test_aucun_chemin_rendu_ne_franchit_le_plancher(carte, plateforme):
    """G4 — BLOQUANT.

    yangmap n'indexe que des modèles d'état. Aucun chemin rendu ne doit
    ressembler à un verbe d'écriture : si c'était le cas, yangmap deviendrait
    un moyen de suggérer à un modèle ce que le plancher lui interdit.
    """
    _, _, version = CIBLES[plateforme]
    for sujet in ("configure", "commit", "reload", "transceiver", "route"):
        for r in carte.chercher(sujet, plateforme, version, limite=10)["resultats"]:
            resultat = check_floor(r["chemin"])
            assert resultat.allowed, f"{r['chemin']} heurte le plancher : {resultat.reason}"


def test_un_chemin_yangmap_interroge_vraiment_l_arista():
    """G2 — BLOQUANT. Le chemin classé premier doit rendre une donnée."""
    hote, port, version = CIBLES["arista_eos"]
    if not _joignable(hote, port):
        pytest.skip("gNMI Arista injoignable — tunnel 6030 fermé")

    r = Carte().chercher("etat operationnel des interfaces", "arista_eos", version, 1)
    chemin = _valuer(r["resultats"][0]["chemin"], {"name": "Ethernet1"})

    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        reponse = c.get(path=[chemin], encoding="json")
    valeurs = [u.get("val") for n in reponse.get("notification", [])
               for u in n.get("update", [])]
    assert valeurs, f"{chemin} n'a rien rendu"
    assert valeurs[0] in ("UP", "DOWN"), valeurs


def test_le_prefixe_de_module_retire_est_accepte_par_le_materiel():
    """C2 confirmé sur matériel — la forme sans préfixe est la bonne.

    Le xpath pyang porte `openconfig-platform-transceiver:transceiver` en
    milieu de chemin. yangmap le retire ; ce test prouve que la forme retirée
    est acceptée par un vrai équipement, ce qu'aucun raisonnement ne pouvait
    établir.
    """
    hote, port, _ = CIBLES["arista_eos"]
    if not _joignable(hote, port):
        pytest.skip("gNMI Arista injoignable")

    sans = "/interfaces/interface[name=Ethernet1]/state/transceiver"
    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        reponse = c.get(path=[sans], encoding="json")
    assert reponse.get("notification"), "la forme sans préfixe a été refusée"


def test_le_chemin_route_table_referme_le_manque_du_handoff():
    """G3 — le manque documenté au HANDOFF netlive du 2026-08-10.

    « Aucun collecteur nommé pour la table de routage » : yangmap donne le
    chemin, et il rend des compteurs réels sur le lab.
    """
    hote, port, version = CIBLES["nokia_sros"]
    if not _joignable(hote, port):
        pytest.skip("gNMI Nokia injoignable")

    r = Carte().chercher(
        "nombre de routes actives et inactives dans la table de routage",
        "nokia_sros", version, limite=5,
    )
    chemins = [x["chemin"] for x in r["resultats"]]
    assert any("route-table" in c for c in chemins), chemins

    conteneur = "/state/router[router-name=Base]/route-table/unicast/ipv4/statistics"
    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=40) as c:
        reponse = c.get(path=[conteneur], encoding="json")

    valeurs = [u.get("val") for n in reponse.get("notification", [])
               for u in n.get("update", [])]
    assert valeurs, "aucune statistique de routage rendue"
    protocoles = valeurs[0]
    porteurs = {
        k: v for k, v in protocoles.items()
        if isinstance(v, dict) and v.get("available-routes")
    }
    assert porteurs, f"aucun protocole porteur de routes : {list(protocoles)[:8]}"


def test_la_version_vient_de_capabilities_lue_sur_l_equipement():
    """G5 — la boucle complète : l'équipement dit sa version, yangmap s'y règle."""
    hote, port, _ = CIBLES["nokia_sros"]
    if not _joignable(hote, port):
        pytest.skip("gNMI Nokia injoignable")

    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        capacites = c.capabilities()

    modeles = {m["name"]: m.get("version", "") for m in capacites.get("supported_models", [])}
    assert "nokia-state" in modeles, sorted(modeles)[:10]

    # La version annoncée pilote le choix du bundle, sans intervention humaine.
    r = Carte().chercher("transceiver", "nokia_sros", modeles["nokia-state"] or "24.3.R3")
    assert r["resultats"]
    assert r["bundle_servi"]


def test_les_descriptions_d_outils_pesent_moins_que_celles_de_netlive():
    """G7 — l'ajout de yangmap ne doit pas gonfler le contexte de base."""
    from yangmap.api import Carte as _C
    from yangmap.server import create_server

    server = create_server(_C())
    import asyncio
    outils = asyncio.run(server.list_tools())
    total = sum(len(o.description) for o in outils)
    # netlive répète l'inventaire dans chacun de ses 11 outils ; yangmap doit
    # rester très en dessous.
    assert total < 1200, f"{total} caractères pour {len(outils)} outils"
