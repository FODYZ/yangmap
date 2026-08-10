"""L'API que le serveur MCP expose, et que netlive peut appeler en direct.

Séparée de `server.py` pour que l'intégration à un autre outil n'oblige pas à
passer par un sous-processus MCP — et pour que les tests portent sur la
logique, pas sur le transport.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from yangmap import index as idx
from yangmap import search
from yangmap.errors import IndexError_, ResolutionError, YangmapError
from yangmap.resolve import Ecart, resoudre

RACINE_DEFAUT = Path.home() / ".yangmap"
PLATEFORMES = ("nokia_sros", "cisco_iosxe", "arista_eos")


@dataclass(frozen=True)
class Carte:
    """Accès aux index construits, sans aucune connexion à quoi que ce soit."""

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
                f"plateforme inconnue : {plateforme!r} "
                f"(connues : {', '.join(PLATEFORMES)}). "
                "Aucun repli sur un autre vendeur n'est fait."
            )
        dispo = self.versions(plateforme)
        if not dispo:
            raise IndexError_(
                f"aucun index pour {plateforme} — jouer "
                f"`yangmap fetch {plateforme} <version>` puis "
                f"`yangmap build {plateforme} <version>`"
            )
        res = resoudre(version, dispo)
        conn = idx.ouvrir(self._index / plateforme / f"{res.version}.db")
        return conn, res

    # -- outils exposés ----------------------------------------------------

    def chercher(
        self,
        sujet: str,
        plateforme: str,
        version: str | None = None,
        limite: int = 10,
    ) -> dict[str, Any]:
        conn, res = self._ouvrir(plateforme, version)
        try:
            trouves = search.chercher(conn, sujet, limite)
        finally:
            conn.close()

        return {
            "plateforme": plateforme,
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
                f"Aucun chemin ne correspond à {sujet!r} sur {plateforme} "
                f"{res.version}. Ne pas inventer de chemin : reformuler, ou "
                f"conclure que cette information n'est pas modélisée."
            ),
            # Un chemin recopié sans substituer ses clés produit un résultat
            # vide, que netlive traduisait en « fonction non configurée » —
            # une conclusion fausse et assurée. Défaut trouvé sur le lab réel
            # le 2026-08-10. Le rappel n'est émis que lorsqu'il sert.
            "action_requise": (
                "Remplacer chaque « =? » par une valeur réelle AVANT "
                "d'interroger un équipement (ex. [router-name=Base]). Un "
                "chemin laissé avec « =? » sera refusé."
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
                    f"chemin inconnu dans {plateforme} {res.version} : {chemin!r}. "
                    "Utiliser `yang_chercher` pour en obtenir un valide."
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


def en_erreur(e: Exception) -> dict[str, Any]:
    """Rend une erreur au modèle comme un fait, jamais comme un vide."""
    return {
        "status": "error",
        "message": str(e) if isinstance(e, YangmapError) else f"{type(e).__name__}: {e}",
    }
