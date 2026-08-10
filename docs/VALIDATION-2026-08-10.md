# Déroulé du cahier de critères — 2026-08-10

> Référentiel : [`CRITERES-VALIDATION.md`](CRITERES-VALIDATION.md)
> Matériel : containerlab réel (`sros-lab-01` SR OS 24.3.R3 en gNMI,
> `ceos-lab-01` EOS 4.32.11M en gNMI activé pour cette campagne,
> `csr-lab-01` IOS-XE 17.3.4a).
> Modèle : Qwen3.6 27B Q5 en local, via l'Ollama du homelab.

## Verdict

| | |
|---|---|
| ✅ Tenus | **42** |
| ⚠️ Partiels | **1** |
| ❌ Non tenus | **0** |
| **Total** | **43** |

| Suite | Tests |
|---|---|
| yangmap, hors lab | **91** ✅ |
| yangmap, index réels (`build`) | **3** ✅ |
| yangmap, containerlab réel (`lab`) | **9** ✅ |
| netlive, hors lab | **359** ✅ (dont **15 ajoutés** par cette campagne) |
| netlive, containerlab réel | **13** ✅ |

## A — La frontière fondatrice

| # | Critère | État | Preuve |
|---|---|---|---|
| A1 | Aucun socket réseau à l'exécution | ✅ | Test AST sur les 9 modules. **Confirmé par accident** : le venv yangmap n'a pas `pygnmi`, les tests lab ont dû tourner depuis celui de netlive |
| A2 | Aucune bibliothèque de secrets | ✅ | Test AST, 9 modules |
| A3 | Aucun inventaire lu | ✅ | Revue + test textuel |
| A4 | Le téléchargement n'est pas atteignable depuis un outil | ✅ | `server.py` et `api.py` n'importent ni `bundles` ni `indexer`. **Test mis en échec volontairement** — voir ci-dessous |
| A5 | Démarre sans réseau | ✅ | pyang absent des dépendances d'exécution ; suite hors ligne verte |

**A4 ne protégeait rien avant d'être mis en échec.** `from yangmap import bundles`
passait : l'extracteur d'AST relevait le *module* (`yangmap`) et jamais le *nom
importé* (`bundles`). Corrigé, puis vérifié rouge avant d'être vérifié vert.

## B — Ingestion et index

| # | Critère | État | Mesure |
|---|---|---|---|
| B1 | Nokia : 0 erreur, > 50 000 chemins | ✅ | **50 772 chemins**, 1/1 modèle, 5 s |
| B2 | Cisco IOS-XE : 0 erreur | ✅ | **12 123 chemins**, 120/120 modèles |
| B3 | Arista/OpenConfig : 0 erreur | ✅ | **9 924 chemins**, 89/89 modèles |
| B4 | Schéma complet par entrée | ✅ | xpath, chemin gNMI, genre, type, description, module, clés, profondeur |
| B5 | Construction idempotente | ✅ | Double construction : même compte, table FTS5 non dupliquée |
| B6 | Un modèle cassé n'emporte pas les autres | ✅ | Injection d'un YANG invalide : le valide est indexé, l'échec rapporté |
| B7 | Aucun CSV intermédiaire ne subsiste | ✅ | Contrôle du répertoire |

Couverture des descriptions mesurée sur les index réels : **98 % / 97 % / 100 %**.

## C — Normalisation des chemins

| # | Critère | État | Note |
|---|---|---|---|
| C1 | Préfixe de module retiré de chaque segment | ✅ | |
| C2 | Préfixe en milieu de chemin | ✅ | **Tranché par le matériel**, pas par le raisonnement — voir ci-dessous |
| C3 | Clés marquées `=?` | ✅ | |
| C4 | Clés multiples toutes conservées | ✅ | Cas réel `[ip-address][mac-address][pppoe-session-id]` |
| C5 | xpath canonique conservé | ✅ | |
| C6 | Normalisation pure | ✅ | |

**C2 — la spec affirmait le contraire de ce que fait le code.** Elle disait le
préfixe « conservé » ; l'implémentation le retire. Testé sur `ceos-lab-01` :
les **deux formes sont acceptées** par le vrai équipement. Retirer est donc
sûr, et la spec a été corrigée d'après la mesure.

## D — Résolution de version et mode dégradé

| # | Critère | État | Mesure sur les vrais bundles |
|---|---|---|---|
| D1 | Version exacte servie | ✅ | Nokia 24.3.R3 → `24.3.3`, écart `exact` |
| D2 | Même train, écart déclaré | ✅ | Cisco 17.3.**4a** → `17.3.1` |
| D3 | Train absent, avertissement fort | ✅ | Testé unitairement |
| D4 | Plateforme inconnue, aucun repli | ✅ | BLOQUANT tenu |
| D5 | Message qui nomme la commande | ✅ | |
| D6 | Aucun écart dissimulé | ✅ | Arista 4.32.**11M** → `4.32.2`, écart `meme_train` déclaré — **et le chemin marche quand même sur le vrai matériel** |

