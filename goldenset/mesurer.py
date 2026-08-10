"""Banc de mesure du classement — c'est lui qui décide des pondérations.

    python goldenset/mesurer.py              mesure le réglage courant
    python goldenset/mesurer.py --ablation   retire un signal à la fois (E10)
    python goldenset/mesurer.py --detail     montre les échecs, résultat par résultat

Aucune pondération ne doit être changée sans que ce banc ait dit qu'elle
améliore quelque chose.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from yangmap import search  # noqa: E402
from yangmap.api import RACINE_DEFAUT  # noqa: E402

RANG_ACCEPTE = 5
GOLDEN = Path(__file__).parent / "golden.yaml"


@dataclass
class Cas:
    question: str
    plateforme: str
    attendu: str
    pourquoi: str


@dataclass
class Mesure:
    cas: Cas
    rang: int | None
    premiers: list[str]

    @property
    def reussi(self) -> bool:
        return self.rang is not None and self.rang <= RANG_ACCEPTE


def charger() -> list[Cas]:
    brut = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    return [Cas(**e) for e in brut]


def _index(racine: Path, plateforme: str) -> Path:
    base = Path(racine) / "index" / plateforme
    bases = sorted(base.glob("*.db"))
    if not bases:
        raise SystemExit(
            f"aucun index pour {plateforme} — jouer `yangmap fetch` puis `build`"
        )
    return bases[-1]


def mesurer(cas: list[Cas], poids: search.Poids, racine: Path) -> list[Mesure]:
    mesures: list[Mesure] = []
    for c in cas:
        conn = sqlite3.connect(_index(racine, c.plateforme))
        conn.row_factory = sqlite3.Row
        try:
            trouves = search.chercher(conn, c.question, limite=50, poids=poids)
        finally:
            conn.close()

        rx = re.compile(c.attendu)
        rang = next(
            (i for i, r in enumerate(trouves, 1) if rx.search(r.noeud.chemin)), None
        )
        mesures.append(Mesure(c, rang, [r.noeud.chemin for r in trouves[:5]]))
    return mesures


def taux(mesures: list[Mesure]) -> float:
    return 100.0 * sum(m.reussi for m in mesures) / max(1, len(mesures))


def _rapport(mesures: list[Mesure], detail: bool) -> None:
    par_plateforme: dict[str, list[Mesure]] = {}
    for m in mesures:
        par_plateforme.setdefault(m.cas.plateforme, []).append(m)

    print(f"{'plateforme':<14} {'reussis':>9} {'total':>6} {'taux':>7}")
    print("-" * 40)
    for plateforme, groupe in sorted(par_plateforme.items()):
        n = sum(m.reussi for m in groupe)
        print(f"{plateforme:<14} {n:>9} {len(groupe):>6} {taux(groupe):>6.0f}%")
    print("-" * 40)
    print(f"{'TOTAL':<14} {sum(m.reussi for m in mesures):>9} "
          f"{len(mesures):>6} {taux(mesures):>6.0f}%")

    echecs = [m for m in mesures if not m.reussi]
    if echecs:
        print(f"\n{len(echecs)} echec(s) :")
        for m in echecs:
            rang = m.rang if m.rang else "absent des 50"
            print(f"\n  ✗ [{m.cas.plateforme}] « {m.cas.question} »  (rang : {rang})")
            print(f"    attendu : {m.cas.attendu}")
            if detail:
                for i, chemin in enumerate(m.premiers, 1):
                    print(f"      {i}. {chemin[:96]}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ablation", action="store_true")
    p.add_argument("--detail", action="store_true")
    p.add_argument("--racine", default=str(RACINE_DEFAUT))
    args = p.parse_args()

    cas = charger()
    racine = Path(args.racine)
    reference = mesurer(cas, search.DEFAUT, racine)

    if not args.ablation:
        _rapport(reference, args.detail)
        return 0 if taux(reference) >= 80 else 1

    base = taux(reference)
    print(f"reference : {base:.0f}%  ({len(cas)} cas)\n")
    print(f"{'signal neutralise':<22} {'taux':>7} {'delta':>8}  verdict")
    print("-" * 60)
    for nom in search.DEFAUT.__dataclass_fields__:
        t = taux(mesurer(cas, search.sans_signal(search.DEFAUT, nom), racine))
        delta = t - base
        verdict = "UTILE" if delta < 0 else ("inutile" if delta == 0 else "NUISIBLE")
        print(f"{nom:<22} {t:>6.0f}% {delta:>+7.0f}%  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
