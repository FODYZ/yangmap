"""Which bundle serves a requested version, and with what gap.

Vendors don't publish their YANG at every revision: measured on 2026-08-10,
Nokia publishes `sros_24.3.r3` down to the patch, Cisco and Arista stop at
the train. Falling back is therefore the **normal case on two vendors out of
three**, and it must be reported — never silent (criteria D2, D3, D6).

Pure module: it reasons over version names, not files.
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
    """Returned as-is to the client. `None` only when the gap is nil."""


_NOMBRES = re.compile(r"\d+")


def analyser_version(brut: str) -> Version:
    """Extracts (major, minor, patch) from any vendor's version string.

    Tolerates the real forms encountered: `24.3.R3`, `17.3.4a`, `4.32.11M`,
    `24.3`, `sros_24.3.r3`. Anything that isn't a number is ignored:
    qualification suffixes (`F`, `M`, `a`) don't order anything usable here.
    """
    nombres = _NOMBRES.findall(brut or "")
    if not nombres:
        raise ResolutionError(f"unreadable version: {brut!r}")
    valeurs = [int(n) for n in nombres[:3]]
    while len(valeurs) < 3:
        valeurs.append(0)
    return Version(*valeurs)


def resoudre(demandee: str | None, disponibles: list[str]) -> Resolution:
    """Picks the closest bundle and qualifies the gap.

    With no requested version, the most recent one is served — a choice,
    so it's announced like any other.
    """
    if not disponibles:
        raise ResolutionError(
            "no bundle installed for this platform — "
            "run `yangmap fetch <platform> <version>`"
        )

    versions = sorted(
        {analyser_version(d) for d in disponibles},
        key=lambda v: (v.majeur, v.mineur, v.patch),
    )

    if not demandee:
        choisie = versions[-1]
        return Resolution(
            choisie, Ecart.EXACT, "(unspecified)",
            f"No version specified: bundle {choisie} served (the most recent).",
        )

    cible = analyser_version(demandee)

    for v in versions:
        if v == cible:
            return Resolution(v, Ecart.EXACT, demandee, None)

    # Same train: we stay on the same feature family, the gap is minor.
    du_train = [v for v in versions if v.train == cible.train]
    if du_train:
        choisie = min(du_train, key=lambda v: abs(v.patch - cible.patch))
        return Resolution(
            choisie, Ecart.MEME_TRAIN, demandee,
            f"Version {demandee} not published by the vendor: bundle "
            f"{choisie} served (same train {cible.majeur}.{cible.mineur}). "
            f"Paths may differ at the margin.",
        )

    # Different train: the gap may be structural, the warning is stronger.
    choisie = min(
        versions,
        key=lambda v: (abs(v.majeur - cible.majeur), abs(v.mineur - cible.mineur)),
    )
    return Resolution(
        choisie, Ecart.AUTRE_TRAIN, demandee,
        f"WARNING: no bundle for train {cible.majeur}.{cible.mineur}. "
        f"Bundle {choisie} served instead. Some paths may not "
        f"exist on version {demandee}.",
    )
