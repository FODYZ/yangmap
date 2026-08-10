# yangmap — conception

> Spec établie le 2026-08-10, après une campagne de reconnaissance dont tous
> les chiffres cités ici ont été **mesurés**, pas estimés. La méthode de mesure
> est donnée à chaque fois, pour qu'on puisse la contredire.

## 1. Le problème

Un modèle de langage à qui l'on donne un accès gNMI en lecture ne sait pas
**où regarder**. Il connaît la syntaxe CLI par cœur et invente des chemins
YANG plausibles qui n'existent pas. Chaque invention coûte un appel d'outil,
une approbation humaine, et rend `not_configured` — un statut qui ressemble à
une réponse et n'en est pas une.

Constaté en conditions réelles sur `net-ai-copilot` : un agent interrogé sur
les routes actives et inactives d'un Nokia SR OS n'a trouvé aucun chemin, faute
de collecteur nommé, et a proposé une commande CLI refusée par construction.

Le manque n'est pas un manque d'autorisation — les policies ouvrent déjà tout
`/state`. C'est un manque de **carte**.

## 2. Ce que yangmap est, et n'est pas

**yangmap ne se connecte à aucun équipement.** Il ne détient aucun credential,
n'ouvre aucune session, n'émet aucune requête réseau à l'exécution. C'est un
serveur de *documentation*, pas de collecte.

Cette frontière est le cœur du design et non un détail d'implémentation :

| Conséquence | Pourquoi elle compte |
|---|---|
| Surface de sécurité nulle | Publiable en open source sans les précautions qu'un outil de collecte impose |
| Aucune donnée d'exploitant ne le traverse | Il ne voit que des schémas publics de vendeurs |
| Utilisable par n'importe qui | Il ne dépend d'aucun inventaire, d'aucun parc, d'aucune infrastructure |

Corollaire : **ce n'est pas yangmap qui appelle `Capabilities`.** L'appelant
(netlive, ou tout autre client) découvre la version de l'équipement et la
**passe en paramètre**. yangmap reste hors ligne et sans privilège.

## 3. Ce que la reconnaissance a mesuré

### 3.1 Les descriptions existent et sont exploitables

Mesure : comptage sur les fichiers YANG publiés, puis sur l'index généré.

| Vendeur | Chemins indexés | Portant une description | Descriptions distinctes |
|---|---|---|---|
| Nokia SR OS 24.3.R3 | 51 122 | 50 227 — **98 %** | 12 791 |
| Cisco IOS-XE 17.3.1 (`*-oper`) | 12 431 | 12 139 — **97 %** | 8 010 |
| Arista / OpenConfig 4.32.0F | 7 492 | 7 492 — **100 %** | 3 139 |

Sur Nokia, 1 511 des 12 791 descriptions distinctes sont du remplissage de
navigation (`Enter the <x> context`), soit **11 %**. Elles portent toutes sur
des conteneurs ; les feuilles — celles qui portent l'information — sont
documentées utilement.

Échantillon non choisi, pris tel quel dans `nokia-state` :

```
/state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/active-routes
    "Count of routes of a routing protocol active in the FIB."

/state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/available-routes
    "Count of routes of a routing protocol, both active in the FIB
     and inactive in the RIB."
```

C'est exactement la distinction actif/inactif qu'un ingénieur cherche, écrite
par le vendeur, versionnée avec l'OS.

### 3.2 La génération est un problème résolu

`pyang -f flatten --flatten-keys-in-xpath --flatten-type --flatten-description
--flatten-keyword` produit un CSV `xpath,keyword,type,description`.

| Vendeur | Temps | Erreurs |
|---|---|---|
| Nokia (`nokia-state.yang`, 15,5 Mo) | 3,7 s | 0 |
| Cisco (tous les `*-oper.yang`) | 1,5 s | 0 |
| Arista / OpenConfig (4 modèles) | 1,4 s | 0 |

**Il n'y a pas de parseur YANG à écrire.** C'est la partie que l'on aurait crue
coûteuse, et elle est gratuite.

### 3.3 Le volume interdit de tout servir

Les descriptions utiles distinctes de `nokia-state` pèsent 832 Ko, soit environ
**213 000 tokens**. Servir l'index en bloc est hors de question, quelle que
soit la fenêtre de contexte. **La recherche n'est pas un raffinement : c'est la
fonction.**

