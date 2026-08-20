"""pyang xpath ⟶ gNMI path.

pyang returns a node's identity in the *schema*: prefixed by the module,
keys named but without a value. A gNMI client needs something else — the
path in the *data* tree, where module prefixes don't appear and keys await a
value.

Pure module: no I/O, no state. It can be tested with no YANG, no network,
and no database (see criterion C6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A segment looks like `router[router-name]`, `nokia-state:state`, or
# `host[ip-address][mac-address][pppoe-session-id]`.
_CLES = re.compile(r"\[([^\]]+)\]")


@dataclass(frozen=True)
class Chemin:
    """Both forms of the same node, plus what's needed to query it."""

    xpath: str
    """pyang's canonical form, module prefixes kept. This is the node's
    identity in the schema, and the exact search key."""

    gnmi: str
    """Form ready for a gNMI Get: no prefix, keys marked `=?`."""

    module: str | None
    """Source module, when the segment carried one. A consumer that needs
    a qualified path can reconstruct it; none is ever lost."""

    cles: tuple[str, ...]
    """Keys to fill in, in the order they appear."""

    profondeur: int
    """Number of segments. A ranking signal: nine segments denote a
    specialized subsystem, four denote the core of a device."""

    segments: tuple[str, ...]
    """Segment names, without keys or prefixes — the indexed text."""


def _decoupe(segment: str) -> tuple[str, str | None, list[str]]:
    """Returns (name, module, keys) for an xpath segment."""
    corps, _, reste = segment.partition("[")
    cles = _CLES.findall("[" + reste) if reste else []

    module = None
    nom = corps
    if ":" in corps:
        # `openconfig-platform-transceiver:transceiver` — the prefix names
        # the module that augments the tree, not a level of the tree.
        module, _, nom = corps.rpartition(":")

    return nom, module, cles


def analyser(xpath: str) -> Chemin:
    """Splits a pyang xpath into its two useful forms."""
    bruts = [s for s in xpath.strip().strip("/").split("/") if s]

    noms: list[str] = []
    segments_gnmi: list[str] = []
    cles_totales: list[str] = []
    module_premier: str | None = None

    for rang, segment in enumerate(bruts):
        nom, module, cles = _decoupe(segment)
        if rang == 0:
            module_premier = module
        noms.append(nom)
        cles_totales.extend(cles)

        # A key that already carries a value is left untouched: it came
        # from a caller who knows what it wants, not from the schema.
        marquees = "".join(
            f"[{c}]" if "=" in c else f"[{c}=?]" for c in cles
        )
        segments_gnmi.append(nom + marquees)

    return Chemin(
        xpath=xpath,
        gnmi="/" + "/".join(segments_gnmi) if segments_gnmi else "/",
        module=module_premier,
        cles=tuple(cles_totales),
        profondeur=len(bruts),
        segments=tuple(noms),
    )


def arbre_de(xpath: str) -> str:
    """`conf` if the path belongs to the configuration tree, otherwise `etat`.

    Nokia separates the two into two modules (`nokia-conf`, `nokia-state`); the
    prefix on the first segment decides. Cisco only exposes `*-oper` models,
    and OpenConfig carries `config`/`state` inside the same tree: on both
    vendors everything remains `etat`, which is accurate — neither has an
    indexed configuration tree today.
    """
    module = analyser(xpath).module or ""
    return "conf" if module.endswith("-conf") else "etat"


def mots_de(chemin: str) -> str:
    """Reduces a path's segments to words, for full-text indexing.

    `route-table` becomes "route-table route table": an engineer searches
    for "routing table" without the hyphen, and FTS5 doesn't split on it.
    """
    vus: list[str] = []
    for segment in analyser(chemin).segments:
        for mot in [segment, *segment.split("-")]:
            if mot and mot not in vus:
                vus.append(mot)
    return " ".join(vus)
