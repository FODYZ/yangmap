"""Is a path queryable — and what will it return?

`chercher` answers "where is the information". It was missing the next
question, the one the model asks right before querying a device: **does this
path exist, and is it reasonable to query it?**

Without it, there is only one way to know: send the query, wait for the
device, and interpret the silence. But the three failure modes look
identical once returned:

| What happened | What the model receives | What it concludes |
|---|---|---|
| The path does not exist | An empty response | "The feature is not configured" |
| A key was left as a template | An empty response | "The feature is not configured" |
| The subtree is enormous | A truncated response | It concludes from amputated data |

The first two lines are **false facts** stated with confidence; the third
is worse because it is invisible. This module decides all three offline,
before any contact, and returns an explicit reason instead of a blank void.

Pure read module: opens no connections, writes nothing, and only knows
the index.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from dataclasses import dataclass

from yangmap import index as idx
from yangmap.index import Noeud

# A key and its value: `[router-name=Base]`, `[interface-name=*]`, `[name=?]`.
_CLE = re.compile(r"\[([^\]=]+)=([^\]]*)\]")

# A key left as a template by a catalog, or empty. netlive already rejects
# both at runtime; rejecting them here saves the round trip.
_NON_RENSEIGNEE = ("?", "")

# How many nodes under a path before declaring it voluminous.
#
# Calibrated, not chosen arbitrarily: netlive's `interfaces` collector targeted
# the container `interface[interface-name=*]` and returned 17,583 characters for 5
# interfaces — easily enough to get truncated. This container has 522
# descendants in nokia-state 24.3.R3. The same path narrowed to the `oper-state`
# leaf returned 573 characters. The measured ratio is ~6.7 characters of JSON
# per descendant and per instance.
#
# 40 descendants on an unbounded list therefore amount to ~270 characters per
# instance: 100 instances suffice to saturate a 20,000 budget. That is where
# we warn.
SEUIL_LISTE = 40

# Even without multiple instances, a subtree of this size weighs ~2,000
# characters: still readable, beyond that no.
SEUIL_UNIQUE = 300

# Measured on netlive: 17,583 characters / (522 descendants × 5 instances).
OCTETS_PAR_DESCENDANT = 6.7


@dataclass(frozen=True)
class Verdict:
    """What can be stated about a path without touching any device."""

    verdict: str            # sur | volumineux | cle_manquante | inexistant
    motif: str
    noeud: Noeud | None = None
    descendants: int = 0
    octets_estimes: int = 0
    instances_inconnues: bool = False
    cles_manquantes: tuple[str, ...] = ()
    chemin_valide: str = ""
    suggestions: tuple[str, ...] = ()

    @property
    def interrogeable(self) -> bool:
        """A voluminous path remains queryable — it is a warning, not a
        rejection. Rejecting it in place of the operator would decide for them:
        sometimes you really want the entire tree."""
        return self.verdict in ("sur", "volumineux")


def _nom(xpath: str) -> str:
    """Last segment of an xpath, without keys or module prefix."""
    segment = xpath.rstrip("/").rsplit("/", 1)[-1]
    segment = segment.split("[", 1)[0]
    return segment.rsplit(":", 1)[-1]


def _segments(chemin: str) -> list[str]:
    """Splits on '/', **except inside square brackets**.

    A naive `split("/")` breaks on the key format Nokia enforces
    everywhere: `[port-id=1/1/c1]`. The path became "state, port[port-id=1,
    1, c1]", and the tool answered "unknown segment: 1" — a false negative
    on the exact path that tool descriptions cite as an example.
    """
    sortie, courant, dans_crochets = [], [], 0
    for c in chemin.strip().strip("/"):
        if c == "[":
            dans_crochets += 1
        elif c == "]":
            dans_crochets = max(0, dans_crochets - 1)
        if c == "/" and not dans_crochets:
            if courant:
                sortie.append("".join(courant))
            courant = []
            continue
        courant.append(c)
    if courant:
        sortie.append("".join(courant))
    return sortie


def decomposer(chemin: str) -> tuple[list[str], dict[str, str]]:
    """`/state/router[router-name=Base]/bgp` ⟶ (['state','router','bgp'], {…}).

    Key values are set aside: they do not identify the node in the schema,
    but they determine whether the query is bounded.
    """
    valeurs: dict[str, str] = {}
    noms: list[str] = []
    for segment in _segments(chemin):
        for cle, valeur in _CLE.findall(segment):
            valeurs[cle] = valeur
        nu = segment.split("[", 1)[0]
        noms.append(nu.rsplit(":", 1)[-1])
    return noms, valeurs


def _descendre(conn: sqlite3.Connection, noms: list[str]) -> tuple[Noeud | None, int]:
    """Descends segment by segment. Returns the last valid node and its index.

    Descending rather than looking up the entire path at once allows pointing
    out *where* it breaks — and therefore suggesting siblings of the faulty
    segment. A dry "unknown path" would only invite more guessing.
    """
    courant: Noeud | None = None
    for rang, nom in enumerate(noms):
        if courant is None:
            candidat = idx.par_chemin(conn, "/" + nom)
        else:
            candidat = next(
                (f for f in idx.enfants(conn, courant) if _nom(f.xpath) == nom), None
            )
        if candidat is None:
            return courant, rang
        courant = candidat
    return courant, len(noms)


def valider(conn: sqlite3.Connection, chemin: str) -> Verdict:
    """Full verdict on a path, without any equipment contact."""
    noms, valeurs = decomposer(chemin)
    if not noms:
        return Verdict("inexistant", "chemin vide")

    noeud, atteint = _descendre(conn, noms)

    if atteint < len(noms):
        manquant = noms[atteint]
        freres = [_nom(f.xpath) for f in idx.enfants(conn, noeud)] if noeud else []
        proches = difflib.get_close_matches(manquant, freres, n=5, cutoff=0.4)
        # The case encountered on netlab: `export-policy` does not exist, `export` does.
        # A prefix match often escapes get_close_matches — handled here.
        proches += [
            f for f in freres
            if (f.startswith(manquant) or manquant.startswith(f)) and f not in proches
        ]
        valide = noeud.chemin if noeud else "/"
        return Verdict(
            "inexistant",
            f"segment inconnu : {manquant!r} sous {valide}. "
            + (
                f"Enfants possibles : {', '.join(proches[:5])}."
                if proches else
                "Aucun enfant proche — ce n'est pas une faute de frappe, "
                "l'information n'est pas modélisée ici."
            ),
            chemin_valide=valide,
            suggestions=tuple(proches[:5]),
        )

    assert noeud is not None
    # Three states, and only two are errors:
    #
    #   `[ip-address=10.0.0.9]` — bounded, what we want;
    #   `[ip-address=?]` / `[ip-address=]` — a TEMPLATE copied verbatim, which
    #       the equipment translates to an empty response: this is an error;
    #   key absent from path — in gNMI, this means "all instances".
    #       This is valid, and netlive already allows it. Counting it as an
    #       error would reject working collectors — false positive caught
    #       when screening the whole catalog.
    manquantes = tuple(
        cle for cle in noeud.cles
        if cle in valeurs and valeurs[cle].strip() in _NON_RENSEIGNEE
    )
    if manquantes:
        return Verdict(
            "cle_manquante",
            f"clé(s) sans valeur : {', '.join(manquantes)}. Une clé laissée en "
            f"gabarit produit une réponse VIDE, indiscernable d'une fonction "
            f"non activée. Donner une valeur réelle, ou « * » pour toutes les "
            f"instances en connaissant le coût.",
            noeud=noeud,
            cles_manquantes=manquantes,
            chemin_valide=noeud.chemin,
        )

    descendants = idx.compter_descendants(conn, noeud)
    # A wildcard key anywhere in the path is enough to make the number of
    # instances unknown — not just on the last segment:
    # `/router[router-name=*]/interface[interface-name=eth0]` is just as
    # unbounded as the inverse.
    # A wildcard key, or simply absent key, leaves instance count unknown:
    # `/…/neighbor` without brackets returns ALL neighbors, exactly like
    # `[ip-address=*]`.
    jokers = "*" in valeurs.values() or any(
        cle not in valeurs for cle in noeud.cles
    )

    octets = int(descendants * OCTETS_PAR_DESCENDANT)
    seuil = SEUIL_LISTE if jokers else SEUIL_UNIQUE
    if descendants > seuil:
        multiple = " et par instance" if jokers else ""
        return Verdict(
            "volumineux",
            f"{descendants} nœuds sous ce chemin, soit ~{octets} caractères"
            f"{multiple}. "
            + (
                "Le nombre d'instances n'est pas borné : le résultat sera "
                "tronqué, et une troncature se conclut faux sans se voir. "
                if jokers else ""
            )
            + "Viser les feuilles utiles, un sous-chemin d'agrégat "
              "(`.../statistics`), ou renseigner les clés.",
            noeud=noeud,
            descendants=descendants,
            octets_estimes=octets,
            instances_inconnues=jokers,
            chemin_valide=noeud.chemin,
        )

    return Verdict(
        "sur",
        f"{noeud.genre}"
        + (f"/{noeud.type}" if noeud.type else "")
        + f", {descendants} nœud(s) sous ce chemin (~{octets} caractères).",
        noeud=noeud,
        descendants=descendants,
        octets_estimes=octets,
        instances_inconnues=jokers,
        chemin_valide=noeud.chemin,
    )