### 3.4 Le classement naïf ne marche pas — et c'est là qu'est tout le travail

Recherche par sous-chaîne, premiers résultats rendus :

| Question | Premier résultat brut | Verdict |
|---|---|---|
| « transceiver » (Nokia) | `/state/port[]/dwdm/coherent/rx-optical-snr-x-polarization` | hors sujet |
| « table de routage » (Nokia) | `/state/radius/route-downloader[]/statistics/routes-received-count` | hors sujet |
| « pppoe » (Nokia) | `/state/isa/nat-group[]/esa[][]/resources/pppoe-sessions` | hors sujet |
| « table de routage » (Arista) | `…/l2rib/mac-ip-table/entries/entry[][]/host-ip` | hors sujet |

Le chemin correct est présent dans l'index dans chacun de ces cas. **C'est un
défaut de classement, jamais un défaut de données.** Il se manifeste
identiquement sur les trois vendeurs : un seul moteur de classement les sert
donc tous.

La démonstration la plus nette est le PPPoE. Le grep rend d'abord des
compteurs de NAT et de wlan-gateway ; le chemin qu'un ingénieur veut est
celui-ci, et il porte exactement la séquence qu'on déroule quand les sessions
ne montent pas :

```
/state/service/vprn[]/subscriber-interface[]/group-interface[]/sap[]/pppoe/statistics/rx/
    padi                "Number of PADI (PPPoE Active Discovery Initiation) packets."
    padr                "Number of PADR (PPPoE Active Discovery Request) packets."
    padt                "Number of PADT (PPPoE Active Discovery Terminate) packets."
    dropped             "Number of dropped PPPoE packets."
    invalid-ac-cookie   "…invalid AC-Cookie tag."
    invalid-session     "…invalid session-id field."
```

Le PADI arrive-t-il ? Le PADR suit-il ? Qu'est-ce qui est rejeté, et pourquoi ?
La méthode de diagnostic est déjà dans le schéma du vendeur. Il ne manque que
de savoir où regarder — c'est-à-dire yangmap.

### 3.5 La version exacte n'est pas toujours publiée

| Vendeur | Version du matériel de référence | Bundle publié le plus proche |
|---|---|---|
| Nokia | 24.3.R3 | `sros_24.3.r3` — **exact** |
| Cisco | 17.3.4a | `1731` (17.3.1) — train seulement |
| Arista | 4.32.11M | `4.32.0F` / `1F` / `2F` — train seulement |

Le repli sur le bundle le plus proche est donc le **cas normal sur deux
vendeurs sur trois**, pas un cas limite. Il doit être annoncé dans la réponse,
jamais silencieux.

## 4. Architecture

```
bundles/<plateforme>/<version>/        YANG téléchargé, hors versionnement git
        │
        ▼
   ┌─────────────┐
   │  indexer    │  pyang -f flatten ──▶ normalisation ──▶ SQLite FTS5
   └─────────────┘
   ┌─────────────┐
   │  resolve    │  (plateforme, version) ──▶ quel bundle, exact ou approché
   └─────────────┘
   ┌─────────────┐
   │  search     │  BM25 + signaux de chemin ──▶ classement
   └─────────────┘
   ┌─────────────┐
   │  server     │  2 outils MCP
   └─────────────┘
```

`sqlite3` de la bibliothèque standard porte **FTS5 et `bm25()`**. Aucune
dépendance d'exécution. `pyang` n'est requis qu'à la construction de l'index.

### 4.1 Découpage en modules

| Module | Fait | Dépend de |
|---|---|---|
| `bundles.py` | Télécharge un bundle YANG (`git clone` peu profond sur le tag) | git |
| `indexer.py` | Lance pyang, normalise, écrit l'index SQLite | pyang, sqlite3 |
| `normalize.py` | xpath pyang ⟶ chemin gNMI | rien |
| `resolve.py` | (plateforme, version) ⟶ bundle, avec écart annoncé | rien |
| `search.py` | Requête ⟶ résultats classés | sqlite3 |
| `server.py` | Expose les deux outils MCP | tous les précédents |

`normalize.py`, `resolve.py` et `search.py` ne dépendent de rien d'autre que de
la bibliothèque standard : ils se testent sans réseau, sans YANG et sans MCP.

## 5. Normalisation des chemins

pyang rend un xpath préfixé par le module et sans valeur de clé. Un client gNMI
a besoin d'autre chose. La transformation est déterministe :

