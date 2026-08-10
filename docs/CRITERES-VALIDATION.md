# Cahier de critères de validation — yangmap

> Établi le 2026-08-10 à partir de
> [`docs/superpowers/specs/2026-08-10-yangmap-design.md`](superpowers/specs/2026-08-10-yangmap-design.md).
> Même discipline que le cahier de `net-ai-copilot` : un critère n'est pas une
> reformulation de la spec, c'est un **énoncé falsifiable** accompagné du moyen
> de le contredire.

## Comment lire ce cahier

| Niveau | Sens |
|---|---|
| **BLOQUANT** | Un échec invalide une garantie annoncée. Ne pas livrer. |
| **MAJEUR** | Un échec dégrade une propriété centrale sans rompre la frontière fondatrice. |
| **MINEUR** | Écart de confort, de documentation ou de complétude. |

Quand aucune vérification mécanique n'est possible, c'est écrit. Une revue
déclarée vaut mieux qu'une preuve imaginaire.

---

## A — La frontière fondatrice : aucun contact équipement

C'est ce qui rend yangmap publiable et réutilisable. Si A tombe, le projet
change de nature.

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| A1 | Aucun module du serveur n'ouvre de socket réseau à l'exécution | BLOQUANT | Test AST : aucun import de `socket`, `http*`, `requests`, `httpx`, `grpc`, `paramiko`, `scrapli`, `pygnmi` hors du module de téléchargement de bundles |
| A2 | Aucun module n'importe `keyring` ni aucune bibliothèque de secrets | BLOQUANT | Test AST sur toute l'arborescence |
| A3 | Le serveur ne lit aucun fichier d'inventaire, ni aucun fichier hors `bundles/` et son index | BLOQUANT | Revue de code déclarée + test des chemins ouverts |
| A4 | Le téléchargement de bundles est **une commande séparée**, jamais déclenchée par un appel d'outil MCP | BLOQUANT | Test : aucun chemin de code du serveur n'appelle le module de téléchargement |
| A5 | Le serveur démarre et répond sans aucun accès réseau | MAJEUR | Exécution de la suite avec le réseau coupé |

## B — Ingestion et construction de l'index

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| B1 | Un bundle Nokia s'indexe avec **0 erreur pyang** et produit > 50 000 chemins | MAJEUR | Construction réelle, comptage |
| B2 | Un bundle Cisco IOS-XE (`*-oper`) s'indexe avec 0 erreur | MAJEUR | Idem |
| B3 | Un bundle Arista/OpenConfig s'indexe avec 0 erreur | MAJEUR | Idem |
| B4 | Chaque entrée d'index porte : xpath canonique, chemin gNMI, genre de nœud, type, description, module d'origine | MAJEUR | Contrôle de schéma sur la base construite |
| B5 | La construction est **idempotente** : reconstruire un bundle déjà indexé donne le même nombre d'entrées | MAJEUR | Double construction, comparaison |
| B6 | Une erreur pyang sur un modèle n'interrompt pas l'indexation des autres, et est **rapportée** | MAJEUR | Injection d'un fichier YANG invalide |
| B7 | L'index se construit sans que le CSV intermédiaire subsiste | MINEUR | Contrôle du répertoire après construction |

## C — Normalisation des chemins

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| C1 | Le préfixe de module du **premier** segment est retiré (`/nokia-state:state/…` ⟶ `/state/…`) | MAJEUR | Tests unitaires |
| C2 | Un préfixe de module **en milieu de chemin** est **conservé** (cas OpenConfig) | MAJEUR | Test dédié sur `…/state/openconfig-platform-transceiver:transceiver` |
| C3 | Les clés de liste sont marquées comme attendant une valeur (`[router-name]` ⟶ `[router-name=?]`) | MAJEUR | Tests unitaires |
| C4 | Une liste à clés multiples conserve **toutes** ses clés | MAJEUR | Test sur `[ip-address][mac-address][pppoe-session-id]` |
| C5 | Le xpath canonique est conservé intact à côté du chemin gNMI | MAJEUR | Contrôle de schéma |
| C6 | La normalisation est pure : mêmes entrées, mêmes sorties, sans état | MINEUR | Revue + tests |

## D — Résolution de version et mode dégradé

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| D1 | Version exacte disponible ⟹ elle est servie, écart nul déclaré | MAJEUR | Test : Nokia 24.3.R3 |
| D2 | Version absente, même train ⟹ le plus proche du train, **écart déclaré dans la réponse** | MAJEUR | Test : Cisco 17.3.4a ⟶ 17.3.1 |
| D3 | Train absent ⟹ le train le plus proche, écart déclaré avec un avertissement plus fort | MAJEUR | Test : Arista 4.32.11M ⟶ 4.32.x |
| D4 | Plateforme inconnue ⟹ erreur explicite, **aucun repli sur un autre vendeur** | BLOQUANT | Test dédié |
| D5 | Aucun bundle installé pour une plateforme ⟹ message qui nomme la commande à jouer | MAJEUR | Test dédié |
| D6 | Une réponse ne dissimule **jamais** un écart de version | BLOQUANT | Toute réponse porte le bundle servi ; test sur les trois cas D1–D3 |

## E — Recherche et classement

