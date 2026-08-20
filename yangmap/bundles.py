"""Downloading and locating vendors' YANG models.

**The only module allowed to touch the network**, and it is never called by
the MCP server (criteria A1, A4). `yangmap fetch` is an installation
operation; at runtime, yangmap is offline.

Each vendor publishes differently — Nokia a git tag per revision, Cisco a
directory per train in a giant repository, Arista a directory per revision
in a single repository. All this irregularity is confined here: the rest of
the code only ever sees `bundles/<platform>/<version>/`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from yangmap.errors import BundleError
from yangmap.resolve import Version, analyser_version

PLATEFORMES = ("nokia_sros", "cisco_iosxe", "arista_eos")


@dataclass(frozen=True)
class Bundle:
    plateforme: str
    version: str
    racine: Path

    @property
    def modeles(self) -> tuple[list[Path], list[Path]]:
        return _MODELES[self.plateforme](self.racine)


def _git(*args: str, cwd: Path | None = None) -> None:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise BundleError(
            f"git {' '.join(args[:2])} failed:\n{proc.stderr.strip()[:500]}"
        )


def _refs_distantes(depot: str, motif: str) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", "--heads", depot],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise BundleError(f"repository unreachable: {depot}")
    noms = []
    for ligne in proc.stdout.splitlines():
        _, _, ref = ligne.partition("\t")
        ref = ref.replace("refs/tags/", "").replace("refs/heads/", "")
        if ref.endswith("^{}"):
            continue
        if re.match(motif, ref):
            noms.append(ref)
    return noms


# ---------------------------------------------------------------------------
# Nokia SR OS — a git tag per revision: `sros_24.3.r3`
# ---------------------------------------------------------------------------

def _fetch_nokia(cible: Version, dest: Path) -> str:
    depot = "https://github.com/nokia/7x50_YangModels.git"
    refs = _refs_distantes(depot, r"^sros_\d+\.\d+(\.r\d+)?$")
    if not refs:
        raise BundleError("no published SR OS revision found")

    exact = f"sros_{cible.majeur}.{cible.mineur}.r{cible.patch}"
    ref = exact if exact in refs else None
    if ref is None:
        train = [r for r in refs if r.startswith(f"sros_{cible.majeur}.{cible.mineur}")]
        ref = sorted(train)[-1] if train else sorted(refs)[-1]

    _git("clone", "--depth", "1", "--branch", ref, "--single-branch", "-q", depot, str(dest))
    return str(analyser_version(ref))


def _modeles_nokia(racine: Path) -> tuple[list[Path], list[Path]]:
    yang = racine / "YANG"
    # The combined model carries the whole state tree in one file: no
    # `include` resolution to do, so no possible error on that front.
    etat = yang / "nokia-combined" / "nokia-state.yang"
    if not etat.exists():
        raise BundleError(f"nokia-state.yang not found under {yang}")
    return [etat], [yang, yang / "ietf"]


# ---------------------------------------------------------------------------
# Cisco IOS-XE — a directory per train in a 168 MB repository
# ---------------------------------------------------------------------------

def _repertoire_cisco(v: Version) -> str:
    """17.3.1 ⟶ `1731`, 17.10.1 ⟶ `17101`. The train gives the name."""
    return f"{v.majeur}{v.mineur}{v.patch}"


def _fetch_cisco(cible: Version, dest: Path) -> str:
    depot = "https://github.com/YangModels/yang.git"
    # Sparse checkout: without it, 168 MB for a few hundred files.
    _git("clone", "--depth", "1", "--filter=blob:none", "--sparse", "-q", depot, str(dest))
    _git("sparse-checkout", "set", "vendor/cisco/xe", cwd=dest)

    base = dest / "vendor" / "cisco" / "xe"
    presents = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name.isdigit())
    if not presents:
        raise BundleError("no IOS-XE version found in the repository")

    voulu = _repertoire_cisco(cible)
    if voulu not in presents:
        # Stay in the train, otherwise the closest one numerically.
        prefixe = f"{cible.majeur}{cible.mineur}"
        train = [p for p in presents if p.startswith(prefixe)]
        voulu = train[-1] if train else min(
            presents, key=lambda p: abs(int(p) - int(voulu))
        )

    # Keep only the chosen version: the rest is dead weight.
    for p in base.iterdir():
        if p.name != voulu and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    v = analyser_version(f"{voulu[:2]}.{voulu[2:-1]}.{voulu[-1]}")
    return str(v)


def _modeles_cisco(racine: Path) -> tuple[list[Path], list[Path]]:
    base = racine / "vendor" / "cisco" / "xe"
    dossiers = [p for p in base.iterdir() if p.is_dir() and p.name.isdigit()]
    if not dossiers:
        raise BundleError(f"no version directory under {base}")
    d = dossiers[0]
    # `*-oper.yang` carries operational state: it's the equivalent of
    # `nokia-state`. Configuration models are out of scope (spec §10).
    fichiers = sorted(d.glob("*-oper.yang"))
    if not fichiers:
        raise BundleError(f"no *-oper.yang model under {d}")
    return fichiers, [d]


# ---------------------------------------------------------------------------
# Arista EOS — a directory per revision, single 4 MB repository
# ---------------------------------------------------------------------------

def _fetch_arista(cible: Version, dest: Path) -> str:
    depot = "https://github.com/aristanetworks/yang.git"
    _git("clone", "--depth", "1", "-q", depot, str(dest))

    dossiers = sorted(p.name for p in dest.iterdir() if p.name.startswith("EOS-"))
    if not dossiers:
        raise BundleError("no EOS revision found in the repository")

    prefixe = f"EOS-{cible.majeur}.{cible.mineur}."
    train = [d for d in dossiers if d.startswith(prefixe)]
    retenu = sorted(train)[-1] if train else sorted(dossiers)[-1]

    for p in dest.iterdir():
        if p.is_dir() and p.name.startswith("EOS-") and p.name != retenu:
            shutil.rmtree(p, ignore_errors=True)

    return str(analyser_version(retenu))


def _modeles_arista(racine: Path) -> tuple[list[Path], list[Path]]:
    dossiers = [p for p in racine.iterdir() if p.name.startswith("EOS-")]
    if not dossiers:
        raise BundleError(f"no EOS-* directory under {racine}")
    eos = dossiers[0]
    modeles = eos / "openconfig" / "public" / "release" / "models"
    if not modeles.is_dir():
        raise BundleError(f"openconfig tree not found under {eos}")

    # gNMI on EOS speaks OpenConfig. We index the families useful for
    # troubleshooting, not the whole tree: `aft`, `gribi`, or `ate` have
    # no business in a diagnostic map.
    familles = (
        "interfaces", "platform", "network-instance", "system", "lldp",
        "bgp", "isis", "lacp", "local-routing", "optical-transport",
        "relay-agent", "vlan", "qos",
    )
    fichiers: list[Path] = []
    for famille in familles:
        fichiers += sorted((modeles / famille).glob("*.yang"))
    if not fichiers:
        raise BundleError(f"no useful openconfig model under {modeles}")

    tiers = eos / "openconfig" / "public" / "third_party" / "ietf"
    return fichiers, [modeles, tiers, *[modeles / f for f in familles]]


# ---------------------------------------------------------------------------

_FETCH = {
    "nokia_sros": _fetch_nokia,
    "cisco_iosxe": _fetch_cisco,
    "arista_eos": _fetch_arista,
}

_MODELES = {
    "nokia_sros": _modeles_nokia,
    "cisco_iosxe": _modeles_cisco,
    "arista_eos": _modeles_arista,
}


def telecharger(plateforme: str, version: str, racine_bundles: Path) -> Bundle:
    """Downloads a bundle. Returns the version **actually** obtained."""
    if plateforme not in PLATEFORMES:
        raise BundleError(
            f"unknown platform: {plateforme!r} "
            f"(known: {', '.join(PLATEFORMES)})"
        )

    cible = analyser_version(version)
    temporaire = Path(racine_bundles) / plateforme / f".tmp-{cible}"
    if temporaire.exists():
        shutil.rmtree(temporaire, ignore_errors=True)
    temporaire.parent.mkdir(parents=True, exist_ok=True)

    obtenue = _FETCH[plateforme](cible, temporaire)

    definitif = Path(racine_bundles) / plateforme / obtenue
    if definitif.exists():
        shutil.rmtree(definitif, ignore_errors=True)
    temporaire.rename(definitif)

    (definitif / "bundle.json").write_text(
        json.dumps(
            {"plateforme": plateforme, "version": obtenue, "demandee": version},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return Bundle(plateforme, obtenue, definitif)


def installes(plateforme: str, racine_bundles: Path) -> list[str]:
    """Versions already downloaded for a platform."""
    base = Path(racine_bundles) / plateforme
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