Le repli est bien le **cas normal sur deux vendeurs sur trois**, comme la
reconnaissance l'annonçait.

## E — Recherche et classement

| # | Critère | État | Mesure |
|---|---|---|---|
| E1 | Recherche < 1 s | ✅ | **3 à 100 ms** sur 50 772 chemins |
| E2 | Description **et** segments cherchés | ✅ | Testé dans les deux sens |
| E3 | Terme absurde ⇒ rien, jamais d'approximation | ✅ | BLOQUANT tenu |
| E4 | **≥ 80 % du jeu d'or dans le top 5** | ✅ | **100 % (21/21)** |
| E5 | ≥ 15 entrées, 3 plateformes | ✅ | 21 entrées : 11 Nokia, 5 Cisco, 5 Arista |
| E6 | Chemins attendus vérifiés présents | ✅ | Sondés dans l'index avant inscription |
| E7 | Les 4 échecs de spec §3.4 corrigés | ✅ | Tous au jeu d'or |
| E8 | Score rendu | ✅ | |
| E9 | Limite respectée, plafonnée à 50 | ✅ | |
| E10 | Tout signal sans effet est retiré | ✅ | **Deux signaux retirés** |

**Progression du classement : 65 % → 95 % → 100 %.**

| Signal neutralisé | Taux | Delta | Verdict |
|---|---|---|---|
| BM25 descriptions | 76 % | −24 % | utile |
| BM25 segments | 86 % | −14 % | utile |
| Correspondance exacte de segment | 90 % | −10 % | utile |
| Pénalité de profondeur | 95 % | −5 % | utile |

**Deux signaux essayés puis retirés** faute d'effet mesurable à *aucun* poids :
la bonification des feuilles, et la couverture des termes. E10 interdit de les
garder « au cas où ».

