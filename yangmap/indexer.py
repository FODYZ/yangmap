"""Building an index from a YANG bundle.

The only module that depends on pyang, and it is **never** imported by the
MCP server — that's what lets the server run without pyang and without
network access (criteria A1, A5).

pyang does all the hard work: `-f flatten` directly returns
`xpath,keyword,type,description`. Measured on 2026-08-10: 0 errors and under
4 seconds across all three vendors.
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
    """What the build produced, including what failed."""

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
    """Inserts the nodes and feeds FTS5. Returns the number written."""
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
    # External-content table: FTS5 must be fed explicitly.
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
    """Builds an index from a list of YANG models.

    Idempotent: the destination is rebuilt from nothing on every call
    (criterion B5). A half-rebuilt index would be worse than no index.
    """
    if not fichiers:
        raise BundleError("no YANG model to index")

    sortie, erreurs, code = _lancer_pyang(fichiers, chemins_recherche)
    rapport = Rapport()

    if not sortie.strip():
        # pyang produced nothing: writing an empty index would give the
        # illusion of a covered platform.
        lignes_err = [l for l in erreurs.splitlines() if l.strip()][:20]
        raise BundleError(
            "pyang produced no path (code "
            f"{code}):\n" + "\n".join(lignes_err)
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
