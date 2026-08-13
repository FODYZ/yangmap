"""Interface humaine : fetch, build, chercher, detail, versions.

`fetch` est la seule commande qui touche le réseau.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yangmap import bundles, indexer
from yangmap.api import PLATEFORMES, RACINE_DEFAUT, Carte
from yangmap.errors import YangmapError
from yangmap.resolve import analyser_version


def _fetch(args) -> int:
    b = bundles.telecharger(args.plateforme, args.version, Path(args.racine) / "bundles")
    fichiers, _ = b.modeles
    print(f"bundle {b.plateforme} {b.version} → {b.racine}")
    print(f"  {len(fichiers)} modèle(s) YANG à indexer")
    # Comparer les versions analysées, pas les chaînes : `24.3.R3` et `24.3.3`
    # sont la même révision, et annoncer un écart inexistant serait un mensonge.
    if analyser_version(b.version) != analyser_version(args.version):
        print(f"  version demandée {args.version} non publiée : {b.version} obtenue")
    print(f"\nEnsuite : yangmap build {b.plateforme} {b.version}")
    return 0


def _build(args) -> int:
    racine = Path(args.racine)
    base = racine / "bundles" / args.plateforme
    versions = bundles.installes(args.plateforme, racine / "bundles")
    if not versions:
        print(f"aucun bundle {args.plateforme} — jouer `yangmap fetch` d'abord",
              file=sys.stderr)
        return 1
    version = args.version or versions[-1]
    if version not in versions:
        print(f"bundle {version} absent (présents : {', '.join(versions)})",
              file=sys.stderr)
        return 1

    b = bundles.Bundle(args.plateforme, version, base / version)
    fichiers, chemins = b.modeles
    destination = racine / "index" / args.plateforme / f"{version}.db"

    print(f"indexation de {len(fichiers)} modèle(s)…")
    rapport = indexer.construire(
        fichiers, chemins, destination, args.plateforme, version
    )
    print(f"  {rapport.noeuds} chemins indexés → {destination}")
    print(f"  {rapport.modeles_ok}/{len(fichiers)} modèles sans erreur")
    if rapport.modeles_en_echec:
        print(f"  {len(rapport.modeles_en_echec)} modèle(s) en erreur :")
        for m in rapport.modeles_en_echec[:5]:
            print(f"    {m}")
    return 0


def _chercher(args) -> int:
    r = Carte(Path(args.racine)).chercher(
        args.sujet, args.plateforme, args.version, args.limite, arbre=args.arbre
    )
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    print(f"{args.plateforme} {r['bundle_servi']}  ({r['ecart']})  arbre={args.arbre}")
    if r["avertissement"]:
        print(f"  ⚠ {r['avertissement']}")
    print()
    if not r["resultats"]:
        print(r["message"])
        return 0
    for x in r["resultats"]:
        print(f"  [{x['score']:>7.2f}] {x['chemin']}")
        print(f"            {x['genre']}/{x['type'] or '-'} — {x['description'][:100]}")
    return 0


def _detail(args) -> int:
    r = Carte(Path(args.racine)).detail(args.chemin, args.plateforme, args.version)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    n = r["noeud"]
    print(f"{n['chemin']}\n  {n['genre']}/{n['type'] or '-'} — {n['description']}")
    if n["cles_a_fournir"]:
        print(f"  clés à fournir : {', '.join(n['cles_a_fournir'])}")
    print(f"\n  {len(r['enfants'])} enfant(s) immédiat(s) :")
    for e in r["enfants"]:
        print(f"    {e['nom']:<32} {e['genre']:<10} {e['description'][:70]}")
    return 0


def _valider(args) -> int:
    r = Carte(Path(args.racine)).valider(args.chemin, args.plateforme, args.version)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    marque = {"sur": "OK", "volumineux": "!!", "cle_manquante": "KO", "inexistant": "KO"}
    print(f"[{marque.get(r['verdict'], '??')}] {r['verdict']} — {r['chemin_demande']}")
    print(f"     {r['motif']}")
    if r["noeud"]:
        n = r["noeud"]
        print(f"     {n['genre']}/{n['type'] or '-'} (arbre {n['arbre']}) — {n['description'][:120]}")
    if r["suggestions"]:
        print(f"     enfants possibles : {', '.join(r['suggestions'])}")
    # Code 1 sur un chemin qui ne partira jamais : utilisable en garde-fou de
    # script, au même titre que `netlive yang-sync`.
    return 0 if r["interrogeable"] else 1


def _versions(args) -> int:
    carte = Carte(Path(args.racine))
    trouve = carte.plateformes()
    if not trouve:
        print("aucun index construit — jouer `yangmap fetch` puis `yangmap build`")
        return 0
    for plateforme, versions in trouve.items():
        print(f"{plateforme:<14} {', '.join(versions)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="yangmap",
        description="Quel chemin YANG donne quelle information, dans quelle version d'OS.",
    )
    p.add_argument("--racine", default=str(RACINE_DEFAUT),
                   help=f"répertoire des bundles et index (défaut : {RACINE_DEFAUT})")
    sous = p.add_subparsers(dest="commande", required=True)

    f = sous.add_parser("fetch", help="télécharger un bundle YANG (seule commande réseau)")
    f.add_argument("plateforme", choices=PLATEFORMES)
    f.add_argument("version")
    f.set_defaults(fonction=_fetch)

    b = sous.add_parser("build", help="construire l'index depuis un bundle")
    b.add_argument("plateforme", choices=PLATEFORMES)
    b.add_argument("version", nargs="?")
    b.set_defaults(fonction=_build)

    c = sous.add_parser("chercher", help="chercher un chemin")
    c.add_argument("sujet")
    c.add_argument("plateforme", choices=PLATEFORMES)
    c.add_argument("--version")
    c.add_argument("--limite", type=int, default=10)
    c.add_argument("--arbre", choices=("etat", "conf", "tout"), default="etat",
                   help="état opérationnel (défaut) ou arbre de configuration")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fonction=_chercher)

    va = sous.add_parser(
        "valider",
        help="ce chemin existe-t-il, est-il complet, que va-t-il peser ?",
    )
    va.add_argument("chemin")
    va.add_argument("plateforme", choices=PLATEFORMES)
    va.add_argument("--version")
    va.add_argument("--json", action="store_true")
    va.set_defaults(fonction=_valider)

    d = sous.add_parser("detail", help="détailler un chemin et ses enfants")
    d.add_argument("chemin")
    d.add_argument("plateforme", choices=PLATEFORMES)
    d.add_argument("--version")
    d.add_argument("--json", action="store_true")
    d.set_defaults(fonction=_detail)

    v = sous.add_parser("versions", help="index construits")
    v.set_defaults(fonction=_versions)

    args = p.parse_args(argv)
    try:
        return args.fonction(args)
    except YangmapError as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