```
pyang     /nokia-state:state/router[router-name]/route-table/unicast/ipv4
gNMI      /state/router[router-name=?]/route-table/unicast/ipv4
```

Deux règles, et rien de plus :

1. Retirer le préfixe de module du premier segment (`nokia-state:state` ⟶ `state`).
2. Marquer les clés attendues (`[router-name]` ⟶ `[router-name=?]`), pour que le
   consommateur sache qu'une valeur doit être fournie.

L'index conserve **les deux formes** : le xpath canonique, qui est l'identité du
nœud dans le schéma, et le chemin gNMI, qui est ce que le modèle doit recopier.

Un préfixe de module apparaissant **au milieu** d'un chemin (cas OpenConfig,
`…/state/openconfig-platform-transceiver:transceiver`) est conservé tel quel :
il fait partie du chemin réel et le retirer casserait la requête.

## 6. Les deux outils MCP

### `yang_chercher`

| Paramètre | Sens |
|---|---|
| `sujet` | Ce que l'on cherche, en langage naturel ou en mots-clés |
| `plateforme` | `nokia_sros`, `cisco_iosxe`, `arista_eos` |
| `version` | Version d'OS. Facultative — sans elle, le bundle par défaut de la plateforme |
| `limite` | Nombre de résultats, 10 par défaut, 50 au maximum |

Rend, par résultat : le chemin gNMI, le xpath canonique, le genre de nœud
(`leaf`, `container`, `list`), le type de donnée, la description, et le score.

La réponse porte toujours le bundle réellement utilisé et, le cas échéant,
**l'écart avec la version demandée**.

### `yang_detail`

| Paramètre | Sens |
|---|---|
| `chemin` | Un chemin rendu par `yang_chercher` |
| `plateforme`, `version` | Idem |

Rend le nœud, ses **enfants immédiats** et les clés à fournir.

Cet outil n'est pas du confort. Après une recherche, un modèle veut descendre
dans l'arbre : « qu'y a-t-il sous ce conteneur ? ». Sans lui, il redevine — le
comportement même que yangmap existe pour supprimer.

### Ce que les descriptions d'outils doivent dire

Le budget de contexte est une contrainte de conception, pas une optimisation
tardive. Les descriptions restent courtes et ne répètent pas l'inventaire des
plateformes à chaque outil.

## 7. Le classement, défini par sa mesure

C'est le seul endroit difficile du projet. Il est donc spécifié par **ce qu'il
doit réussir**, pas par l'algorithme qui y parviendra.

### 7.1 Le jeu d'or

Un fichier de questions réelles associées aux chemins attendus. La métrique est
binaire et sans indulgence : **le chemin attendu figure-t-il dans les cinq
premiers résultats ?**

Extrait, à compléter à quinze entrées minimum, couvrant les trois vendeurs :

| Question | Chemin attendu |
|---|---|
| routes actives et inactives | `/state/router[]/route-table/unicast/ipv4/statistics/*/available-routes` |
| SFP non reconnu | `/state/port[]/transceiver/{connector-type,diagnostics-capable}` |
| adjacence ISIS | `/state/router[]/isis[]/interface/level[]/…` |
| sessions PPPoE qui ne montent pas | `/state/service/vprn[]/subscriber-interface[]/group-interface[]/sap[]/pppoe/statistics/rx/{padi,padr,padt,dropped}` |
| température d'un optique | `/state/port[]/transceiver/…temperature` |

Une entrée du jeu d'or dont le chemin attendu n'a pas été **vérifié présent
dans l'index** n'a pas sa place dans le jeu d'or : elle testerait la couverture
du vendeur, pas le classement.

### 7.2 Les signaux, par ordre de force présumée

1. **Correspondance exacte d'un segment de chemin.** `transceiver` est un
   segment entier de `/state/port[]/transceiver/…` ; c'est le signal qui
   distingue le bon résultat du bruit dans les quatre échecs mesurés en §3.4.
2. **BM25 sur la description.** Le fond documentaire.
3. **BM25 sur les segments du chemin**, en champ séparé et mieux pondéré que la
   description.
4. **Pénalité de profondeur.** Neuf segments désignent un sous-système
   spécialisé, quatre désignent le cœur d'un équipement.

