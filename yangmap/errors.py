"""Erreurs de yangmap.

Une erreur nomme toujours ce qu'il faut faire pour la lever. Un message qui
constate sans orienter fait perdre du temps à l'opérateur comme au modèle.
"""

from __future__ import annotations


class YangmapError(Exception):
    """Racine — permet d'attraper tout ce qui vient de yangmap."""


class ResolutionError(YangmapError):
    """Version ou plateforme impossible à résoudre."""


class IndexError_(YangmapError):
    """Index absent, illisible ou incohérent."""


class BundleError(YangmapError):
    """Bundle YANG absent ou impossible à télécharger."""
