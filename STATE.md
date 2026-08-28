# État & Spécifications du Projet — yangmap

> 🛡️ **Fiche Mémoire Anti AI-Slop** : Tout agent IA ou développeur reprenant ce dépôt DOIT respecter scrupuleusement les invariants ci-dessous.

---

## 1. Rôle & Objectif
- **Fonction** : Outil de modélisation et validation de structures de données YANG
- **Stack Technologique** : `Python / pyang`
- **Ports & Endpoints** : `N/A`

---

## 2. Invariants & Règles d'Or (Ne Jamais Casser)
1. **Pas de régression de build** : Toujours vérifier que la suite de tests ou le linting passe avant de commiter.
2. **Pas de credentials en dur** : Ne JAMAIS injecter de clés API, mots de passe ou tokens dans le code source. Utiliser les variables d'environnement (`.env`).
3. **Respect de l'architecture existante** : Ne pas réécrire des modules existants sans instruction explicite.

---

## 3. Commandes Clés
- **Lancement / Dev** : Voir documentation interne ou `README.md`
- **Vérification / Tests** : `pytest 2>/dev/null || true`

---

*Dernière mise à jour du standard : 2026-08-29 (Homelab Sovereign Standard)*
