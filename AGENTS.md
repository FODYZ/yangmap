# Project agent memory

> **Les règles de travail sont dans [`AGENTS.md`](AGENTS.md)** — source unique
> pour Claude, Codex, Gemini et Hermes. L'état courant vit dans Pilot :
> `pilot open yangmap`.

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Naming: English prose, French API surface

The repo was translated to English prose in 2026-08 (README, docs, docstrings,
comments, CLI help, MCP tool descriptions), but **the actual API surface was
deliberately left in French**: the CLI subcommands `chercher`/`detail`, the
MCP tool names `yang_chercher`/`yang_detail`, the Python method names
(`Carte.chercher`, `search.chercher`), and every JSON/dict field returned to
callers (`plateforme`, `chemin`, `bundle_servi`, `version_demandee`, `ecart`,
`avertissement`, `resultats`, `cles`, `cles_a_fournir`, `noeud`, `enfants`,
`action_requise`). Do not rename these without checking for external
consumers first — `docs/VALIDATION-2026-08-10.md` documents a real one
(`netlive`) already calling `yang_chercher`/`yang_detail` by name. Renaming
the tool/CLI surface is a breaking API change, not a translation.

Also deliberately untranslated: `goldenset/golden.yaml`'s `question:` values
and the French test queries scattered in `tests/test_integration_netlive.py`
and `tests/test_search.py` — these exercise the French→English lexicon in
`yangmap/search.py::LEXIQUE`, which is real functionality (users query in
French, vendor YANG descriptions are in English), not leftover prose.

Tests that `pytest.raises(..., match="...")` or assert on substrings of
runtime messages are coupled to the (now English) error/print text in
`yangmap/*.py`. If you change a user-facing message, grep the test suite for
the old substring before assuming the tests still pass.

## Build/test

`pip install -e ".[dev]"` then `pytest -m "not lab"` (91 tests, offline).
`pytest -m build` needs `pyang` (in the `dev`/`build` extras) plus a real
downloaded bundle under `~/.yangmap` to do anything beyond the 3 synthetic
tests. `pytest -m lab` needs a real containerlab and `netlive` installed —
see `tests/test_integration_netlive.py`'s module docstring for the env vars.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.

## Pièges connus

Repris des anciens `STATE.md` et `HANDOFF.md` du dépôt, supprimés le 2026-09-04.
L'original reste dans l'historique Git.

- `pyang` ne doit être ajouté que ponctuellement via `uv run --with pyang` pour le build de l'index, jamais comme dépendance runtime (invariant critique pour éviter la régression de poids).
- Un changement de contrat de `yangmap` peut casser le consommateur `netlive`, exigeant le rejeu des suites de tests des deux dépôts.
- Le recalibrage du golden set est strictement réservé aux cas avec une reason écrite explicitement documentée.
- Aucune credential ni fichier `.env` ne doit être inclus dans l'index YANG généré.
