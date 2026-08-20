"""yangmap MCP server — two tools, no equipment contact.

This server connects to nothing. It reads indexes built offline and returns
documented paths. That's what gives it a zero security surface: no
credential, no inventory, no socket.

It **never** imports `bundles` or `indexer` — the only two modules that
touch the network or pyang. A test verifies this on the syntax tree.
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
    "yangmap tells you WHICH gNMI PATH carries WHICH information, on which"
    " vendor, and in which OS version. It contacts no equipment and returns"
    " no operational data: only the map of the YANG model."
    " Method: `yang_chercher` with the subject in natural language to get"
    " ranked paths, then `yang_detail` to descend the tree."
    " NEVER INVENT a path: if `yang_chercher` returns nothing, the"
    " information isn't modeled — say so rather than guess."
    " The `bundle_servi` field says which version the response covers;"
    " if `ecart` is anything other than `exact`, relay the warning."
)

_SUJET = (
    "What is being searched for, in natural language: 'active and inactive"
    " routes', 'SFP transceiver', 'ISIS adjacencies'. French is accepted."
)
_PLATEFORME = f"Vendor: {', '.join(PLATEFORMES)}."
_VERSION = (
    "Equipment OS version, as returned by gNMI Capabilities"
    " (e.g. 24.3.R3). Optional — without it, the most recently"
    " installed version is served, and the approximation is declared."
)


def _museler_les_bibliotheques() -> None:
    """stdio carries JSON-RPC: one stray line on stdout corrupts it."""
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
        except Exception as e:  # noqa: BLE001 — returned to the model as a fact
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
            "Finds the gNMI paths that carry a given piece of information,"
            f" ranked from most to least relevant. {_SUJET} {_PLATEFORME}"
            f" {_VERSION} Returns for each: the path ready to query, the"
            " node kind, the data type, and the vendor description."
        ),
    )
    server.add_tool(
        yang_detail,
        name="yang_detail",
        description=(
            "Details a path returned by `yang_chercher`: its description, the"
            " keys to fill in, and its IMMEDIATE CHILDREN — to descend the"
            f" tree without guessing. {_PLATEFORME} {_VERSION}"
        ),
    )
    return server


def main() -> None:
    p = argparse.ArgumentParser(description="yangmap MCP server")
    p.add_argument("--racine", default=str(RACINE_DEFAUT))
    args = p.parse_args()

    _museler_les_bibliotheques()
    carte = Carte(Path(args.racine))
    disponibles = carte.plateformes()
    if not disponibles:
        print(
            "yangmap: no index built. Run `yangmap fetch <platform>"
            " <version>` then `yangmap build <platform> <version>`.",
            file=sys.stderr,
        )
    else:
        resume = ", ".join(f"{p} {'/'.join(v)}" for p, v in disponibles.items())
        print(f"yangmap: available indexes — {resume}", file=sys.stderr)

    asyncio.run(create_server(carte).run_stdio_async())


if __name__ == "__main__":
    main()
