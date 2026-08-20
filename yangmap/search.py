"""Search and ranking — the only hard part of the project.

The weights below aren't intuitions: they're tuned against the golden set
(`goldenset/`), and any signal that doesn't improve one of its entries must
be removed (criterion E10).

The baseline to beat is documented and measured: a substring search returns
`/state/port[]/dwdm/coherent/rx-optical-snr-x-polarization` for "transceiver"
and `/state/radius/route-downloader[]/…` for "routing table". The correct
data is in the index in both cases; only the order is wrong.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace

from yangmap.index import Noeud, _vers_noeud

# ---------------------------------------------------------------------------
# Query preparation
# ---------------------------------------------------------------------------

# Vendor descriptions are in English; questions arrive in French. This
# lexicon is deliberately short and purely networking-focused: it translates
# what an engineer types, not the French language in general. Every entry
# must be justified by a golden-set question.
#
# An entry can return **several** words: "optique" indifferently denotes
# optical, transceiver, and SFF depending on the vendor, and emitting only
# one of them would miss the other two.
#
# The keys are intentionally left in French: this is the actual translation
# table that lets a French-speaking engineer's question reach English vendor
# vocabulary, and it's what the golden set (`goldenset/golden.yaml`) exercises.
LEXIQUE: dict[str, str] = {
    "routage": "routing route",
    "chemin": "path route",
    "voisin": "neighbor",
    "voisinage": "neighbor adjacency",
    "adjacence": "adjacency",
    "optique": "optical transceiver sff",
    "temperature": "temperature",
    "puissance": "power",
    "emission": "tx transmit",
    "reception": "rx receive",
    "abonne": "subscriber",
    "etat": "state status",
    "operationnel": "oper operational",
    "actif": "active",
    "active": "active",
    "inactif": "inactive",
    "inactive": "inactive",
    "erreur": "error",
    "rejete": "rejected dropped",
    "rejet": "dropped discard",
    "perdu": "dropped lost",
    "compteur": "counter statistics",
    "statistique": "statistics",
    "paquet": "packet",
    "utilisation": "usage utilization",
    "charge": "usage load",
    "processeur": "cpu",
    "memoire": "memory",
    "carte": "card",
    "chassis": "chassis",
    "alimentation": "power-supply",
    "ventilateur": "fan",
    "temps": "uptime time",
    "etiquette": "label",
    "voie": "channel",
    "debit": "rate bandwidth",
}

# Words that add nothing to selection and dilute the score. Kept bilingual
# (French + English) since questions can arrive in either language.
VIDES = frozenset("""
a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui
ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui
sa se ses son sur ta te tes toi ton tu un une vos votre vous y est sont quel
quelle quels quelles quoi comment pourquoi combien
the of for and or is are to in on with what which how
""".split())

_MOT = re.compile(r"[a-z0-9]+", re.I)


def _racine(mot: str) -> str:
    """French plural crudely stripped, so the FTS5 prefix can bite.

    "actives" isn't a prefix of "active": without this shortening, a
    plural question would never find a singular description.
    """
    if len(mot) > 4 and mot.endswith(("s", "x")):
        return mot[:-1]
    return mot


def termes(sujet: str) -> list[str]:
    """Natural-language question ⟶ search terms, deduplicated."""
    sortie: list[str] = []
    for brut in _MOT.findall((sujet or "").lower()):
        if brut in VIDES or len(brut) < 2:
            continue
        candidats = [_racine(brut)]
        for cle in (brut, _racine(brut)):
            if cle in LEXIQUE:
                candidats += LEXIQUE[cle].split()
        for mot in candidats:
            if mot and mot not in sortie:
                sortie.append(mot)
    return sortie


def requete_fts(mots: list[str]) -> str:
    """Builds a tolerant FTS5 query: OR of prefixes.

    The OR favors recall; ranking does the sorting. An AND would return
    zero results as soon as one word from the question is missing from
    the schema.
    """
    return " OR ".join(f'"{m}"*' for m in mots)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Poids:
    """Each field is an isolable signal, to allow ablation.

    These values come from a sweep against the golden set, not intuition.
    TWO extra signals were tried and then **removed**, for lack of
    measurable effect (criterion E10): boosting leaves at the expense of
    containers, and question term coverage. Neither one moved a single
    golden-set entry, at any weight.
    """

    bm25_segments: float = 10.0
    bm25_description: float = 5.0
    segment_exact: float = 4.0
    profondeur: float = 0.6


DEFAUT = Poids()


@dataclass(frozen=True)
class Resultat:
    noeud: Noeud
    score: float


def _correspond(terme: str, segment: str) -> bool:
    """A term matches a segment if either prefixes the other.

    Strict equality was too rigid: "error" didn't recognize the segment
    `in-errors`, nor "counter" the segment `counters`. The prefix tolerance
    matches the FTS5 query's, so both signals speak the same vocabulary.
    The three-character floor keeps a short word like "in" from biting on
    "interface".
    """
    if terme == segment:
        return True
    if len(terme) < 3 or len(segment) < 3:
        return False
    return terme.startswith(segment) or segment.startswith(terme)


def _bonus_segment_exact(noeud: Noeud, mots: list[str]) -> float:
    """A term that IS a path segment, not just a word in its prose.

    This is the decisive signal: "transceiver" is an entire segment of
    `/state/port[]/transceiver/…`, while it appears nowhere in the DWDM
    paths that substring search ranked first.
    """
    segments: set[str] = set()
    for segment in noeud.chemin.strip("/").split("/"):
        nom = segment.split("[")[0]
        segments.add(nom)
        segments.update(nom.split("-"))

    return float(sum(1 for m in mots if any(_correspond(m, s) for s in segments)))


def chercher(
    conn: sqlite3.Connection,
    sujet: str,
    limite: int = 10,
    poids: Poids = DEFAUT,
) -> list[Resultat]:
    """Returns the most relevant nodes, best to worst."""
    mots = termes(sujet)
    if not mots:
        return []

    # bm25() returns a value that grows more negative the better the match;
    # we invert it so all signals can be added in the same direction.
    lignes = conn.execute(
        """
        SELECT n.*, bm25(recherche, ?, ?) AS score_fts
        FROM recherche
        JOIN noeuds n ON n.id = recherche.rowid
        WHERE recherche MATCH ?
        ORDER BY score_fts
        LIMIT 400
        """,
        (poids.bm25_segments, poids.bm25_description, requete_fts(mots)),
    ).fetchall()

    resultats: list[Resultat] = []
    for ligne in lignes:
        noeud = _vers_noeud(ligne)
        score = -float(ligne["score_fts"])
        score += poids.segment_exact * _bonus_segment_exact(noeud, mots)
        score -= poids.profondeur * noeud.profondeur
        resultats.append(Resultat(noeud, score))

    resultats.sort(key=lambda r: (-r.score, r.noeud.chemin))
    return resultats[: max(1, min(limite, 50))]


def sans_signal(poids: Poids, nom: str) -> Poids:
    """Neutralizes a signal — used only for ablation measurement (E10)."""
    if nom not in poids.__dataclass_fields__:
        raise ValueError(f"unknown signal: {nom}")
    return replace(poids, **{nom: 0.0})
