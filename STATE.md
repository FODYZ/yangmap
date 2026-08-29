# État & Spécifications du Projet — yangmap

> 🛡️ **Fiche Mémoire Anti AI-Slop** : Tout agent IA ou développeur reprenant ce dépôt DOIT respecter scrupuleusement les invariants ci-dessous.

---

## 1. Rôle & Objectif

Serveur **MCP** qui répond à « quel chemin YANG/gNMI porte quelle information, dans quelle version d'OS » : résolution de chemins YANG, indexation d'un arbre de configuration, validation (`yang_valider`). Consommé par `netlive-mcp` (`netlive/` l'importe).

- **Stack** : **Python 3.11+**, `mcp` (seule dépendance runtime). `pyang` est **uniquement nécessaire pour construire l'index** (`build` deps), pas pour faire tourner le serveur. Entrée CLI : `yangmap = "yangmap.cli:main"`.
- **Ports / endpoints** : serveur MCP (`yangmap.serveur_mcp`), pas de port HTTP autonome.

## 2. Ce qui a été fait

- Noyau + serveur MCP + jeu d'or à 100 % (`5aadcd6`).
- Arbre de configuration indexé et `yang_valider` (`541c308`) ; le « G6 tranche » : YangMap est décisif sur un chemin obscur, coûteux s'il ne sert pas (`febdbbd`).
- Retrait de tout ce qui liait le dépôt à un seul lab (`5145fc1`) ; licence MIT (`5145fc1`).
- Cahier de critères : 41 tenus, 2 partiels, 0 non tenus (`a7b5799`) ; golden set de 100 %.

## 3. En cours

- Rien de bloquant. Le dépôt est livré et validé par le golden set.

## 4. Prochaine action

Reconstruire l'index YANG avec `pyang` après modification d'un module YANG, puis rejouer `.venv/bin/python -m pytest -q` pour confirmer que le golden set reste à 100 %.

## 5. Commandes clés

- **Tests** :
  ```bash
  .venv/bin/python -m pytest -q
  ```
  → `105 passed, 3 skipped`.
- **Construire l'index** (nécessite `pyang`) :
  ```bash
  uv run --with pyang <commande d'indexation>
  ```
  (`pyang` n'est nécessaire qu'au build, pas au runtime — ne pas l'ajouter aux deps du serveur).

## 6. Pièges connus

- **`pyang` ne sert qu'au build de l'index** : l'ajouter via `--with pyang` ponctuellement, jamais dans les deps runtime (critère A5 : zéro dépendance lourde au runtime).
- **Golden set** : le recalibrer uniquement avec une reason écrite (convention de la suite).
- **`yangmap` est décisif pour `netlive`** : un changement de contrat ici peut casser `netlive` — rejuyer les deux suites.

## 7. Invariants

1. **Pas de régression de build** : rejouer `.venv/bin/python -m pytest -q` (`105 passed`) et garder le golden set à 100 % avant de commiter.
2. **Pas de credentials en dur** : jamais de clés ni de `.env` dans l'index YANG.
3. **Respect de l'architecture existante** : zéro dépendance lourde au runtime (`pyang` = build seulement).

---

*Dernière mise à jour : 2026-08-29 (fiche réelle, générée depuis `README.md` + `AGENTS.md` + `pyproject.toml` + `git log`, vérifiée : `.venv/bin/python -m pytest -q` → 105 passed, 3 skipped).*
