# yangmap — design

> Spec established on 2026-08-10, after a reconnaissance campaign whose every
> figure cited here was **measured**, not estimated. The measurement method is
> given each time, so it can be disproved.

## 1. The problem

A language model given read-only gNMI access doesn't know **where to look**.
It knows CLI syntax by heart and invents plausible YANG paths that don't
exist. Each invention costs a tool call, a human approval, and returns
`not_configured` — a status that looks like an answer and isn't one.

Observed under real conditions on `net-ai-copilot`: an agent asked about
active and inactive routes on a Nokia SR OS found no path, for lack of a
named collector, and proposed a CLI command refused by construction.

The gap isn't a missing permission — the policies already open all of
`/state`. It's a missing **map**.

## 2. What yangmap is, and isn't

**yangmap connects to no equipment.** It holds no credentials, opens no
session, issues no network request at runtime. It's a *documentation*
server, not a collection server.

This boundary is the heart of the design, not an implementation detail:

| Consequence | Why it matters |
|---|---|
| Zero security surface | Publishable as open source without the precautions a collection tool would require |
| No operator data ever passes through it | It only sees vendors' public schemas |
| Usable by anyone | It depends on no inventory, no fleet, no infrastructure |

Corollary: **it isn't yangmap that calls `Capabilities`.** The caller
(netlive, or any other client) discovers the equipment's version and
**passes it as a parameter**. yangmap stays offline and unprivileged.

## 3. What the reconnaissance measured

### 3.1 Descriptions exist and are usable

Measurement: count on the published YANG files, then on the generated index.

| Vendor | Indexed paths | Carrying a description | Distinct descriptions |
|---|---|---|---|
| Nokia SR OS 24.3.R3 | 51,122 | 50,227 — **98%** | 12,791 |
| Cisco IOS-XE 17.3.1 (`*-oper`) | 12,431 | 12,139 — **97%** | 8,010 |
| Arista / OpenConfig 4.32.0F | 7,492 | 7,492 — **100%** | 3,139 |

On Nokia, 1,511 of the 12,791 distinct descriptions are navigation filler
(`Enter the <x> context`), i.e. **11%**. They're all on containers; the
leaves — the ones that carry the information — are usefully documented.

Unselected sample, taken as-is from `nokia-state`:

```
/state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/active-routes
    "Count of routes of a routing protocol active in the FIB."

/state/router[router-name]/route-table/unicast/ipv4/statistics/aggregate/available-routes
    "Count of routes of a routing protocol, both active in the FIB
     and inactive in the RIB."
```

That's exactly the active/inactive distinction an engineer looks for, written
by the vendor, versioned with the OS.

### 3.2 Generation is a solved problem

`pyang -f flatten --flatten-keys-in-xpath --flatten-type --flatten-description
--flatten-keyword` produces a `xpath,keyword,type,description` CSV.

| Vendor | Time | Errors |
|---|---|---|
| Nokia (`nokia-state.yang`, 15.5 MB) | 3.7 s | 0 |
| Cisco (all `*-oper.yang`) | 1.5 s | 0 |
| Arista / OpenConfig (4 models) | 1.4 s | 0 |

**There's no YANG parser to write.** The part expected to be costly is free.

### 3.3 Volume rules out serving everything

The distinct useful descriptions from `nokia-state` weigh 832 KB, roughly
**213,000 tokens**. Serving the whole index at once is out of the question,
whatever the context window. **Search isn't a refinement: it's the
function.**

### 3.4 Naive ranking doesn't work — and that's where all the work is

Substring search, top results returned:

| Question | Top raw result | Verdict |
|---|---|---|
| "transceiver" (Nokia) | `/state/port[]/dwdm/coherent/rx-optical-snr-x-polarization` | off-topic |
| "routing table" (Nokia) | `/state/radius/route-downloader[]/statistics/routes-received-count` | off-topic |
| "pppoe" (Nokia) | `/state/isa/nat-group[]/esa[][]/resources/pppoe-sessions` | off-topic |
| "routing table" (Arista) | `…/l2rib/mac-ip-table/entries/entry[][]/host-ip` | off-topic |

The correct path is present in the index in every one of these cases. **This
is a ranking defect, never a data defect.** It shows up identically across
all three vendors: a single ranking engine serves all of them.

The clearest demonstration is PPPoE. Grep first returns NAT and
wlan-gateway counters; the path an engineer wants is this one, and it carries
exactly the sequence you walk through when sessions don't come up:

```
/state/service/vprn[]/subscriber-interface[]/group-interface[]/sap[]/pppoe/statistics/rx/
    padi                "Number of PADI (PPPoE Active Discovery Initiation) packets."
    padr                "Number of PADR (PPPoE Active Discovery Request) packets."
    padt                "Number of PADT (PPPoE Active Discovery Terminate) packets."
    dropped             "Number of dropped PPPoE packets."
    invalid-ac-cookie   "…invalid AC-Cookie tag."
    invalid-session     "…invalid session-id field."
```

