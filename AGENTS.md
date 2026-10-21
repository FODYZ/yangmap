# AGENTS.md — yangmap

Serveur MCP hors ligne qui dit quel chemin gNMI porte quelle information, par
vendeur et version d'OS, à partir du YANG publié. Ne se connecte à aucun
équipement : pas de credentials, pas d'inventaire, pas de socket. Page wiki :
[[yangmap]].

## Commandes

- Installation : `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- `.venv/bin/python -m pytest -m "not lab"` — la suite hors ligne, avant tout
  commit.
- `pytest -m build` — nécessite `pyang` (extras `dev`/`build`) et un bundle
  téléchargé sous `~/.yangmap`.
- `pytest -m lab` — nécessite un containerlab réel et `netlive` installés
  (variables d'environnement dans le docstring de
  `tests/test_integration_netlive.py`).
- CLI : `yangmap fetch <plateforme> <version>` (la seule commande qui touche
  le réseau), puis `yangmap build <plateforme>` (index, ensuite hors ligne).

## Fichiers et dossiers

- `yangmap/search.py` — recherche ; le lexique français → anglais
  (`LEXIQUE`) est une fonctionnalité, pas des reliquats.
- `goldenset/golden.yaml` — le jeu d'or.
- `docs/VALIDATION-2026-08-10.md` — le consommateur `netlive` appelle
  `yang_chercher`/`yang_detail` par leur nom.

## Pièges et accords

- **Surface API volontairement en français** : sous-commandes `chercher`/
  `detail`, outils MCP `yang_chercher`/`yang_detail`, champs JSON
  (`plateforme`, `chemin`, `bundle_servi`, `ecart`, …). Ne pas renommer sans
  vérifier les consommateurs externes : c'est une cassure d'API, pas une
  traduction. Les `question:` du golden set et les requêtes de test en
  français non plus.
- Les tests qui matchent des sous-chaînes de messages sont couplés au texte
  (anglais) de `yangmap/*.py` : avant de changer un message, grep la suite de
  tests pour l'ancien substring.
- `pyang` s'ajoute ponctuellement via `uv run --with pyang` pour le build de
  l'index, jamais comme dépendance runtime (invariant de poids).
- Un changement de contrat peut casser `netlive` : rejouer les suites des deux
  dépôts.
- Le recalibrage du golden set exige une raison écrite documentée.
- Aucune credential ni fichier `.env` dans l'index YANG généré.
