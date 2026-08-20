# yangmap

**Which gNMI path carries which information, on which vendor, in which OS version.**

A language model given read-only gNMI access doesn't know *where to look*. It
knows CLI syntax by heart and invents plausible YANG paths that don't exist.
yangmap gives it the map — built from the YANG published by the vendor, not
from a hand-written list.

```
$ yangmap chercher "active and inactive routes" nokia_sros --version 24.3.R3
nokia_sros 24.3.3  (exact)

  [  31.44] /state/router[router-name=?]/route-table/unicast/ipv4/statistics/aggregate/available-routes
            leaf/uint32 — Count of routes of a routing protocol, both active in the FIB and inactive in the RIB.
```

## What yangmap does not do

**It connects to no equipment.** No credentials, no inventory, no socket.
It's a *documentation* server, not a collection server — and that's what
gives it a zero security surface.

The caller discovers the equipment's version (gNMI `Capabilities`) and passes
it as a parameter. yangmap stays offline and unprivileged.

## Guarantees

| Guarantee | Mechanism | Test |
|---|---|---|
| No equipment contact | No server module imports a network library | `tests/test_frontiere.py` |
| No access to secrets | No module imports `keyring` or an equivalent | `tests/test_frontiere.py` |
| The download path is unreachable from a tool | `server.py` imports neither `bundles` nor `indexer` | `tests/test_frontiere.py` |
| No silent fallback between vendors | Unknown platform ⇒ error | `tests/test_api.py` |
| A version mismatch is always reported | Every response carries the bundle actually served | `tests/test_api.py` |

These tests were **deliberately broken** before being fixed. One of them
protected nothing: `from yangmap import bundles` passed, because the AST
extractor only picked up the module, never the imported name.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
# 1. Download the vendor's YANG — the ONLY command that touches the network
yangmap fetch nokia_sros 24.3.R3

# 2. Build the index — offline from here on
yangmap build nokia_sros

# 3. Search
yangmap chercher "SFP transceiver" nokia_sros
yangmap detail "/state/port[port-id=?]/transceiver" nokia_sros

yangmap versions
```

Bundles and indexes live under `~/.yangmap` and are never version-controlled:
they regenerate from a single command.

## MCP server

```bash
yangmap-mcp
```

Two tools, and not one more:

| Tool | Returns |
|---|---|
| `yang_chercher(subject, platform, version, limit)` | Ranked paths, with node kind, type, and vendor description |
| `yang_detail(path, platform, version)` | The node, the keys it requires, and its **immediate children** |

The second lets the model descend the tree without guessing.

## Platforms

| Platform | YANG source | Indexed models | Paths | Descriptions |
|---|---|---|---|---|
| `nokia_sros` | [nokia/7x50_YangModels](https://github.com/nokia/7x50_YangModels), tag per revision | `nokia-state` | 50,772 | 98% |
| `cisco_iosxe` | [YangModels/yang](https://github.com/YangModels/yang), `vendor/cisco/xe` | `*-oper.yang` | 12,123 | 97% |
| `arista_eos` | [aristanetworks/yang](https://github.com/aristanetworks/yang) | OpenConfig | 9,924 | 100% |

**The exact version isn't always published** — Nokia goes down to the patch,
Cisco and Arista stop at the train. Falling back is therefore the normal
case, and it is **reported in every response**:

```json
{"bundle_servi": "17.3.1", "version_demandee": "17.3.4a", "ecart": "meme_train",
 "avertissement": "Version 17.3.4a not published by the vendor: bundle 17.3.1 served…"}
```

## Ranking

This is the only genuinely hard part, and it's defined by its **measurement**:
a golden set of real questions, metric "is the expected path in the top
five". **21 questions, three platforms, 100%.**

```bash
python goldenset/mesurer.py             # measure
python goldenset/mesurer.py --ablation  # does each signal earn its place?
```

Four signals, all proven useful by ablation:

| Signal neutralized | Rate | Delta |
|---|---|---|
| BM25 on descriptions | 76% | −24% |
| BM25 on path segments | 86% | −14% |
| Exact segment match | 90% | −10% |
| Depth penalty | 95% | −5% |

**Two signals were tried and then dropped** for lack of measurable effect:
boosting leaves, and term coverage. A signal that doesn't move a single
golden-set entry doesn't stay in the code.

### The baseline that ranking has to beat

A naive substring search returns, across all three vendors:

| Question | Top raw result |
|---|---|
| "transceiver" (Nokia) | `…/dwdm/coherent/rx-optical-snr-x-polarization` |
| "routing table" (Nokia) | `/state/radius/route-downloader[]/statistics/…` |
| "routing table" (Arista) | `…/l2rib/mac-ip-table/entries/entry[][]/host-ip` |

The correct data is in the index every time. **This is a ranking defect,
never a data defect.**

## Tests

```bash
.venv/bin/python -m pytest -m "not lab"   # 91 tests, no network or hardware
.venv/bin/python -m pytest -m lab         # 9 tests against a real containerlab
```

## Documentation

[Design](docs/superpowers/specs/2026-08-10-yangmap-design.md) ·
[Validation criteria](docs/CRITERES-VALIDATION.md)

## License

[MIT](LICENSE)
