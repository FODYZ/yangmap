"""Un chemin est-il interrogeable — et que va-t-il rendre ?

`chercher` répond à « où est l'information ». Il manquait la question d'après,
celle que le modèle se pose juste avant d'appeler un équipement : **est-ce que
ce chemin-là existe, et est-ce raisonnable de le tirer ?**

Sans elle, il n'y a qu'une façon de savoir : envoyer, attendre l'équipement,
et interpréter le silence. Or les trois façons d'échouer se ressemblent une
fois revenues :

| Ce qui s'est passé | Ce que le modèle reçoit | Ce qu'il en conclut |
|---|---|---|
| le chemin n'existe pas | une réponse vide | « la fonction n'est pas activée » |
| une clé est restée en gabarit | une réponse vide | « la fonction n'est pas activée » |
| le sous-arbre est énorme | une réponse tronquée | il conclut sur des données amputées |

Les deux premières lignes sont des **faits faux** énoncés avec assurance ; la
troisième est pire, parce qu'invisible. Ce module tranche les trois hors ligne,
avant tout contact, et rend un motif au lieu d'un vide.

Module de lecture pure : il n'ouvre aucune connexion, n'écrit rien, et ne
connaît que l'index.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from dataclasses import dataclass

from yangmap import index as idx
from yangmap.index import Noeud

# Une clé et sa valeur : `[router-name=Base]`, `[interface-name=*]`, `[name=?]`.
_CLE = re.compile(r"\[([^\]=]+)=([^\]]*)\]")

# Une clé laissée en gabarit par un catalogue, ou vide. netlive refuse déjà
# ces deux formes à l'exécution ; les refuser ici évite l'aller-retour.
_NON_RENSEIGNEE = ("?", "")

# Combien de nœuds sous un chemin avant de le déclarer volumineux.
#
# Calibré, pas choisi : le collecteur `interfaces` de netlive visait le
# conteneur `interface[interface-name=*]` et rendait 17 583 caractères pour 5
# interfaces — largement de quoi se faire tronquer. Ce conteneur porte **522**
# descendants dans nokia-state 24.3.R3. Le même chemin restreint à la feuille
# `oper-state` rendait 573 caractères. Le rapport mesuré est d'environ
# 6,7 caractères de JSON par descendant et par instance.
#
# 40 descendants sur une liste non bornée valent donc ~270 caractères par
# instance : cent instances suffisent à saturer un budget de 20 000. C'est là
# qu'on avertit.
SEUIL_LISTE = 40

# Même sans instance multiple, un sous-arbre de cette taille pèse ~2 000
# caractères : ça reste lisible, au-delà non.
SEUIL_UNIQUE = 300

# Mesuré sur netlive : 17 583 caractères / (522 descendants × 5 instances).
OCTETS_PAR_DESCENDANT = 6.7


@dataclass(frozen=True)
class Verdict:
    """Ce qu'on peut dire d'un chemin sans toucher à un équipement."""

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
        """Un chemin volumineux reste interrogeable — c'est un avertissement,
        pas un refus. Le refuser à la place de l'opérateur serait décider pour
        lui : parfois on veut vraiment tout l'arbre."""
        return self.verdict in ("sur", "volumineux")


def _nom(xpath: str) -> str:
    """Dernier segment d'un xpath, sans clés ni préfixe de module."""
    segment = xpath.rstrip("/").rsplit("/", 1)[-1]
    segment = segment.split("[", 1)[0]
    return segment.rsplit(":", 1)[-1]


def _segments(chemin: str) -> list[str]:
    """Découpe sur « / », **sauf à l'intérieur des crochets**.

    Un `split("/")` naïf casse sur la seule forme de clé que Nokia impose
    partout : `[port-id=1/1/c1]`. Le chemin devenait « state, port[port-id=1,
    1, c1] », et l'outil répondait « segment inconnu : 1 » — un faux négatif
    sur le chemin même que les descriptions d'outils citent en exemple.
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

    Les valeurs de clés sont mises de côté : elles n'identifient pas le nœud
    dans le schéma, mais ce sont elles qui décident si la requête est bornée.
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
    """Descend segment par segment. Rend le dernier nœud valide et son rang.

    Descendre plutôt que chercher le chemin entier d'un coup, c'est ce qui
    permet de dire *où* ça casse — et donc de proposer les frères du segment
    fautif. Un « chemin inconnu » sec ne fait qu'inviter à deviner encore.
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
    """Verdict complet sur un chemin, sans aucun contact équipement."""
    noms, valeurs = decomposer(chemin)
    if not noms:
        return Verdict("inexistant", "chemin vide")

    noeud, atteint = _descendre(conn, noms)

    if atteint < len(noms):
        manquant = noms[atteint]
        freres = [_nom(f.xpath) for f in idx.enfants(conn, noeud)] if noeud else []
        proches = difflib.get_close_matches(manquant, freres, n=5, cutoff=0.4)
        # Le cas vécu sur netlab : `export-policy` n'existe pas, `export` si.
        # Un préfixe échappe souvent à get_close_matches — pas ici.
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
    manquantes = tuple(
        cle for cle in noeud.cles
        if valeurs.get(cle, "?").strip() in _NON_RENSEIGNEE
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
    # Une clé jokerisée n'importe où dans le chemin suffit à rendre le nombre
    # d'instances inconnu — pas seulement sur le dernier segment :
    # `/router[router-name=*]/interface[interface-name=eth0]` est tout aussi
    # non borné que l'inverse.
    jokers = "*" in valeurs.values()

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
