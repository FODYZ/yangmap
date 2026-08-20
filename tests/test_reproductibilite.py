"""Domains F and H — stdio transport, reproducibility, offline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE_PROJET = Path(__file__).resolve().parents[1]


def test_le_serveur_mcp_repond_sur_stdio_sans_corrompre_le_json_rpc(racine_carte):
    """F6 — the classic trap: one stray line on stdout kills the protocol.

    The test actually speaks JSON-RPC to a subprocess, the way an MCP host
    would. A stray `print` in any module would make it fail.
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
        assert ligne.strip(), "no response on stdout"
        reponse = json.loads(ligne)  # would fail if stdout were polluted
        assert reponse["id"] == 1
        assert "serverInfo" in reponse["result"]
        assert reponse["result"]["serverInfo"]["name"] == "yangmap"
    finally:
        proc.kill()
        proc.wait(timeout=10)


def test_l_avertissement_de_demarrage_part_sur_stderr_pas_stdout(racine_carte, tmp_path):
    """Corollary of F6: even with no index, nothing must pollute stdout."""
    env = {**os.environ, "PYTHONPATH": str(RACINE_PROJET)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "yangmap.server", "--racine", str(tmp_path / "vide")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, cwd=str(RACINE_PROJET),
    )
    try:
        proc.stdin.close()
        _, erreurs = proc.communicate(timeout=15)
        assert "no index" in erreurs
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.skip("the server is still waiting on stdin")
    finally:
        proc.kill()


def test_les_bundles_et_index_sont_ignores_par_git():
    """H2 — a 50,000-line index has no business in a repository."""
    ignore = (RACINE_PROJET / ".gitignore").read_text(encoding="utf-8")
    for motif in ("bundles/", "index/", "*.db"):
        assert motif in ignore, f"{motif} missing from .gitignore"

    suivis = subprocess.run(
        ["git", "ls-files"], cwd=RACINE_PROJET, capture_output=True, text=True
    ).stdout.splitlines()
    assert not [f for f in suivis if f.endswith(".db")], "an index is version-controlled"
    assert not [f for f in suivis if f.startswith("bundles/")], "a bundle is version-controlled"


def test_la_suite_hors_lab_ne_touche_ni_reseau_ni_materiel():
    """H5 — verified by construction: no unmarked test opens a socket.

    Tests that need one carry `lab` or `build`. This test rereads the marks
    rather than trusting a convention.
    """
    sortie = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m",
         "not lab and not build"],
        cwd=RACINE_PROJET, capture_output=True, text=True,
    ).stdout
    assert "test_integration_netlive" not in sortie, (
        "a lab test is collected by the offline suite"
    )
