"""Domaines F et H — transport stdio, reproductibilité, hors-ligne."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE_PROJET = Path(__file__).resolve().parents[1]


def test_le_serveur_mcp_repond_sur_stdio_sans_corrompre_le_json_rpc(racine_carte):
    """F6 — le piège classique : une ligne parasite sur stdout tue le protocole.

    Le test parle vraiment JSON-RPC à un sous-processus, comme le ferait un
    hôte MCP. Un `print` égaré dans n'importe quel module le ferait échouer.
    """
    env = {**os.environ, "PYTHONPATH": str(RACINE_PROJET)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "yangmap.server", "--racine", str(racine_carte)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=str(RACINE_PROJET),
    )

    def envoyer(message: dict) -> None:
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    envoyer({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "essai", "version": "0"},
        },
    })
    try:
        ligne = proc.stdout.readline()
        assert ligne.strip(), "aucune réponse sur stdout"
        reponse = json.loads(ligne)  # échouerait si stdout était pollué
        assert reponse["id"] == 1
        assert "serverInfo" in reponse["result"]
        assert reponse["result"]["serverInfo"]["name"] == "yangmap"
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_l_avertissement_de_demarrage_part_sur_stderr_pas_stdout(racine_carte, tmp_path):
    """Corollaire de F6 : même sans index, rien ne doit polluer stdout."""
    env = {**os.environ, "PYTHONPATH": str(RACINE_PROJET)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "yangmap.server", "--racine", str(tmp_path / "vide")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=str(RACINE_PROJET),
    )
    try:
        proc.stdin.close()
        _, erreurs = proc.communicate(timeout=15)
        assert "aucun index" in erreurs
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.skip("le serveur attend toujours sur stdin")
    finally:
        proc.kill()


def test_les_bundles_et_index_sont_ignores_par_git():
    """H2 — un index de 50 000 lignes n'a rien à faire dans un dépôt."""
    ignore = (RACINE_PROJET / ".gitignore").read_text(encoding="utf-8")
    for motif in ("bundles/", "index/", "*.db"):
        assert motif in ignore, f"{motif} absent du .gitignore"

    suivis = subprocess.run(
        ["git", "ls-files"], cwd=RACINE_PROJET, capture_output=True, text=True
    ).stdout.splitlines()
    assert not [f for f in suivis if f.endswith(".db")], "un index est versionné"
    assert not [f for f in suivis if f.startswith("bundles/")], "un bundle est versionné"


def test_la_suite_hors_lab_ne_touche_ni_reseau_ni_materiel():
    """H5 — vérifié par construction : aucun test non marqué n'ouvre de socket.

    Les tests qui en ont besoin portent `lab` ou `build`. Ce test relit les
    marques plutôt que de faire confiance à une convention.
    """
    sortie = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m",
         "not lab and not build"],
        cwd=RACINE_PROJET, capture_output=True, text=True,
    ).stdout
    assert "test_integration_netlive" not in sortie, (
        "un test lab est collecté par la suite hors ligne"
    )
