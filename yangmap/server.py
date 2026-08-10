"""Serveur MCP yangmap — deux outils, aucun contact équipement.

Ce serveur ne se connecte à rien. Il lit des index construits hors ligne et
rend des chemins documentés. C'est ce qui lui donne une surface de sécurité
nulle : il n'a ni credential, ni inventaire, ni socket.

Il n'importe **jamais** `bundles` ni `indexer` — les deux seuls modules qui
touchent le réseau ou pyang. Un test le vérifie sur l'arbre syntaxique.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from yangmap.api import PLATEFORMES, RACINE_DEFAUT, Carte, en_erreur

INSTRUCTIONS = (
    "yangmap dit QUEL CHEMIN gNMI porte QUELLE information, sur quel vendeur"
    " et dans quelle version d'OS. Il ne contacte aucun équipement et ne rend"
    " aucune donnée d'exploitation : uniquement la carte du modèle YANG."
    " Méthode : `yang_chercher` avec le sujet en langage naturel pour obtenir"
    " des chemins classés, puis `yang_detail` pour descendre dans l'arbre."
    " N'INVENTE JAMAIS de chemin : si `yang_chercher` ne rend rien, c'est que"
    " l'information n'est pas modélisée — dis-le plutôt que de deviner."
    " Le champ `bundle_servi` dit sur quelle version la réponse porte ;"
    " si `ecart` vaut autre chose que `exact`, relaie l'avertissement."
)

_SUJET = (
    "Ce que l'on cherche, en langage naturel : « routes actives et inactives »,"
    " « transceiver SFP », « adjacences ISIS ». Le français est accepté."
)
_PLATEFORME = f"Vendeur : {', '.join(PLATEFORMES)}."
_VERSION = (
    "Version d'OS de l'équipement, telle que rendue par gNMI Capabilities"
    " (ex. 24.3.R3). Facultative — sans elle, la version la plus récente"
    " installée est servie, et l'approximation est déclarée."
)


def _museler_les_bibliotheques() -> None:
    """stdio porte du JSON-RPC : une ligne parasite sur stdout le corrompt."""
    logging.basicConfig(level=logging.CRITICAL, stream=sys.stderr)
    for nom in ("mcp", "asyncio"):
        logging.getLogger(nom).setLevel(logging.CRITICAL)


def create_server(carte: Carte) -> MCPServer:
    server = MCPServer(name="yangmap", instructions=INSTRUCTIONS, version="0.1.0")

    def yang_chercher(
        sujet: str,
        plateforme: str,
        version: str | None = None,
        limite: int = 10,
    ) -> dict[str, Any]:
        try:
            return carte.chercher(sujet, plateforme, version, limite)
        except Exception as e:  # noqa: BLE001 — rendu au modèle comme un fait
            return en_erreur(e)

    def yang_detail(
        chemin: str,
        plateforme: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        try:
            return carte.detail(chemin, plateforme, version)
        except Exception as e:  # noqa: BLE001
            return en_erreur(e)

    server.add_tool(
        yang_chercher,
        name="yang_chercher",
        description=(
            "Trouve les chemins gNMI qui portent une information donnée, classés"
            f" du plus pertinent au moins pertinent. {_SUJET} {_PLATEFORME}"
            f" {_VERSION} Rend pour chacun : le chemin prêt à interroger, le"
            " genre de nœud, le type de donnée et la description du vendeur."
        ),
    )
    server.add_tool(
        yang_detail,
        name="yang_detail",
        description=(
            "Détaille un chemin rendu par `yang_chercher` : sa description, les"
            " clés à renseigner, et ses ENFANTS IMMÉDIATS — pour descendre dans"
            f" l'arbre sans deviner. {_PLATEFORME} {_VERSION}"
        ),
    )
    return server


def main() -> None:
    p = argparse.ArgumentParser(description="Serveur MCP yangmap")
    p.add_argument("--racine", default=str(RACINE_DEFAUT))
    args = p.parse_args()

    _museler_les_bibliotheques()
    carte = Carte(Path(args.racine))
    disponibles = carte.plateformes()
    if not disponibles:
        print(
            "yangmap : aucun index construit. Jouer `yangmap fetch <plateforme>"
            " <version>` puis `yangmap build <plateforme> <version>`.",
            file=sys.stderr,
        )
    else:
        resume = ", ".join(f"{p} {'/'.join(v)}" for p, v in disponibles.items())
        print(f"yangmap : index disponibles — {resume}", file=sys.stderr)

    asyncio.run(create_server(carte).run_stdio_async())


if __name__ == "__main__":
    main()
