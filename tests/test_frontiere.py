"""Domain A — the founding boundary: no equipment contact.

These tests work on the syntax tree, not on behavior: it's the absence of a
code path that protects, not an instruction. A behavioral test would let an
import added by mistake slip through.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAQUET = Path(__file__).resolve().parents[1] / "yangmap"

# `bundles` downloads (git) and `indexer` runs pyang: these are the only two
# modules allowed to leave the process, and neither is imported by the
# server.
MODULES_RESEAU = {"bundles.py", "indexer.py"}

INTERDITS_RESEAU = {
    "socket", "http", "http.client", "https", "urllib", "urllib.request",
    "requests", "httpx", "aiohttp", "grpc", "grpcio", "pygnmi", "paramiko",
    "scrapli", "netmiko", "telnetlib", "ftplib", "smtplib",
}
INTERDITS_SECRETS = {"keyring", "getpass", "secretstorage", "keyrings"}


def _modules() -> list[Path]:
    return sorted(PAQUET.glob("*.py"))


def _imports(fichier: Path) -> set[str]:
    """Everything this file brings in, module AND imported name.

    Picking up only the module would let `from yangmap import bundles`
    through: the module there is `yangmap`, and it's the *name* that carries
    the violation. This defect was found by deliberately breaking the test —
    without which criterion A4 would have protected nothing.
    """
    arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
    noms: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.update(a.name.split(".")[0] for a in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module:
            noms.add(noeud.module.split(".")[0])
            noms.add(noeud.module)
            noms.update(a.name for a in noeud.names)
    return noms


@pytest.mark.parametrize("fichier", _modules(), ids=lambda p: p.name)
def test_aucun_module_hors_bundles_ne_peut_atteindre_le_reseau(fichier: Path):
    """A1 — no network socket at runtime."""
    if fichier.name in MODULES_RESEAU:
        pytest.skip("installation module, allowed to leave the process")
    fautifs = _imports(fichier) & INTERDITS_RESEAU
    assert not fautifs, f"{fichier.name} imports {fautifs}"


@pytest.mark.parametrize("fichier", _modules(), ids=lambda p: p.name)
def test_aucun_module_n_importe_de_bibliotheque_de_secrets(fichier: Path):
    """A2 — yangmap has no reason to know a password."""
    fautifs = _imports(fichier) & INTERDITS_SECRETS
    assert not fautifs, f"{fichier.name} imports {fautifs}"


def test_le_serveur_n_importe_ni_bundles_ni_indexer():
    """A4 — downloading can't be triggered by a tool call.

    If `server.py` could reach `bundles`, a model could trigger network
    access from a tool. The guarantee rests on that code path not existing.
    """
    importes = _imports(PAQUET / "server.py")
    assert "bundles" not in importes
    assert "indexer" not in importes

    # The API the server uses must not lead there either.
    importes_api = _imports(PAQUET / "api.py")
    assert "bundles" not in importes_api
    assert "indexer" not in importes_api


def test_le_serveur_n_a_pas_besoin_de_pyang():
    """A5 — the server starts without the build dependency.

    pyang is only declared in the `build` extra. If `server` or `api`
    depended on it, a minimal install wouldn't start.
    """
    for module in ("server.py", "api.py", "search.py", "index.py", "resolve.py"):
        assert "pyang" not in _imports(PAQUET / module), module


def test_aucun_module_ne_lit_un_inventaire():
    """A3 — yangmap ignores everything about an equipment fleet."""
    for fichier in _modules():
        texte = fichier.read_text(encoding="utf-8").lower()
        assert "inventory" not in texte or fichier.name in {"server.py", "api.py"}, (
            f"{fichier.name} mentions an inventory"
        )
