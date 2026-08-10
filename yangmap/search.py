"""Recherche et classement — le seul endroit difficile du projet.

Les pondérations ci-dessous ne sont pas des intuitions : elles sont réglées
contre le jeu d'or (`goldenset/`), et tout signal qui n'améliore aucune de ses
entrées doit être retiré (cahier E10).

Le défaut à battre est documenté et mesuré : une recherche par sous-chaîne rend
`/state/port[]/dwdm/coherent/rx-optical-snr-x-polarization` pour « transceiver »
et `/state/radius/route-downloader[]/…` pour « table de routage ». La donnée
correcte est dans l'index dans les deux cas ; seul l'ordre est faux.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace

from yangmap.index import Noeud, _vers_noeud

# ---------------------------------------------------------------------------
# Préparation de la requête
# ---------------------------------------------------------------------------

# Les descriptions des vendeurs sont en anglais ; les questions arrivent en
# français. Ce lexique est volontairement court et purement réseau : il traduit
# ce qu'un ingénieur tape, pas la langue française. Toute entrée doit être
# justifiée par une question du jeu d'or.
#
# Une entrée peut rendre **plusieurs** mots : « optique » désigne indifféremment
# l'optical, le transceiver et le SFF selon le vendeur, et n'en émettre qu'un
# seul ferait manquer les deux autres.
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

# Mots qui n'apportent rien à la sélection et diluent le score.
VIDES = frozenset("""
a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui
ma mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui
sa se ses son sur ta te tes toi ton tu un une vos votre vous y est sont quel
quelle quels quelles quoi comment pourquoi combien
the of for and or is are to in on with what which how
""".split())

_MOT = re.compile(r"[a-z0-9]+", re.I)


def _racine(mot: str) -> str:
    """Pluriel français grossièrement retiré, pour que le préfixe FTS5 morde.

    « actives » n'est pas un préfixe d'« active » : sans ce raccourcissement,
    une question au pluriel ne trouverait jamais une description au singulier.
    """
    if len(mot) > 4 and mot.endswith(("s", "x")):
        return mot[:-1]
    return mot


def termes(sujet: str) -> list[str]:
    """Question en langage naturel ⟶ termes de recherche, dédoublonnés."""
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
    """Construit une requête FTS5 tolérante : OR de préfixes.

    Le OR privilégie le rappel ; c'est le classement qui fait le tri. Un AND
    rendrait zéro résultat dès qu'un mot de la question manque au schéma.
    """
    return " OR ".join(f'"{m}"*' for m in mots)


# ---------------------------------------------------------------------------
# Classement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Poids:
    """Chaque champ est un signal isolable, pour permettre l'ablation.

    Ces valeurs sortent d'un balayage contre le jeu d'or, pas d'une intuition.
    DEUX signaux supplémentaires ont été essayés puis **retirés**, faute
    d'effet mesurable (cahier E10) : bonifier les feuilles au détriment des
    conteneurs, et la couverture des termes de la question. Ni l'un ni
    l'autre ne déplaçait une seule entrée du jeu d'or, à aucun poids.
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
    """Un terme correspond à un segment si l'un préfixe l'autre.

    L'égalité stricte était trop rigide : « error » ne reconnaissait pas le
    segment `in-errors`, ni « counter » le segment `counters`. La tolérance de
    préfixe est la même que celle de la requête FTS5, donc les deux signaux
    parlent du même vocabulaire. Le plancher de trois caractères évite qu'un
    mot court comme « in » morde sur « interface ».
    """
    if terme == segment:
        return True
    if len(terme) < 3 or len(segment) < 3:
        return False
    return terme.startswith(segment) or segment.startswith(terme)


def _bonus_segment_exact(noeud: Noeud, mots: list[str]) -> float:
    """Un terme qui EST un segment du chemin, pas seulement un mot de sa prose.

    C'est le signal décisif : « transceiver » est un segment entier de
    `/state/port[]/transceiver/…` alors qu'il n'apparaît nulle part dans les
    chemins DWDM que la sous-chaîne remontait en tête.
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
    """Rend les nœuds les plus pertinents, du meilleur au moins bon."""
    mots = termes(sujet)
    if not mots:
        return []

    # bm25() rend une valeur d'autant plus négative que la correspondance est
    # bonne ; on l'inverse pour additionner des signaux qui vont tous dans le
    # même sens.
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
    """Neutralise un signal — sert uniquement à la mesure par ablation (E10)."""
    if nom not in poids.__dataclass_fields__:
        raise ValueError(f"signal inconnu : {nom}")
    return replace(poids, **{nom: 0.0})