Les pondérations sont **déterminées par le jeu d'or**, jamais posées par
intuition. Un signal qui n'améliore aucune entrée du jeu d'or est retiré.

### 7.3 Ce qui est explicitement écarté pour l'instant

Les embeddings sémantiques. Ils traiteraient mieux les formulations indirectes,
mais ajoutent une dépendance lourde et — surtout — rendraient impossible de
savoir **lequel des deux moteurs porte un résultat**, donc quoi améliorer.
Le lexical d'abord, mesuré. S'il plafonne sur le jeu d'or, la question se
rouvrira avec des chiffres à l'appui.

## 8. Résolution de version et mode dégradé

| Cas | Comportement |
|---|---|
| Version exacte disponible | L'utiliser. `ecart: null` dans la réponse |
| Version absente, même train | Utiliser le plus proche du train et **le déclarer** (`demandé 17.3.4a, servi 17.3.1`) |
| Train absent | Utiliser le train le plus proche et le déclarer, avec un avertissement plus fort |
| Plateforme inconnue | Erreur explicite. **Aucun repli sur un autre vendeur** |
| Aucun résultat | Le dire. Jamais de chemin approximatif présenté comme certain |

Le principe est celui de netlive : un manque déclaré vaut mieux qu'un manque
comblé en silence. Un modèle qui ignore qu'il lui manque une information conclut
faux avec assurance.

## 9. Souveraineté

`yangmap fetch <plateforme> <version>` télécharge un bundle — **opération
d'installation**. À l'exécution, le serveur n'émet aucune requête réseau.

Les bundles YANG et les index construits ne sont pas versionnés dans git :
ils se régénèrent d'une commande.

## 10. Hors périmètre

- **Toute connexion à un équipement.** Voir §2 — c'est la frontière fondatrice.
- **La configuration** (`nokia-conf`, modèles `*-cfg`). yangmap sert le
  troubleshooting, donc l'état. Rien n'interdit d'ingérer les modèles de
  configuration plus tard ; ils n'entrent pas dans la v1.
- **La qualité des descriptions du vendeur.** yangmap les sert, ne les réécrit
  pas. Une description pauvre reste une description pauvre.
- **Les commandes CLI.** Un cheat-sheet de `show` est un autre problème, avec
  une autre source. Il ne se traite pas avec du YANG.

## 11. Critères d'acceptation falsifiables

| # | Critère | Niveau |
|---|---|---|
| Y1 | Aucun module de yangmap n'ouvre de socket réseau à l'exécution du serveur | BLOQUANT |
| Y2 | Aucun module n'importe de bibliothèque de credentials ni ne lit de fichier d'inventaire | BLOQUANT |
| Y3 | L'index d'un bundle Nokia se construit sans erreur et contient plus de 50 000 chemins | MAJEUR |
| Y4 | ≥ 80 % des entrées du jeu d'or placent le chemin attendu dans les 5 premiers résultats | MAJEUR |
| Y5 | Toute réponse porte le bundle servi ; un écart avec la version demandée est déclaré | MAJEUR |
| Y6 | Un xpath pyang se traduit en chemin gNMI par les deux règles de §5, y compris avec un préfixe de module en milieu de chemin | MAJEUR |
| Y7 | Une plateforme inconnue rend une erreur et ne se replie sur aucune autre | MAJEUR |
| Y8 | Les trois plateformes de §3.1 s'indexent avec 0 erreur pyang | MAJEUR |
| Y9 | `yang_detail` rend les enfants immédiats d'un conteneur et les clés à fournir | MAJEUR |
| Y10 | Aucune réponse ne dépasse la limite demandée, et la limite est plafonnée à 50 | MINEUR |

**Y4 est le critère qui décide du projet.** Les autres protègent des propriétés
qu'on sait déjà tenir ; celui-là mesure la seule chose incertaine.

## 12. Ce que cette spec ne couvre pas, volontairement

- **Le réglage final des pondérations.** Il sort du jeu d'or, pas d'une décision
  de conception. L'écrire ici serait le figer avant de l'avoir mesuré.
- **La complétude du jeu d'or.** Quinze entrées est un plancher, pas une cible.
  Il grandira avec les échecs constatés à l'usage.
- **Les performances.** Aucun budget de latence n'est fixé. Une recherche FTS5
  sur 51 000 lignes est instantanée ; si cela cesse d'être vrai, ce sera mesuré
  avant d'être optimisé.
