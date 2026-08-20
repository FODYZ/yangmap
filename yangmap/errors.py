"""yangmap errors.

An error always names what needs to be done to clear it. A message that
states a fact without pointing to a fix wastes the operator's time as much
as the model's.
"""

from __future__ import annotations


class YangmapError(Exception):
    """Root — lets callers catch anything coming from yangmap."""


class ResolutionError(YangmapError):
    """Version or platform that could not be resolved."""


class IndexError_(YangmapError):
    """Index missing, unreadable, or inconsistent."""


class BundleError(YangmapError):
    """YANG bundle missing or impossible to download."""
