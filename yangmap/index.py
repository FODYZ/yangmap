"""L'index : SQLite FTS5, sans aucune dépendance externe.

`sqlite3` de la bibliothèque standard porte FTS5 **et** `bm25()`. C'est ce qui
permet au serveur de tourner sans rien installer — et donc de tenir le critère
A5 : démarrer et répondre sans accès réseau.

Ce module ne sait pas construire un index (voir `indexer.py`), seulement le
lire et l'écrire. La séparation compte : le serveur MCP n'importe que celui-ci,
jamais pyang.
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
    segments    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chemin ON noeuds(chemin);

-- Table externe : le texte n'est pas dupliqué, FTS5 pointe sur `noeuds`.
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
    )


def ouvrir(chemin: Path, creer: bool = False) -> sqlite3.Connection:
    chemin = Path(chemin)
    if not creer and not chemin.exists():
        raise IndexError_(
            f"index absent : {chemin} — jouer `yangmap build <plateforme> <version>`"
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
    """Retrouve un nœud par son chemin gNMI, ou par son xpath canonique.

    Les deux sont acceptés parce que le modèle peut recopier l'un ou l'autre :
    refuser le xpath canonique le punirait d'avoir lu la réponse en entier.
    """
    for colonne in ("chemin", "xpath"):
        ligne = conn.execute(
            f"SELECT * FROM noeuds WHERE {colonne} = ?", (chemin,)
        ).fetchone()
        if ligne:
            return _vers_noeud(ligne)
    return None


def enfants(conn: sqlite3.Connection, noeud: Noeud) -> list[Noeud]:
    """Enfants **immédiats** d'un nœud, jamais son sous-arbre entier.

    Rendre le sous-arbre reproduirait le problème que yangmap existe pour
    résoudre : noyer le modèle sous des milliers de chemins.
    """
    prefixe = noeud.xpath.rstrip("/") + "/"
    lignes = conn.execute(
        "SELECT * FROM noeuds WHERE xpath LIKE ? AND profondeur = ? ORDER BY xpath",
        (prefixe + "%", noeud.profondeur + 1),
    )
    return [_vers_noeud(l) for l in lignes]
