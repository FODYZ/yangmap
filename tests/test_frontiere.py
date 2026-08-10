"""Domaine A — la frontière fondatrice : aucun contact équipement.

Ces tests portent sur l'arbre syntaxique, pas sur le comportement : c'est
l'absence d'un chemin de code qui protège, pas une consigne. Un test de
comportement laisserait passer un import ajouté par mégarde.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAQUET = Path(__file__).resolve().parents[1] / "yangmap"

# `bundles` télécharge (git) et `indexer` lance pyang : ce sont les deux seuls
# modules autorisés à sortir du processus, et ni l'un ni l'autre n'est importé
# par le serveur.
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
    """Tout ce que ce fichier fait entrer, module ET nom importé.

    Ne relever que le module laisserait passer `from yangmap import bundles` :
    le module y est `yangmap`, et c'est le *nom* qui porte la violation. Ce
    défaut a été trouvé en mettant volontairement le test en échec — sans quoi
    le critère A4 n'aurait rien protégé.
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
    """A1 — aucun socket réseau à l'exécution."""
    if fichier.name in MODULES_RESEAU:
        pytest.skip("module d'installation, autorisé à sortir du processus")
    fautifs = _imports(fichier) & INTERDITS_RESEAU
    assert not fautifs, f"{fichier.name} importe {fautifs}"


@pytest.mark.parametrize("fichier", _modules(), ids=lambda p: p.name)
def test_aucun_module_n_importe_de_bibliotheque_de_secrets(fichier: Path):
    """A2 — yangmap n'a aucune raison de connaître un mot de passe."""
    fautifs = _imports(fichier) & INTERDITS_SECRETS
    assert not fautifs, f"{fichier.name} importe {fautifs}"


def test_le_serveur_n_importe_ni_bundles_ni_indexer():
    """A4 — le téléchargement ne peut pas être déclenché par un appel d'outil.

    Si `server.py` pouvait atteindre `bundles`, un modèle pourrait provoquer
    un accès réseau depuis un outil. La garantie tient à ce que le chemin de
    code n'existe pas.
    """
    importes = _imports(PAQUET / "server.py")
    assert "bundles" not in importes
    assert "indexer" not in importes

    # L'API que le serveur utilise ne doit pas non plus y mener.
    importes_api = _imports(PAQUET / "api.py")
    assert "bundles" not in importes_api
    assert "indexer" not in importes_api


def test_le_serveur_n_a_pas_besoin_de_pyang():
    """A5 — le serveur démarre sans la dépendance de construction.

    pyang n'est déclaré que dans l'extra `build`. Si `server` ou `api` en
    dépendaient, une installation minimale ne démarrerait pas.
    """
    for module in ("server.py", "api.py", "search.py", "index.py", "resolve.py"):
        assert "pyang" not in _imports(PAQUET / module), module


def test_aucun_module_ne_lit_un_inventaire():
    """A3 — yangmap ignore tout d'un parc d'équipements."""
    for fichier in _modules():
        texte = fichier.read_text(encoding="utf-8").lower()
        assert "inventory" not in texte, fichier.name
        assert "inventaire" not in texte or fichier.name in {"server.py", "api.py"}, (
            f"{fichier.name} mentionne un inventaire"
        )
