# yangmap

**Quel chemin gNMI porte quelle information, sur quel vendeur, dans quelle
version d'OS.**

Un modèle de langage à qui l'on donne un accès gNMI en lecture ne sait pas *où
regarder*. Il connaît la syntaxe CLI par cœur et invente des chemins YANG
plausibles qui n'existent pas. yangmap lui donne la carte — construite depuis
le YANG publié par le vendeur, pas depuis une liste écrite à la main.

```
$ yangmap chercher "routes actives et inactives" nokia_sros --version 24.3.R3
nokia_sros 24.3.3  (exact)

  [  31.44] /state/router[router-name=?]/route-table/unicast/ipv4/statistics/aggregate/available-routes
            leaf/uint32 — Count of routes of a routing protocol, both active in the FIB and inactive in the RIB.
```

## Ce que yangmap ne fait pas

**Il ne se connecte à aucun équipement.** Pas de credential, pas d'inventaire,
pas de socket. C'est un serveur de *documentation*, pas de collecte — et c'est
ce qui lui donne une surface de sécurité nulle.

C'est l'appelant qui découvre la version de l'équipement (gNMI `Capabilities`)
et la passe en paramètre. yangmap reste hors ligne et sans privilège.

## Les garanties

| Garantie | Mécanisme | Test |
|---|---|---|
| Aucun contact équipement | Aucun module du serveur n'importe de bibliothèque réseau | `tests/test_frontiere.py` |
| Aucun accès aux secrets | Aucun module n'importe `keyring` ni équivalent | `tests/test_frontiere.py` |
| Le téléchargement n'est pas atteignable depuis un outil | `server.py` n'importe ni `bundles` ni `indexer` | `tests/test_frontiere.py` |
| Aucun repli silencieux entre vendeurs | Plateforme inconnue ⇒ erreur | `tests/test_api.py` |
| Un écart de version est toujours déclaré | Chaque réponse porte le bundle servi | `tests/test_api.py` |

Ces tests ont été **mis en échec volontairement** avant d'être remis au vert.
L'un d'eux ne protégeait rien : `from yangmap import bundles` passait, parce
que l'extracteur d'AST ne relevait que le module et jamais le nom importé.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
# 1. Telecharger le YANG du vendeur — SEULE commande qui touche le reseau
yangmap fetch nokia_sros 24.3.R3

# 2. Construire l'index — hors ligne a partir d'ici
yangmap build nokia_sros

# 3. Chercher
yangmap chercher "transceiver SFP" nokia_sros
yangmap detail "/state/port[port-id=?]/transceiver" nokia_sros

yangmap versions
```

Bundles et index vivent dans `~/.yangmap` et ne sont jamais versionnés : ils se
régénèrent d'une commande.

## Serveur MCP

```bash
yangmap-mcp
```

Deux outils, et pas un de plus :

| Outil | Rend |
|---|---|
| `yang_chercher(sujet, plateforme, version, limite)` | Chemins classés, avec type et description du vendeur |
| `yang_detail(chemin, plateforme, version)` | Le nœud, ses clés à fournir, ses **enfants immédiats** |

Le second permet au modèle de descendre dans l'arbre sans deviner.

## Plateformes

| Plateforme | Source YANG | Modèles indexés | Chemins | Descriptions |
|---|---|---|---|---|
| `nokia_sros` | [nokia/7x50_YangModels](https://github.com/nokia/7x50_YangModels), tag par révision | `nokia-state` | 50 772 | 98 % |
| `cisco_iosxe` | [YangModels/yang](https://github.com/YangModels/yang), `vendor/cisco/xe` | `*-oper.yang` | 12 123 | 97 % |
| `arista_eos` | [aristanetworks/yang](https://github.com/aristanetworks/yang) | OpenConfig | 9 924 | 100 % |

**La version exacte n'est pas toujours publiée** — Nokia va jusqu'au patch,
Cisco et Arista s'arrêtent au train. Le repli est donc le cas normal, et il
est **annoncé dans chaque réponse** :

```json
{"bundle_servi": "17.3.1", "version_demandee": "17.3.4a", "ecart": "meme_train",
 "avertissement": "Version 17.3.4a non publiée par le vendeur : bundle 17.3.1 servi…"}
```

## Le classement

C'est le seul endroit difficile, et il est défini par sa **mesure** : un jeu
d'or de questions réelles, métrique « le chemin attendu est-il dans les cinq
premiers ». **21 questions, trois plateformes, 100 %.**

```bash
python goldenset/mesurer.py             # mesure
python goldenset/mesurer.py --ablation  # chaque signal gagne-t-il sa place ?
```

Quatre signaux, tous prouvés utiles par ablation :

| Signal neutralisé | Taux | Delta |
|---|---|---|
| BM25 sur les descriptions | 76 % | −24 % |
| BM25 sur les segments de chemin | 86 % | −14 % |
| Correspondance exacte de segment | 90 % | −10 % |
| Pénalité de profondeur | 95 % | −5 % |

**Deux signaux ont été essayés puis retirés** faute d'effet mesurable :
bonifier les feuilles, et la couverture des termes. Un signal qui ne déplace
aucune entrée du jeu d'or ne reste pas dans le code.

### Le défaut que le classement doit battre

Une recherche par sous-chaîne rend, sur les trois vendeurs :

| Question | Premier résultat brut |
|---|---|
| « transceiver » (Nokia) | `…/dwdm/coherent/rx-optical-snr-x-polarization` |
| « table de routage » (Nokia) | `/state/radius/route-downloader[]/statistics/…` |
| « table de routage » (Arista) | `…/l2rib/mac-ip-table/entries/entry[][]/host-ip` |

La donnée correcte est dans l'index à chaque fois. **C'est un défaut de
classement, jamais un défaut de données.**

## Tests

```bash
.venv/bin/python -m pytest -m "not lab"   # 91 tests, sans reseau ni materiel
.venv/bin/python -m pytest -m lab         # 9 tests contre un containerlab reel
```

## Documentation

[Conception](docs/superpowers/specs/2026-08-10-yangmap-design.md) ·
[Cahier de critères de validation](docs/CRITERES-VALIDATION.md)