**Deux entrées du jeu d'or ont été corrigées parce qu'elles encodaient une
erreur de l'auteur**, pas un défaut du code : l'adjacence ISIS vit sous
`interface[]/adjacency` (le code l'avait trouvée au rang 3, c'est le motif
attendu qui était faux — repris d'un commentaire netlive périmé), et « routes
actives et inactives » ne nomme aucune famille d'adressage, donc exiger
`unicast` testait une intention absente de la question.

## F — Contrat MCP

| # | Critère | État | Mesure |
|---|---|---|---|
| F1 | Exactement deux outils | ✅ | `yang_chercher`, `yang_detail` |
| F2 | Enfants **immédiats**, pas le sous-arbre | ✅ | |
| F3 | Clés à fournir rendues | ✅ | |
| F4 | Chemin inconnu ⇒ erreur claire | ✅ | Oriente vers `yang_chercher` |
| F5 | Descriptions courtes | ✅ | **< 600 caractères** par outil |
| F6 | stdio JSON-RPC non corrompu | ✅ | Vrai sous-processus, `initialize` complet |
| F7 | JSON valide à `limite=50` | ✅ | |

## G — Usage réel par netlive

| # | Critère | État | Preuve sur le lab |
|---|---|---|---|
| G1 | Chemins acceptés par la policy netlive | ✅ | > 10 chemins par plateforme, tous `allow` |
| G2 | Un chemin interroge vraiment l'équipement | ✅ | `/interfaces/interface[name=Ethernet1]/state/oper-status` → **`UP`** |
| G3 | Le manque `route_table` du HANDOFF est refermé | ✅ | `direct 3/3, host 0/2, isis 1/1` — **`host` porte 2 routes disponibles pour 0 active** |
| G4 | Aucun chemin ne franchit le plancher | ✅ | BLOQUANT tenu, 5 sujets × 2 plateformes |
| G5 | Version issue de `Capabilities` réelle | ✅ | `nokia-state` lu sur l'équipement, pilote le bundle |
| G6 | Le modèle trouve ce qu'il ne trouvait pas | ✅ | **Décisif sur un chemin obscur** : 0/2 en 12 appels sans, **2/2 en 3 appels avec**. Neutre à coûteux ailleurs — voir ci-dessous |
| G7 | Contexte de base non gonflé | ✅ | < 1 200 caractères pour les 2 outils |

### Le défaut sérieux trouvé en confrontant les deux outils

Un chemin recopié avec sa clé en gabarit — `[router-name=?]` — était **accepté
par la policy, envoyé à l'équipement**, qui répondait une valeur vide. Le noyau
la traduisait en `not_configured`, c'est-à-dire, pour le modèle, « cette
fonction n'est pas activée » — un statut que le prompt système lui ordonne de
tenir pour un **FAIT**.

**Une clé oubliée devenait une conclusion fausse et assurée.**

Corrigé des deux côtés :

| Côté | Correction |
|---|---|
| netlive | Une clé `=?` est refusée **sans que l'équipement soit contacté** — `denied` en 0 ms, vérifié sur `sros-lab-01`. Le motif dit comment corriger |
| yangmap | `action_requise` émis dès qu'un résultat porte des clés |

### G6 — ce que la campagne a réellement montré

La question de référence est celle qui a échoué le 2026-08-10 : « combien de
routes actives et inactives sur `sros-lab-01` ». Trois passes :

| Passe | SANS yangmap | AVEC yangmap |
|---|---|---|
| 1 — état initial | échec : `denied` en boucle | échec : appelle yangmap, puis retombe en CLI |
| 2 — après le garde-fou des clés | échec | échec |
| 3 — après la description par transport | ✅ **chiffres corrects** | ✅ **chiffres corrects** |

**C'est le correctif de description qui a débloqué, pas yangmap.** Rien ne
disait au modèle qu'un équipement gNMI refuse toute CLI ; il dépensait ses
appels en reformulations `show router route-table …` toutes refusées, puis
concluait « je ne peux pas répondre ». Une fois informé de la *forme* attendue,
il a retrouvé le chemin Nokia de lui-même — sans yangmap.

C'est un résultat honnête et utile : **sur les chemins que le modèle connaît
déjà, yangmap n'apporte rien.**

### La batterie qui tranche G6

Trois questions de difficulté croissante, vérité terrain relevée par gNMI
direct **avant** la campagne, six passes complètes :

| Question | Config | Valeurs attendues trouvées | Appels | yangmap appelé | Durée |
|---|---|---|---|---|---|
| **Q1** transceiver du port 1/1/c1 | SANS | **0/2** | **12** (budget épuisé) | — | **476 s** |
| | AVEC | **2/2** | **3** | oui | **38 s** |
| **Q2** prefix-SID ISIS | SANS | 2/2 | 1 | — | 22 s |
| | AVEC | 2/2 | 2 | **non** | 30 s |
| **Q3** sessions LDP (réponse négative) | SANS | — correct | 6 | — | 123 s |
| | AVEC | — correct | 9 | oui | 216 s |

**Q1 est le cas où yangmap est décisif.** Sans lui, le modèle a inventé des
chemins Nokia plausibles et inexistants — `/state/optical-module` (trois fois),
`/state/interface`, `/state/transceiver`, `/components` — a épuisé ses douze
appels, et a conclu qu'il n'avait aucune information. **Huit minutes et douze
approbations humaines pour rien.** Avec yangmap : trois appels, trente-huit
secondes, `qsfp` et `1302 nm`, exacts.

**Q2 montre la limite.** `segment_routing` est un collecteur nommé du
catalogue : le modèle l'a utilisé directement et n'a même pas appelé yangmap.
Bon réflexe — mais l'appel supplémentaire à `netlive_instances` a coûté 8 s de
plus.

**Q3 montre le coût quand yangmap ne sert pas.** Réponse correcte des deux
côtés, mais 9 appels et 216 s avec, contre 6 et 123 s sans : l'exploration
supplémentaire est du gaspillage sur une question dont la réponse est négative.

**Conclusion — G6 ✅, avec sa nuance :** yangmap est décisif là où aucun
collecteur nommé n'existe et où le chemin est obscur. Il est neutre quand le
catalogue couvre déjà le besoin, et **coûteux quand il ne sert pas**. Il
complète le catalogue, il ne le remplace pas.

## H — Reproductibilité

| # | Critère | État | Mesure |
|---|---|---|---|
| H1 | `fetch` puis `build` depuis rien | ✅ | Arista depuis un répertoire vide : **3,2 s + 2,3 s** |
| H2 | Bundles et index non versionnés | ✅ | `.gitignore` + `git ls-files` |
| H3 | Chiffres du README exacts | ✅ | Repris des mesures ci-dessus |
| H4 | Chaque garantie du README a son test nommé | ✅ | 5 lignes, 5 tests |
| H5 | Suite hors matériel et hors réseau | ✅ | 91 tests, marques `lab`/`build` séparées |

## Ce qui reste ouvert

| # | État | Décision |
|---|---|---|
| E4 | ⚠️ | 100 % sur 21 cas est un bon signal, pas une preuve de généralité. Le jeu d'or grandira avec les échecs constatés — même logique que `netlive gaps` |

**Piste ouverte par Q3** : yangmap coûte des appels quand il ne sert pas. La
description de `yang_chercher` pourrait dire d'essayer d'abord les collecteurs
nommés. À mesurer avant d'écrire — c'est la discipline de ce projet.

## Effets de bord sur netlive

Trois changements, tous nés de la confrontation, tous couverts par des tests :

| Changement | Pourquoi |
|---|---|
| `LiaisonMultiple` | Plusieurs serveurs MCP présentés à l'agent comme un seul, sans toucher à la boucle |
| Clé `=?` refusée sans contact | Empêchait un faux `not_configured` — le défaut le plus grave de la campagne |
| `netlive_run` décrit par transport | Le modèle ignorait qu'un équipement gNMI refuse toute CLI |

**359 tests hors lab côté netlive (+15), 13 contre le lab, aucune régression.**
