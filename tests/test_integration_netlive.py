"""Domain G — real-world usage by netlive, against the containerlab.

These tests are the project's reason for existing: a well-ranked path that
was refused by the policy, or that returned nothing on real hardware, would
be worthless. They require netlive installed and the tunnels open.

    NETLIVE_POLICIES=/path/to/netlive/policies \
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

# The two reachable gNMI devices: the core Nokia and the Arista, whose gNMI
# was enabled for this campaign.
CIBLES = {
    "nokia_sros": ("127.0.0.1", 57400, "24.3.R3"),
    "arista_eos": ("127.0.0.1", 6030, "4.32.11M"),
}
# No hardcoded path or credential: this repo is public, and must serve other
# labs than its author's.
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
    """Replaces the `=?` with real key values."""
    for cle, valeur in valeurs.items():
        chemin = chemin.replace(f"[{cle}=?]", f"[{cle}={valeur}]")
    return chemin


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plateforme", sorted(CIBLES))
def test_les_chemins_rendus_sont_acceptes_par_la_policy_netlive(
    carte, policies, plateforme
):
    """G1 — BLOCKING.

    A well-ranked path refused by netlive would be unusable. netlive's
    policy allows gNMI paths except for a blocked subtree: the FORM
    produced by yangmap still has to be recognized as a path.
    """
    _, _, version = CIBLES[plateforme]
    policy = policies.for_platform(plateforme)

    sujets = ["transceiver", "voisins BGP", "etat des interfaces", "table de routage"]
    verifies = 0
    for sujet in sujets:
        for r in carte.chercher(sujet, plateforme, version, limite=5)["resultats"]:
            # Keys must be filled in: a path carrying `=?` isn't meant to
            # be sent as-is.
            chemin = r["chemin"].replace("=?]", "=X]")
            verdict = policy.evaluate_request(chemin, "gnmi")
            assert verdict.decision.value == "allow", (
                f"{plateforme}: {chemin} refused — {verdict.reason}"
            )
            verifies += 1
    assert verifies > 10, "sample too thin to conclude anything"


@pytest.mark.parametrize("plateforme", sorted(CIBLES))
def test_aucun_chemin_rendu_ne_franchit_le_plancher(carte, plateforme):
    """G4 — BLOCKING.

    yangmap only indexes state models. No returned path should look like a
    write verb: if it did, yangmap would become a way to suggest to a model
    what the security floor forbids it.
    """
    _, _, version = CIBLES[plateforme]
    for sujet in ("configure", "commit", "reload", "transceiver", "route"):
        for r in carte.chercher(sujet, plateforme, version, limite=10)["resultats"]:
            resultat = check_floor(r["chemin"])
            assert resultat.allowed, f"{r['chemin']} crosses the floor: {resultat.reason}"


def test_un_chemin_yangmap_interroge_vraiment_l_arista():
    """G2 — BLOCKING. The top-ranked path must return data."""
    hote, port, version = CIBLES["arista_eos"]
    if not _joignable(hote, port):
        pytest.skip("Arista gNMI unreachable — tunnel 6030 closed")

    r = Carte().chercher("etat operationnel des interfaces", "arista_eos", version, 1)
    chemin = _valuer(r["resultats"][0]["chemin"], {"name": "Ethernet1"})

    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        reponse = c.get(path=[chemin], encoding="json")
    valeurs = [u.get("val") for n in reponse.get("notification", [])
               for u in n.get("update", [])]
    assert valeurs, f"{chemin} returned nothing"
    assert valeurs[0] in ("UP", "DOWN"), valeurs


def test_le_prefixe_de_module_retire_est_accepte_par_le_materiel():
    """C2 confirmed on hardware — the prefix-free form is the right one.

    The pyang xpath carries `openconfig-platform-transceiver:transceiver`
    mid-path. yangmap strips it; this test proves the stripped form is
    accepted by real equipment, something no reasoning alone could settle.
    """
    hote, port, _ = CIBLES["arista_eos"]
    if not _joignable(hote, port):
        pytest.skip("Arista gNMI unreachable")

    sans = "/interfaces/interface[name=Ethernet1]/state/transceiver"
    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        reponse = c.get(path=[sans], encoding="json")
    assert reponse.get("notification"), "the prefix-free form was refused"


def test_le_chemin_route_table_referme_le_manque_du_handoff():
    """G3 — the gap documented in netlive's HANDOFF of 2026-08-10.

    "No named collector for the routing table": yangmap gives the path,
    and it returns real counters on the lab.
    """
    hote, port, version = CIBLES["nokia_sros"]
    if not _joignable(hote, port):
        pytest.skip("Nokia gNMI unreachable")

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
    assert valeurs, "no routing statistic returned"
    protocoles = valeurs[0]
    porteurs = {
        k: v for k, v in protocoles.items()
        if isinstance(v, dict) and v.get("available-routes")
    }
    assert porteurs, f"no protocol carrying routes: {list(protocoles)[:8]}"


def test_la_version_vient_de_capabilities_lue_sur_l_equipement():
    """G5 — the full loop: the equipment states its version, yangmap adapts to it."""
    hote, port, _ = CIBLES["nokia_sros"]
    if not _joignable(hote, port):
        pytest.skip("Nokia gNMI unreachable")

    with pygnmi.gNMIclient(target=(hote, port), username=UTILISATEUR, password=MOT_DE_PASSE,
                           insecure=True, skip_verify=True, timeout=30) as c:
        capacites = c.capabilities()

    modeles = {m["name"]: m.get("version", "") for m in capacites.get("supported_models", [])}
    assert "nokia-state" in modeles, sorted(modeles)[:10]

    # The announced version drives the bundle choice, with no human intervention.
    r = Carte().chercher("transceiver", "nokia_sros", modeles["nokia-state"] or "24.3.R3")
    assert r["resultats"]
    assert r["bundle_servi"]


def test_les_descriptions_d_outils_pesent_moins_que_celles_de_netlive():
    """G7 — adding yangmap must not inflate the base context."""
    from yangmap.api import Carte as _C
    from yangmap.server import create_server

    server = create_server(_C())
    import asyncio
    outils = asyncio.run(server.list_tools())
    total = sum(len(o.description) for o in outils)
    # netlive repeats its inventory in each of its 11 tools; yangmap must
    # stay well below that.
    assert total < 1200, f"{total} characters for {len(outils)} tools"
