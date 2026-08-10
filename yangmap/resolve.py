"""Quel bundle sert une version demandée, et avec quel écart.

Les vendeurs ne publient pas leur YANG à chaque révision : mesuré le
2026-08-10, Nokia publie `sros_24.3.r3` au patch près, Cisco et Arista
s'arrêtent au train. Le repli est donc le **cas normal sur deux vendeurs sur
trois**, et il doit être annoncé — jamais silencieux (cahier D2, D3, D6).

Module pur : il raisonne sur des noms de version, pas sur des fichiers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from yangmap.errors import ResolutionError


class Ecart(str, Enum):
    EXACT = "exact"
    MEME_TRAIN = "meme_train"
    AUTRE_TRAIN = "autre_train"


@dataclass(frozen=True)
class Version:
    majeur: int
    mineur: int
    patch: int

    def __str__(self) -> str:
        return f"{self.majeur}.{self.mineur}.{self.patch}"

    @property
    def train(self) -> tuple[int, int]:
        return (self.majeur, self.mineur)


@dataclass(frozen=True)
class Resolution:
    version: Version
    ecart: Ecart
    demandee: str
    message: str | None
    """Rendu tel quel au client. `None` seulement quand l'écart est nul."""


_NOMBRES = re.compile(r"\d+")


def analyser_version(brut: str) -> Version:
    """Extrait (majeur, mineur, patch) d'une version de n'importe quel vendeur.

    Tolère les formes réelles rencontrées : `24.3.R3`, `17.3.4a`, `4.32.11M`,
    `24.3`, `sros_24.3.r3`. Ce qui n'est pas un nombre est ignoré : les
    suffixes de qualification (`F`, `M`, `a`) ne hiérarchisent rien
    d'exploitable ici.
    """
    nombres = _NOMBRES.findall(brut or "")
    if not nombres:
        raise ResolutionError(f"version illisible : {brut!r}")
    valeurs = [int(n) for n in nombres[:3]]
    while len(valeurs) < 3:
        valeurs.append(0)
    return Version(*valeurs)


def resoudre(demandee: str | None, disponibles: list[str]) -> Resolution:
    """Choisit le bundle le plus proche et qualifie l'écart.

    Sans version demandée, la plus récente est servie — un choix, donc il est
    annoncé comme les autres.
    """
    if not disponibles:
        raise ResolutionError(
            "aucun bundle installé pour cette plateforme — "
            "jouer `yangmap fetch <plateforme> <version>`"
        )

    versions = sorted(
        {analyser_version(d) for d in disponibles},
        key=lambda v: (v.majeur, v.mineur, v.patch),
    )

    if not demandee:
        choisie = versions[-1]
        return Resolution(
            choisie, Ecart.EXACT, "(non précisée)",
            f"Version non précisée : bundle {choisie} servi (le plus récent).",
        )

    cible = analyser_version(demandee)

    for v in versions:
        if v == cible:
            return Resolution(v, Ecart.EXACT, demandee, None)

    # Même train : on reste sur la même famille de fonctionnalités, l'écart
    # est mineur.
    du_train = [v for v in versions if v.train == cible.train]
    if du_train:
        choisie = min(du_train, key=lambda v: abs(v.patch - cible.patch))
        return Resolution(
            choisie, Ecart.MEME_TRAIN, demandee,
            f"Version {demandee} non publiée par le vendeur : bundle "
            f"{choisie} servi (même train {cible.majeur}.{cible.mineur}). "
            f"Les chemins peuvent différer à la marge.",
        )

    # Train différent : l'écart peut être structurel, l'avertissement est plus
    # fort.
    choisie = min(
        versions,
        key=lambda v: (abs(v.majeur - cible.majeur), abs(v.mineur - cible.mineur)),
    )
    return Resolution(
        choisie, Ecart.AUTRE_TRAIN, demandee,
        f"ATTENTION : aucun bundle du train {cible.majeur}.{cible.mineur}. "
        f"Bundle {choisie} servi à la place. Des chemins peuvent ne pas "
        f"exister sur la version {demandee}.",
    )