Le cœur du projet. E4 décide de sa valeur.

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| E1 | Une recherche sur un index Nokia rend un résultat en moins d'une seconde | MINEUR | Mesure |
| E2 | La recherche porte sur la description **et** sur les segments du chemin | MAJEUR | Test : un terme présent uniquement dans le chemin est trouvé, et réciproquement |
| E3 | Un terme sans aucun résultat rend une liste vide et le **dit** — jamais un chemin approximatif | BLOQUANT | Test avec un terme absurde |
| E4 | **≥ 80 % des entrées du jeu d'or placent le chemin attendu dans les 5 premiers** | MAJEUR | Exécution du jeu d'or |
| E5 | Le jeu d'or compte au moins 15 entrées et couvre les trois plateformes | MAJEUR | Comptage |
| E6 | Chaque chemin attendu du jeu d'or est **vérifié présent dans l'index** avant d'y figurer | MAJEUR | Test de cohérence du jeu d'or lui-même |
| E7 | Les quatre échecs de classement documentés en spec §3.4 sont corrigés | MAJEUR | Ils font partie du jeu d'or |
| E8 | Le score est rendu au client, pour qu'un résultat faible soit reconnaissable | MINEUR | Contrôle de la réponse |
| E9 | La limite demandée est respectée et plafonnée à 50 | MINEUR | Tests de bornes |
| E10 | Retirer un signal de classement dégrade mesurablement le jeu d'or, ou le signal est retiré du code | MAJEUR | Mesure par ablation, un signal à la fois |

## F — Contrat MCP

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| F1 | Le serveur expose exactement deux outils : `yang_chercher` et `yang_detail` | MAJEUR | Interrogation d'un vrai client MCP |
| F2 | `yang_detail` rend les **enfants immédiats** d'un conteneur, pas son sous-arbre entier | MAJEUR | Test sur `/state/port[port-id]/transceiver` |
| F3 | `yang_detail` rend les clés à fournir pour atteindre le chemin | MAJEUR | Test sur un chemin à clés multiples |
| F4 | `yang_detail` sur un chemin inconnu rend une erreur claire, jamais un résultat vide silencieux | MAJEUR | Test dédié |
| F5 | Les descriptions d'outils ne répètent pas l'inventaire des plateformes à chaque outil | MINEUR | Mesure de la taille des descriptions |
| F6 | Les journaux du serveur ne corrompent pas le JSON-RPC sur stdio | MAJEUR | Test d'un échange complet sur stdio |
| F7 | Une réponse est du JSON valide quelle que soit la taille du résultat | MAJEUR | Test sur `limite=50` |

## G — Usage réel par netlive

Ce que le cahier de netlive ne peut pas couvrir, et qui est la raison d'être du
projet.

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| G1 | Un chemin rendu par `yang_chercher` est **accepté par la policy** de netlive, sans modification | BLOQUANT | Chemins du jeu d'or passés à `Policy.evaluate_request` |
| G2 | Un chemin rendu, complété de ses clés, **interroge réellement** l'équipement du lab et rend une donnée | BLOQUANT | Test bout en bout contre le containerlab |
| G3 | Le chemin `route-table` trouvé par yangmap referme le manque documenté au HANDOFF du 2026-08-10 | MAJEUR | Collecte réelle sur `sros-lab-01`, routes actives et inactives rendues |
| G4 | Un chemin rendu par yangmap ne contourne **jamais** le plancher de sécurité de netlive | BLOQUANT | Aucun chemin du jeu d'or n'est un verbe d'écriture ; test dédié |
| G5 | La version passée à yangmap provient de `Capabilities` réellement lue sur l'équipement | MAJEUR | Test lab : `GnmiTransport.capabilities()` ⟶ version ⟶ `yang_chercher` |
| G6 | Un modèle disposant de yangmap trouve un chemin qu'il ne trouvait pas sans | MAJEUR | Comparaison avec / sans, sur les mêmes questions |
| G7 | L'ajout de yangmap n'augmente pas le contexte de base de plus de ce qu'annonce la spec | MINEUR | Mesure de la taille des descriptions d'outils |

## H — Reproductibilité et documentation

| # | Critère | Niveau | Vérification |
|---|---|---|---|
| H1 | `yangmap fetch` puis `yangmap build` reconstruisent un index depuis rien, d'une commande chacun | MAJEUR | Exécution depuis un répertoire vide |
| H2 | Les bundles et les index ne sont pas versionnés dans git | MAJEUR | Contrôle du `.gitignore` et de l'index git |
| H3 | Les chiffres publiés dans le README sont exacts | MINEUR | Exécution de la suite |
| H4 | Chaque garantie annoncée au README est tenue par un test **nommé dans le README** | BLOQUANT | Confrontation ligne à ligne |
| H5 | La suite complète tourne sans matériel et sans réseau | MAJEUR | Exécution hors ligne |

---

## Ce que ce cahier ne couvre pas, volontairement

- **La qualité des descriptions du vendeur.** yangmap les sert, ne les réécrit
  pas. Une description pauvre reste pauvre, et aucun critère ne peut l'exiger
  autrement.
- **L'exhaustivité de la couverture YANG.** On ne prouve pas que tout chemin
  utile est trouvable. E4 mesure le classement sur un échantillon assumé.
- **La qualité du raisonnement du modèle.** Trouver le bon chemin n'est pas
  conclure juste. G6 mesure que le chemin est trouvé, pas que le diagnostic est
  bon.
- **Les performances au-delà de E1.** Aucun budget de latence n'est fixé par la
  spec.
- **La complétude du jeu d'or.** Quinze entrées est un plancher. Il grandira
  avec les échecs constatés à l'usage — même logique que `netlive gaps`.