Does the PADI arrive? Does the PADR follow? What's being dropped, and why?
The diagnostic method is already in the vendor's schema. All that's missing
is knowing where to look — that is, yangmap.

### 3.5 The exact version isn't always published

| Vendor | Reference hardware version | Closest published bundle |
|---|---|---|
| Nokia | 24.3.R3 | `sros_24.3.r3` — **exact** |
| Cisco | 17.3.4a | `1731` (17.3.1) — train only |
| Arista | 4.32.11M | `4.32.0F` / `1F` / `2F` — train only |

Falling back to the closest bundle is therefore the **normal case on two
vendors out of three**, not an edge case. It must be reported in the
response, never silent.

## 4. Architecture

```
bundles/<platform>/<version>/          Downloaded YANG, outside git version control
        │
        ▼
   ┌─────────────┐
   │  indexer    │  pyang -f flatten ──▶ normalization ──▶ SQLite FTS5
   └─────────────┘
   ┌─────────────┐
   │  resolve    │  (platform, version) ──▶ which bundle, exact or approximate
   └─────────────┘
   ┌─────────────┐
   │  search     │  BM25 + path signals ──▶ ranking
   └─────────────┘
   ┌─────────────┐
   │  server     │  2 MCP tools
   └─────────────┘
```

The standard library's `sqlite3` carries **both FTS5 and `bm25()`**. No
runtime dependency. `pyang` is only required when building the index.

### 4.1 Module breakdown

| Module | Does | Depends on |
|---|---|---|
| `bundles.py` | Downloads a YANG bundle (shallow `git clone` on the tag) | git |
| `indexer.py` | Runs pyang, normalizes, writes the SQLite index | pyang, sqlite3 |
| `normalize.py` | pyang xpath ⟶ gNMI path | nothing |
| `resolve.py` | (platform, version) ⟶ bundle, with the gap declared | nothing |
| `search.py` | Query ⟶ ranked results | sqlite3 |
| `server.py` | Exposes the two MCP tools | all of the above |

`normalize.py`, `resolve.py`, and `search.py` depend on nothing but the
standard library: they can be tested with no network, no YANG, and no MCP.

## 5. Path normalization

pyang returns an xpath prefixed by the module and with no key value. A gNMI
client needs something else. The transformation is deterministic:

```
pyang     /nokia-state:state/router[router-name]/route-table/unicast/ipv4
gNMI      /state/router[router-name=?]/route-table/unicast/ipv4
```

Two rules, and nothing more:

1. Strip the module prefix from **every** segment that carries one
   (`nokia-state:state` ⟶ `state`).
2. Mark the expected keys (`[router-name]` ⟶ `[router-name=?]`), so the
   consumer knows a value must be supplied.

The index keeps **both forms**: the canonical xpath, which is the node's
identity in the schema and keeps all its prefixes, and the gNMI path, which
is what the model has to copy back.

The case that settles rule 1 is the **mid-path** prefix, produced by an
OpenConfig augmentation:
`…/interface[name]/state/openconfig-platform-transceiver:transceiver`. The
conventional gNMI path — the one `gnmic` and existing netlive collectors
emit — carries no prefix at all: the rule therefore strips them all. Nothing
is lost, since the canonical xpath and the `module` field stay in the index;
a consumer that needs the qualified form can reconstruct it.

This is an implementation decision to **confirm on real hardware** (criterion
G2): it's the only point of the normalization that reasoning alone can't
settle.

## 6. The two MCP tools

### `yang_chercher`

| Parameter | Meaning |
|---|---|
| `sujet` | What is being searched for, in natural language or keywords |
| `plateforme` | `nokia_sros`, `cisco_iosxe`, `arista_eos` |
| `version` | OS version. Optional — without it, the platform's default bundle |
| `limite` | Number of results, 10 by default, 50 maximum |

Returns, per result: the gNMI path, the canonical xpath, the node kind
(`leaf`, `container`, `list`), the data type, the description, and the score.

The response always carries the bundle actually used and, where applicable,
**the gap against the requested version**.

### `yang_detail`

| Parameter | Meaning |
|---|---|
| `chemin` | A path returned by `yang_chercher` |
| `plateforme`, `version` | Same as above |

Returns the node, its **immediate children**, and the keys to supply.

This tool isn't a convenience. After a search, a model wants to descend the
tree: "what's under this container?". Without it, it starts guessing again —
exactly the behavior yangmap exists to remove.

### What tool descriptions must say

The context budget is a design constraint, not a late optimization.
Descriptions stay short and don't repeat the platform inventory in each tool.

## 7. Ranking, defined by its measurement

