"""yangmap MCP server — three tools, no equipment contact.

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
    " Before sending a path constructed or edited by hand, pass it to"
    " `yang_valider`: it tells you if it exists, if its keys are filled in, and"
    " how heavy it will be, without contacting any device — one fewer round"
    " trip, and an explicit reason instead of an empty response."
    " NEVER INVENT a path: if `yang_chercher` returns nothing, the"
    " information isn't modeled — say so rather than guess."
    " Two trees coexist, and a search targets only one at a time:"
    " `arbre=\"etat\"` (default) is operational state, what a diagnostic Get"
    " queries; `arbre=\"conf\"` is the CONFIGURATION tree, to be used for"
    " 'how is this configured' — e.g. which policy is applied to a BGP group."
    " Try the other tree before concluding that information is not modeled."
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
# The details of the two trees live in INSTRUCTIONS, read once: repeating
# them in every description would exceed the context budget protected by
# criterion F5 (< 600 characters per tool).
_ARBRE = "`arbre`: `etat` (default) or `conf` — see instructions."


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
        arbre: str = "etat",
    ) -> dict[str, Any]:
        try:
            return carte.chercher(sujet, plateforme, version, limite, arbre=arbre)
        except Exception as e:  # noqa: BLE001 — returned to the model as a fact
            return en_erreur(e)

    def yang_valider(
        chemin: str,
        plateforme: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        try:
            return carte.valider(chemin, plateforme, version)
        except Exception as e:  # noqa: BLE001
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
            f" ranked by relevance. {_SUJET} {_PLATEFORME} {_VERSION} Returns"
            f" the path, node kind, data type, and description. {_ARBRE}"
        ),
    )
    server.add_tool(
        yang_valider,
        name="yang_valider",
        description=(
            "Validates a path BEFORE sending it to equipment, without"
            " contacting any device. Distinguishes three failures that look"
            " identical once returned: nonexistent path (names the faulty"
            " segment and possible children), template key left as '=?' (empty"
            " response, mistaken for 'not configured'), subtree too large"
            " (truncated response, causing silent wrong conclusions)."
            " Call on any hand-written path, and after any empty result."
            f" {_PLATEFORME}"
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
