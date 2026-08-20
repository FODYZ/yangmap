"""Domain B — ingestion and index construction.

Tests marked `build` require pyang and a downloaded bundle; the others work
on tiny YANG modules written on the fly, so they run offline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yangmap import index as idx
from yangmap import indexer
from yangmap.api import RACINE_DEFAUT
from yangmap.errors import BundleError

pyang = pytest.importorskip("pyang", reason="pyang absent (extra `build`)")

MODULE_VALIDE = """
module essai-etat {
  namespace "urn:essai:etat";
  prefix ee;
  container state {
    description "Test state root";
    list port {
      key "port-id";
      description "List of ports";
      leaf port-id { type string; description "Port identifier"; }
      container transceiver {
        description "Enter the transceiver context";
        leaf equipped { type boolean; description "Is a transceiver present"; }
      }
    }
  }
}
"""

MODULE_INVALIDE = """
module essai-casse {
  this is not YANG
"""


@pytest.fixture
def bundle(tmp_path) -> Path:
    (tmp_path / "essai-etat.yang").write_text(MODULE_VALIDE, encoding="utf-8")
    return tmp_path


def test_un_module_valide_produit_des_chemins_normalises(bundle, tmp_path):
    """B4 — every entry carries both forms and its keys."""
    destination = tmp_path / "sortie" / "essai.db"
    rapport = indexer.construire(
        [bundle / "essai-etat.yang"], [bundle], destination, "nokia_sros", "1.0.0"
    )
    assert rapport.noeuds >= 5
    assert rapport.erreurs_pyang == []

    conn = idx.ouvrir(destination)
    try:
        noeud = idx.par_chemin(conn, "/state/port[port-id=?]/transceiver")
        assert noeud is not None
        assert noeud.xpath.startswith("/essai-etat:state")
        assert noeud.cles == ("port-id",)
        assert noeud.genre == "container"
        meta = idx.lire_meta(conn)
        assert meta["plateforme"] == "nokia_sros" and meta["version"] == "1.0.0"
    finally:
        conn.close()


def test_la_construction_est_idempotente(bundle, tmp_path):
    """B5 — rebuilding gives exactly the same number of entries.

    Without a full rebuild, a second pass would double the FTS5 rows and
    silently skew every score.
    """
    destination = tmp_path / "essai.db"
    args = ([bundle / "essai-etat.yang"], [bundle], destination, "nokia_sros", "1.0.0")
    premier = indexer.construire(*args)
    second = indexer.construire(*args)
    assert premier.noeuds == second.noeuds

    conn = idx.ouvrir(destination)
    try:
        assert idx.compter(conn) == premier.noeuds
        # The FTS5 table must not be doubled either.
        n = conn.execute("SELECT COUNT(*) AS n FROM recherche").fetchone()["n"]
        assert n == premier.noeuds
    finally:
        conn.close()


def test_un_module_casse_est_signale_sans_interrompre_les_autres(bundle, tmp_path):
    """B6 — one model's failure must not take down the whole indexing run."""
    (bundle / "essai-casse.yang").write_text(MODULE_INVALIDE, encoding="utf-8")
    rapport = indexer.construire(
        [bundle / "essai-etat.yang", bundle / "essai-casse.yang"],
        [bundle], tmp_path / "essai.db", "nokia_sros", "1.0.0",
    )
    assert rapport.noeuds >= 5, "the valid model should have been indexed anyway"
    assert rapport.modeles_en_echec, "the failure should have been reported"


def test_aucun_chemin_produit_leve_une_erreur_plutot_qu_un_index_vide(tmp_path):
    """An empty index would give the illusion of a covered platform."""
    (tmp_path / "vide.yang").write_text(MODULE_INVALIDE, encoding="utf-8")
    with pytest.raises(BundleError):
        indexer.construire(
            [tmp_path / "vide.yang"], [tmp_path],
            tmp_path / "x.db", "nokia_sros", "1.0.0",
        )


def test_aucun_fichier_a_indexer_est_refuse(tmp_path):
    with pytest.raises(BundleError, match="no YANG model"):
        indexer.construire([], [], tmp_path / "x.db", "nokia_sros", "1.0.0")


def test_aucun_csv_intermediaire_ne_subsiste(bundle, tmp_path):
    """B7 — pyang's CSV is an intermediate, not an artifact."""
    destination = tmp_path / "sortie" / "essai.db"
    indexer.construire(
        [bundle / "essai-etat.yang"], [bundle], destination, "nokia_sros", "1.0.0"
    )
    assert list(destination.parent.glob("*.csv")) == []


# --- against actually downloaded bundles ------------------------------------

@pytest.mark.build
@pytest.mark.parametrize(
    "plateforme,minimum",
    [("nokia_sros", 50_000), ("cisco_iosxe", 10_000), ("arista_eos", 5_000)],
)
def test_les_index_reels_sont_construits_et_fournis(plateforme, minimum):
    """B1, B2, B3 — all three vendors actually index."""
    base = RACINE_DEFAUT / "index" / plateforme
    bases = sorted(base.glob("*.db"))
    if not bases:
        pytest.skip(f"no {plateforme} index built")

    conn = idx.ouvrir(bases[-1])
    try:
        n = idx.compter(conn)
        assert n >= minimum, f"{plateforme}: {n} paths, expected >= {minimum}"
        avec_description = conn.execute(
            "SELECT COUNT(*) AS n FROM noeuds WHERE description != ''"
        ).fetchone()["n"]
        assert avec_description / n > 0.90, "fewer than 90% of nodes documented"
    finally:
        conn.close()