This is the only hard part of the project. It is therefore specified by
**what it must achieve**, not by the algorithm that will get there.

### 7.1 The golden set

A file of real questions paired with expected paths. The metric is binary
and unforgiving: **does the expected path appear in the top five results?**

Excerpt, to be filled out to a minimum of fifteen entries, covering all three
vendors:

| Question | Expected path |
|---|---|
| active and inactive routes | `/state/router[]/route-table/unicast/ipv4/statistics/*/available-routes` |
| unrecognized SFP | `/state/port[]/transceiver/{connector-type,diagnostics-capable}` |
| ISIS adjacency | `/state/router[]/isis[]/interface/level[]/…` |
| PPPoE sessions that won't come up | `/state/service/vprn[]/subscriber-interface[]/group-interface[]/sap[]/pppoe/statistics/rx/{padi,padr,padt,dropped}` |
| optic temperature | `/state/port[]/transceiver/…temperature` |

A golden-set entry whose expected path hasn't been **verified present in the
index** has no place in the golden set: it would test vendor coverage, not
ranking.

### 7.2 The signals, in presumed order of strength

1. **Exact match of a path segment.** `transceiver` is an entire segment of
   `/state/port[]/transceiver/…`; it's the signal that separates the right
   result from the noise in the four failures measured in §3.4.
2. **BM25 on the description.** The documentary bulk.
3. **BM25 on path segments**, as a separate field, weighted more than the
   description.
4. **Depth penalty.** Nine segments denote a specialized subsystem, four
   denote the core of a device.

Weights are **determined by the golden set**, never set by intuition. A
signal that doesn't improve a single golden-set entry is removed.

### 7.3 What's explicitly set aside for now

Semantic embeddings. They would handle indirect phrasings better, but add a
heavy dependency and — above all — would make it impossible to know **which
of the two engines carries a result**, and therefore what to improve. Lexical
first, measured. If it plateaus on the golden set, the question reopens with
numbers behind it.

## 8. Version resolution and degraded mode

| Case | Behavior |
|---|---|
| Exact version available | Use it. `ecart: null` in the response |
| Version absent, same train | Use the closest in the train and **declare it** (`requested 17.3.4a, served 17.3.1`) |
| Train absent | Use the closest train and declare it, with a stronger warning |
| Unknown platform | Explicit error. **No fallback to another vendor** |
| No result | Say so. Never present an approximate path as certain |

The principle is netlive's: a declared gap beats a gap silently papered over.
A model unaware that it's missing information concludes wrongly, and
confidently.

## 9. Sovereignty

`yangmap fetch <platform> <version>` downloads a bundle — an **installation
operation**. At runtime, the server issues no network request.

YANG bundles and built indexes are not version-controlled in git: they
regenerate from a single command.

## 10. Out of scope

- **Any connection to equipment.** See §2 — this is the founding boundary.
- **Configuration** (`nokia-conf`, `*-cfg` models). yangmap serves
  troubleshooting, hence state. Nothing prevents ingesting configuration
  models later; they're not in v1.
- **The quality of vendor descriptions.** yangmap serves them, doesn't rewrite
  them. A poor description stays a poor description.
- **CLI commands.** A `show`-command cheat sheet is a different problem, with
  a different source. It isn't solved with YANG.

## 11. Falsifiable acceptance criteria

| # | Criterion | Level |
|---|---|---|
| Y1 | No yangmap module opens a network socket while the server runs | BLOCKING |
| Y2 | No module imports a credentials library or reads an inventory file | BLOCKING |
| Y3 | A Nokia bundle's index builds with no error and contains more than 50,000 paths | MAJOR |
| Y4 | ≥ 80% of golden-set entries place the expected path in the top 5 results | MAJOR |
| Y5 | Every response carries the bundle served; a gap against the requested version is declared | MAJOR |
| Y6 | A pyang xpath translates to a gNMI path via the two rules of §5, including a mid-path module prefix | MAJOR |
| Y7 | An unknown platform returns an error and falls back to no other | MAJOR |
| Y8 | The three platforms of §3.1 index with 0 pyang errors | MAJOR |
| Y9 | `yang_detail` returns a container's immediate children and the keys to supply | MAJOR |
| Y10 | No response exceeds the requested limit, and the limit is capped at 50 | MINOR |

**Y4 is the criterion that decides the project.** The others protect
properties already known to hold; that one measures the only uncertain
thing.

## 12. What this spec deliberately does not cover

- **Final weight tuning.** That comes out of the golden set, not a design
  decision. Writing it here would freeze it before it's measured.
- **Golden-set completeness.** Fifteen entries is a floor, not a target. It
  will grow with failures observed in use.
- **Performance.** No latency budget is set. An FTS5 search over 51,000 rows
  is instantaneous; if that stops being true, it will be measured before
  being optimized.
