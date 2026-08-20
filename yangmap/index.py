"""The index: SQLite FTS5, with no external dependency.

The standard library's `sqlite3` carries FTS5 **and** `bm25()`. That's what
lets the server run with nothing to install — and therefore meet criterion
A5: start and respond with no network access.

This module doesn't know how to build an index (see `indexer.py`), only how
to read and write one. The separation matters: the MCP server only imports
this one, never pyang.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from yangmap.errors import IndexError_

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    cle TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS noeuds (
    id          INTEGER PRIMARY KEY,
    xpath       TEXT NOT NULL UNIQUE,
    chemin      TEXT NOT NULL,
    genre       TEXT,
    type        TEXT,
    description TEXT,
    module      TEXT,
    cles        TEXT,
    profondeur  INTEGER NOT NULL,
    segments    TEXT NOT NULL,
    -- `etat` (queryable via gNMI Get) or `conf` (configuration tree).
    -- Both are useful, but never for the same question: mixing them in a
    -- single ranking would drown state under config, which is more verbose.
    -- See `search.chercher(arbre=…)`.
    arbre       TEXT NOT NULL DEFAULT 'etat'
);

CREATE INDEX IF NOT EXISTS idx_chemin ON noeuds(chemin);
CREATE INDEX IF NOT EXISTS idx_arbre ON noeuds(arbre);

-- External-content table: text isn't duplicated, FTS5 points at `noeuds`.
CREATE VIRTUAL TABLE IF NOT EXISTS recherche USING fts5(
    segments,
    description,
    content='noeuds',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
"""


@dataclass(frozen=True)
class Noeud:
    xpath: str
    chemin: str
    genre: str
    type: str
    description: str
    module: str | None
    cles: tuple[str, ...]
    profondeur: int
    arbre: str = "etat"


def _colonnes(ligne: sqlite3.Row) -> set[str]:
    return set(ligne.keys())


def _vers_noeud(ligne: sqlite3.Row) -> Noeud:
    return Noeud(
        xpath=ligne["xpath"],
        chemin=ligne["chemin"],
        genre=ligne["genre"] or "",
        type=ligne["type"] or "",
        description=ligne["description"] or "",
        module=ligne["module"],
        cles=tuple(c for c in (ligne["cles"] or "").split(",") if c),
        profondeur=ligne["profondeur"],
        # An index built before the configuration tree was introduced lacks
        # the column. It only carries state: the default is therefore correct,
        # and an older index continues to serve without rebuild.
        arbre=(ligne["arbre"] if "arbre" in _colonnes(ligne) else None) or "etat",
    )


def porte_l_arbre(conn: sqlite3.Connection) -> bool:
    """True if this index distinguishes configuration and state.

    An index older than 2026-08-13 does not. Rather than requiring a rebuild
    — hence a network fetch — queries adapt.
    """
    return any(
        l["name"] == "arbre"
        for l in conn.execute("PRAGMA table_info(noeuds)")
    )


def ouvrir(chemin: Path, creer: bool = False) -> sqlite3.Connection:
    chemin = Path(chemin)
    if not creer and not chemin.exists():
        raise IndexError_(
            f"missing index: {chemin} — run `yangmap build <platform> <version>`"
        )
    if creer:
        chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    if creer:
        conn.executescript(SCHEMA)
    return conn


def ecrire_meta(conn: sqlite3.Connection, **valeurs: str) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO meta (cle, valeur) VALUES (?, ?)",
        [(k, str(v)) for k, v in valeurs.items()],
    )


def lire_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {l["cle"]: l["valeur"] for l in conn.execute("SELECT cle, valeur FROM meta")}


def compter(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM noeuds").fetchone()["n"]


def par_chemin(conn: sqlite3.Connection, chemin: str) -> Noeud | None:
    """Finds a node by its gNMI path, or by its canonical xpath.

    Both are accepted because the model may copy back either one: refusing
    the canonical xpath would punish it for having read the full response.
    """
    for colonne in ("chemin", "xpath"):
        ligne = conn.execute(
            f"SELECT * FROM noeuds WHERE {colonne} = ?", (chemin,)
        ).fetchone()
        if ligne:
            return _vers_noeud(ligne)
    return None


def compter_descendants(conn: sqlite3.Connection, noeud: Noeud) -> int:
    """Number of nodes under this one across its entire subtree.

    This is the missing payload estimate: a `Get` on a container with 3,000
    descendants saturates model context and gets truncated, which is worse
    than a refusal — the model concludes on amputated data without knowing.
    Counting here costs a single query and avoids the round trip.
    """
    prefixe = noeud.xpath.rstrip("/") + "/"
    return conn.execute(
        "SELECT COUNT(*) AS n FROM noeuds WHERE xpath LIKE ?", (prefixe + "%",)
    ).fetchone()["n"]


def enfants(conn: sqlite3.Connection, noeud: Noeud) -> list[Noeud]:
    """**Immediate** children of a node, never its whole subtree.

    Returning the subtree would reproduce the problem yangmap exists to
    solve: drowning the model under thousands of paths.
    """
    prefixe = noeud.xpath.rstrip("/") + "/"
    lignes = conn.execute(
        "SELECT * FROM noeuds WHERE xpath LIKE ? AND profondeur = ? ORDER BY xpath",
        (prefixe + "%", noeud.profondeur + 1),
    )
    return [_vers_noeud(l) for l in lignes]
