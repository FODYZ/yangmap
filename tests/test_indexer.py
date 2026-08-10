"""Domaine B — ingestion et construction de l'index.

Les tests marqués `build` exigent pyang et un bundle téléchargé ; les autres
travaillent sur des modules YANG minuscules écrits à la volée, donc hors ligne.
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
    description "Racine d'etat de l'essai";
    list port {
      key "port-id";
      description "Liste des ports";
      leaf port-id { type string; description "Identifiant du port"; }
      container transceiver {
        description "Enter the transceiver context";
        leaf equipped { type boolean; description "Un transceiver est-il present"; }
      }
    }
  }
}
"""

MODULE_INVALIDE = """
module essai-casse {
  ce n'est pas du YANG
"""


@pytest.fixture
def bundle(tmp_path) -> Path:
    (tmp_path / "essai-etat.yang").write_text(MODULE_VALIDE, encoding="utf-8")
    return tmp_path


def test_un_module_valide_produit_des_chemins_normalises(bundle, tmp_path):
    """B4 — chaque entrée porte les deux formes et ses clés."""
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
    """B5 — reconstruire donne exactement le même nombre d'entrées.

    Sans reconstruction complète, une seconde passe doublerait les lignes FTS5
    et fausserait tous les scores en silence.
    """
    destination = tmp_path / "essai.db"
    args = ([bundle / "essai-etat.yang"], [bundle], destination, "nokia_sros", "1.0.0")
    premier = indexer.construire(*args)
    second = indexer.construire(*args)
    assert premier.noeuds == second.noeuds

    conn = idx.ouvrir(destination)
    try:
        assert idx.compter(conn) == premier.noeuds
        # La table FTS5 ne doit pas non plus avoir double.
        n = conn.execute("SELECT COUNT(*) AS n FROM recherche").fetchone()["n"]
        assert n == premier.noeuds
    finally:
        conn.close()


def test_un_module_casse_est_signale_sans_interrompre_les_autres(bundle, tmp_path):
    """B6 — l'échec d'un modèle ne doit pas emporter l'indexation entière."""
    (bundle / "essai-casse.yang").write_text(MODULE_INVALIDE, encoding="utf-8")
    rapport = indexer.construire(
        [bundle / "essai-etat.yang", bundle / "essai-casse.yang"],
        [bundle], tmp_path / "essai.db", "nokia_sros", "1.0.0",
    )
    assert rapport.noeuds >= 5, "le module valide devait être indexé quand même"
    assert rapport.modeles_en_echec, "l'échec devait être rapporté"


def test_aucun_chemin_produit_leve_une_erreur_plutot_qu_un_index_vide(tmp_path):
    """Un index vide donnerait l'illusion d'une plateforme couverte."""
    (tmp_path / "vide.yang").write_text(MODULE_INVALIDE, encoding="utf-8")
    with pytest.raises(BundleError):
        indexer.construire(
            [tmp_path / "vide.yang"], [tmp_path],
            tmp_path / "x.db", "nokia_sros", "1.0.0",
        )


def test_aucun_fichier_a_indexer_est_refuse(tmp_path):
    with pytest.raises(BundleError, match="aucun modèle"):
        indexer.construire([], [], tmp_path / "x.db", "nokia_sros", "1.0.0")


def test_aucun_csv_intermediaire_ne_subsiste(bundle, tmp_path):
    """B7 — le CSV de pyang est un intermédiaire, pas un artefact."""
    destination = tmp_path / "sortie" / "essai.db"
    indexer.construire(
        [bundle / "essai-etat.yang"], [bundle], destination, "nokia_sros", "1.0.0"
    )
    assert list(destination.parent.glob("*.csv")) == []


# --- contre les bundles réellement téléchargés ------------------------------

@pytest.mark.build
@pytest.mark.parametrize(
    "plateforme,minimum",
    [("nokia_sros", 50_000), ("cisco_iosxe", 10_000), ("arista_eos", 5_000)],
)
def test_les_index_reels_sont_construits_et_fournis(plateforme, minimum):
    """B1, B2, B3 — les trois vendeurs s'indexent réellement."""
    base = RACINE_DEFAUT / "index" / plateforme
    bases = sorted(base.glob("*.db"))
    if not bases:
        pytest.skip(f"aucun index {plateforme} construit")

    conn = idx.ouvrir(bases[-1])
    try:
        n = idx.compter(conn)
        assert n >= minimum, f"{plateforme} : {n} chemins, attendu ≥ {minimum}"
        avec_description = conn.execute(
            "SELECT COUNT(*) AS n FROM noeuds WHERE description != ''"
        ).fetchone()["n"]
        assert avec_description / n > 0.90, "moins de 90 % des nœuds documentés"
    finally:
        conn.close()
