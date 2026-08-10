"""xpath pyang ⟶ chemin gNMI.

pyang rend l'identité d'un nœud dans le *schéma* : préfixée par le module,
clés nommées mais sans valeur. Un client gNMI a besoin d'autre chose — le
chemin dans l'arbre de *données*, où les préfixes de module ne figurent pas
et où les clés attendent une valeur.

Module pur : aucune entrée/sortie, aucun état. Il se teste sans YANG, sans
réseau et sans base (cf. cahier C6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Un segment ressemble à `router[router-name]`, `nokia-state:state`, ou
# `host[ip-address][mac-address][pppoe-session-id]`.
_CLES = re.compile(r"\[([^\]]+)\]")


@dataclass(frozen=True)
class Chemin:
    """Les deux formes d'un même nœud, plus ce qu'il faut pour le requêter."""

    xpath: str
    """Forme canonique de pyang, préfixes de module conservés. C'est
    l'identité du nœud dans le schéma, et la clé de recherche exacte."""

    gnmi: str
    """Forme prête pour un Get gNMI : sans préfixe, clés marquées `=?`."""

    module: str | None
    """Module d'origine, quand le segment le portait. Un consommateur qui a
    besoin d'un chemin qualifié peut le reconstruire ; aucun ne le perd."""

    cles: tuple[str, ...]
    """Clés à renseigner, dans l'ordre où elles apparaissent."""

    profondeur: int
    """Nombre de segments. Un signal de classement : neuf segments désignent
    un sous-système spécialisé, quatre le cœur d'un équipement."""

    segments: tuple[str, ...]
    """Noms de segments, sans clés ni préfixes — le texte indexé."""


def _decoupe(segment: str) -> tuple[str, str | None, list[str]]:
    """Rend (nom, module, clés) pour un segment de xpath."""
    corps, _, reste = segment.partition("[")
    cles = _CLES.findall("[" + reste) if reste else []

    module = None
    nom = corps
    if ":" in corps:
        # `openconfig-platform-transceiver:transceiver` — le préfixe nomme le
        # module qui augmente l'arbre, pas un niveau de l'arbre.
        module, _, nom = corps.rpartition(":")

    return nom, module, cles


def analyser(xpath: str) -> Chemin:
    """Décompose un xpath pyang en ses deux formes utiles."""
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

        # Une clé déjà porteuse d'une valeur est laissée intacte : elle vient
        # d'un appelant qui sait ce qu'il veut, pas du schéma.
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


def mots_de(chemin: str) -> str:
    """Segments d'un chemin réduits en mots, pour l'indexation plein texte.

    `route-table` devient « route-table route table » : un ingénieur cherche
    « table de routage » sans le trait d'union, et FTS5 ne coupe pas dessus.
    """
    vus: list[str] = []
    for segment in analyser(chemin).segments:
        for mot in [segment, *segment.split("-")]:
            if mot and mot not in vus:
                vus.append(mot)
    return " ".join(vus)
