"""Construction d'un index depuis un bundle YANG.

Seul module à dépendre de pyang, et il n'est **jamais** importé par le serveur
MCP — c'est ce qui permet au serveur de tourner sans pyang et sans réseau
(cahier A1, A5).

pyang fait tout le travail difficile : `-f flatten` rend directement
`xpath,keyword,type,description`. Mesuré le 2026-08-10 : 0 erreur et moins de
4 secondes sur les trois vendeurs.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from yangmap import index as idx
from yangmap.errors import BundleError
from yangmap.normalize import analyser, mots_de

DRAPEAUX = [
    "-f", "flatten",
    "--flatten-keys-in-xpath",
    "--flatten-type",
    "--flatten-description",
    "--flatten-keyword",
    "--flatten-no-header",
]


@dataclass
class Rapport:
    """Ce que la construction a produit, y compris ce qui a échoué."""

    noeuds: int = 0
    modeles_ok: int = 0
    modeles_en_echec: list[str] = None  # type: ignore[assignment]
    erreurs_pyang: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.modeles_en_echec is None:
            self.modeles_en_echec = []
        if self.erreurs_pyang is None:
            self.erreurs_pyang = []


def _lancer_pyang(
    fichiers: list[Path], chemins_recherche: list[Path]
) -> tuple[str, str, int]:
    commande = [sys.executable, "-m", "pyang", *DRAPEAUX]
    for p in chemins_recherche:
        commande += ["-p", str(p)]
    commande += [str(f) for f in fichiers]

    proc = subprocess.run(commande, capture_output=True, text=True)
    return proc.stdout, proc.stderr, proc.returncode


def _ecrire(conn, lignes: list[dict[str, str]]) -> int:
    """Insère les nœuds et alimente FTS5. Rend le nombre écrit."""
    vus: set[str] = set()
    lot = []
    for l in lignes:
        xpath = (l.get("xpath") or "").strip()
        if not xpath or xpath in vus:
            continue
        vus.add(xpath)
        c = analyser(xpath)
        lot.append((
            xpath, c.gnmi, (l.get("keyword") or "").strip(),
            (l.get("type") or "").strip(), " ".join((l.get("description") or "").split()),
            c.module, ",".join(c.cles), c.profondeur, mots_de(xpath),
        ))

    conn.executemany(
        """INSERT OR IGNORE INTO noeuds
           (xpath, chemin, genre, type, description, module, cles, profondeur, segments)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        lot,
    )
    # Table externe : FTS5 doit être alimentée explicitement.
    conn.execute(
        "INSERT INTO recherche(rowid, segments, description) "
        "SELECT id, segments, description FROM noeuds"
    )
    return len(lot)


def construire(
    fichiers: list[Path],
    chemins_recherche: list[Path],
    destination: Path,
    plateforme: str,
    version: str,
) -> Rapport:
    """Construit un index depuis une liste de modèles YANG.

    Idempotent : la destination est reconstruite depuis rien à chaque appel
    (cahier B5). Un index à moitié reconstruit serait pire que pas d'index.
    """
    if not fichiers:
        raise BundleError("aucun modèle YANG à indexer")

    sortie, erreurs, code = _lancer_pyang(fichiers, chemins_recherche)
    rapport = Rapport()

    if not sortie.strip():
        # pyang n'a rien produit : inutile d'écrire un index vide qui donnerait
        # l'illusion d'une plateforme couverte.
        lignes_err = [l for l in erreurs.splitlines() if l.strip()][:20]
        raise BundleError(
            "pyang n'a produit aucun chemin (code "
            f"{code}) :\n" + "\n".join(lignes_err)
        )

    rapport.erreurs_pyang = [l for l in erreurs.splitlines() if ": error:" in l]
    rapport.modeles_en_echec = sorted(
        {l.split(":")[0] for l in rapport.erreurs_pyang}
    )
    rapport.modeles_ok = len(fichiers) - len(rapport.modeles_en_echec)

    destination = Path(destination)
    if destination.exists():
        destination.unlink()

    lignes = list(csv.DictReader(
        io.StringIO(sortie),
        fieldnames=["xpath", "keyword", "type", "description"],
    ))

    conn = idx.ouvrir(destination, creer=True)
    try:
        rapport.noeuds = _ecrire(conn, lignes)
        idx.ecrire_meta(
            conn,
            plateforme=plateforme,
            version=version,
            noeuds=str(rapport.noeuds),
            modeles=str(len(fichiers)),
        )
        conn.commit()
    finally:
        conn.close()

    return rapport
