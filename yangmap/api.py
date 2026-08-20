"""The API the MCP server exposes, and that netlive can call directly.

Kept separate from `server.py` so integrating with another tool doesn't
require going through an MCP subprocess — and so tests exercise the logic,
not the transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from yangmap import index as idx
from yangmap import search
from yangmap.errors import IndexError_, ResolutionError, YangmapError
from yangmap.resolve import Ecart, resoudre
from yangmap.valider import valider as valider_chemin

RACINE_DEFAUT = Path.home() / ".yangmap"
PLATEFORMES = ("nokia_sros", "cisco_iosxe", "arista_eos")


@dataclass(frozen=True)
class Carte:
    """Access to built indexes, with no connection to anything."""

    racine: Path = RACINE_DEFAUT

    @property
    def _index(self) -> Path:
        return Path(self.racine) / "index"

    def versions(self, plateforme: str) -> list[str]:
        base = self._index / plateforme
        if not base.is_dir():
            return []
        return sorted(p.stem for p in base.glob("*.db"))

    def plateformes(self) -> dict[str, list[str]]:
        return {p: self.versions(p) for p in PLATEFORMES if self.versions(p)}

    def _ouvrir(self, plateforme: str, version: str | None):
        if plateforme not in PLATEFORMES:
            raise ResolutionError(
                f"unknown platform: {plateforme!r} "
                f"(known: {', '.join(PLATEFORMES)}). "
                "No fallback to another vendor is performed."
            )
        dispo = self.versions(plateforme)
        if not dispo:
            raise IndexError_(
                f"no index for {plateforme} — run "
                f"`yangmap fetch {plateforme} <version>` then "
                f"`yangmap build {plateforme} <version>`"
            )
        res = resoudre(version, dispo)
        conn = idx.ouvrir(self._index / plateforme / f"{res.version}.db")
        return conn, res

    # -- exposed tools -------------------------------------------------

    def chercher(
        self,
        sujet: str,
        plateforme: str,
        version: str | None = None,
        limite: int = 10,
        arbre: str = "etat",
    ) -> dict[str, Any]:
        conn, res = self._ouvrir(plateforme, version)
        try:
            trouves = search.chercher(conn, sujet, limite, arbre=arbre)
        finally:
            conn.close()

        return {
            "plateforme": plateforme,
            "arbre": arbre,
            "bundle_servi": str(res.version),
            "version_demandee": res.demandee,
            "ecart": res.ecart.value,
            "avertissement": res.message,
            "resultats": [
                {
                    "chemin": r.noeud.chemin,
                    "xpath": r.noeud.xpath,
                    "genre": r.noeud.genre,
                    "type": r.noeud.type,
                    "description": r.noeud.description,
                    "cles": list(r.noeud.cles),
                    "score": round(r.score, 2),
                }
                for r in trouves
            ],
            "message": (
                None if trouves else
                f"No path matches {sujet!r} on {plateforme} "
                f"{res.version} in the {arbre!r} tree. Do not invent a "
                f"path: rephrase, try the other tree "
                f"(`arbre=\"conf\"` holds CONFIGURATION, `arbre=\"etat\"` "
                f"operational state), or conclude that this information "
                f"is not modeled."
            ),
            # A path copied back without substituting its keys produces an
            # empty result, which netlive translated into "feature not
            # configured" — a confidently wrong conclusion. Defect found on
            # the real lab on 2026-08-10. The reminder is only emitted when
            # it's actually useful.
            "action_requise": (
                "Replace every '=?' with a real value BEFORE querying "
                "equipment (e.g. [router-name=Base]). A path left with "
                "'=?' will be refused."
                if any(r.noeud.cles for r in trouves) else None
            ),
        }

    def detail(
        self,
        chemin: str,
        plateforme: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        conn, res = self._ouvrir(plateforme, version)
        try:
            noeud = idx.par_chemin(conn, chemin)
            if noeud is None:
                raise IndexError_(
                    f"unknown path in {plateforme} {res.version}: {chemin!r}. "
                    "Use `yang_chercher` to obtain a valid one."
                )
            fils = idx.enfants(conn, noeud)
        finally:
            conn.close()

        return {
            "plateforme": plateforme,
            "bundle_servi": str(res.version),
            "ecart": res.ecart.value,
            "avertissement": res.message,
            "noeud": {
                "chemin": noeud.chemin,
                "xpath": noeud.xpath,
                "genre": noeud.genre,
                "type": noeud.type,
                "description": noeud.description,
                "cles_a_fournir": list(noeud.cles),
            },
            "enfants": [
                {
                    "chemin": f.chemin,
                    "nom": f.xpath.rsplit("/", 1)[-1].split("[")[0],
                    "genre": f.genre,
                    "type": f.type,
                    "description": f.description,
                }
                for f in fils
            ],
        }


    def valider(
        self,
        chemin: str,
        plateforme: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Does this path exist, is it complete, and what will it return?

        The question the model asks right before querying a device, and which
        it could previously only answer by trying. A failed attempt returns an
        empty response, which netlive translated into "feature not configured" —
        a confidently wrong conclusion. Here, the reason is explicit and no
        device was contacted.
        """
        conn, res = self._ouvrir(plateforme, version)
        try:
            v = valider_chemin(conn, chemin)
        finally:
            conn.close()

        return {
            "plateforme": plateforme,
            "bundle_servi": str(res.version),
            "ecart": res.ecart.value,
            "avertissement": res.message,
            "chemin_demande": chemin,
            "verdict": v.verdict,
            "interrogeable": v.interrogeable,
            "motif": v.motif,
            "chemin_valide_jusqu_a": v.chemin_valide,
            "suggestions": list(v.suggestions),
            "descendants": v.descendants,
            "octets_estimes": v.octets_estimes,
            "instances_non_bornees": v.instances_inconnues,
            "cles_manquantes": list(v.cles_manquantes),
            "noeud": None if v.noeud is None else {
                "chemin": v.noeud.chemin,
                "genre": v.noeud.genre,
                "type": v.noeud.type,
                "description": v.noeud.description,
                "arbre": v.noeud.arbre,
            },
        }


def en_erreur(e: Exception) -> dict[str, Any]:
    """Returns an error to the model as a fact, never as a void."""
    return {
        "status": "error",
        "message": str(e) if isinstance(e, YangmapError) else f"{type(e).__name__}: {e}",
    }
