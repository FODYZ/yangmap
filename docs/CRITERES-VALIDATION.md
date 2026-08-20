# Validation criteria — yangmap

> Established on 2026-08-10 from
> [`docs/superpowers/specs/2026-08-10-yangmap-design.md`](superpowers/specs/2026-08-10-yangmap-design.md).
> Same discipline as `net-ai-copilot`'s criteria: a criterion is not a
> restatement of the spec, it's a **falsifiable statement** paired with a way
> to disprove it.

## How to read this document

| Level | Meaning |
|---|---|
| **BLOCKING** | A failure invalidates an announced guarantee. Do not ship. |
| **MAJOR** | A failure degrades a central property without breaking the founding boundary. |
| **MINOR** | A gap in comfort, documentation, or completeness. |

When no mechanical check is possible, it's stated as such. A declared review
is worth more than an imaginary proof.

---

## A — The founding boundary: no equipment contact

This is what makes yangmap publishable and reusable. If A falls, the project
changes nature.

| # | Criterion | Level | Verification |
|---|---|---|---|
| A1 | No server module opens a network socket at runtime | BLOCKING | AST test: no import of `socket`, `http*`, `requests`, `httpx`, `grpc`, `paramiko`, `scrapli`, `pygnmi` outside the bundle-download module |
| A2 | No module imports `keyring` or any secrets library | BLOCKING | AST test across the whole tree |
| A3 | The server reads no inventory file, nor any file outside `bundles/` and its index | BLOCKING | Declared code review + test of opened paths |
| A4 | Downloading bundles is **a separate command**, never triggered by an MCP tool call | BLOCKING | Test: no server code path calls the download module |
| A5 | The server starts and responds with no network access at all | MAJOR | Suite run with the network cut off |

## B — Ingestion and index construction

| # | Criterion | Level | Verification |
|---|---|---|---|
| B1 | A Nokia bundle indexes with **0 pyang errors** and produces > 50,000 paths | MAJOR | Real build, count |
| B2 | A Cisco IOS-XE bundle (`*-oper`) indexes with 0 errors | MAJOR | Same |
| B3 | An Arista/OpenConfig bundle indexes with 0 errors | MAJOR | Same |
| B4 | Every index entry carries: canonical xpath, gNMI path, node kind, type, description, source module | MAJOR | Schema check on the built database |
| B5 | The build is **idempotent**: rebuilding an already-indexed bundle gives the same entry count | MAJOR | Double build, comparison |
| B6 | A pyang error on one model does not stop indexing the others, and is **reported** | MAJOR | Injection of an invalid YANG file |
| B7 | The index builds without the intermediate CSV surviving | MINOR | Directory check after the build |

## C — Path normalization

| # | Criterion | Level | Verification |
|---|---|---|---|
| C1 | The module prefix is stripped from **every** segment (`/nokia-state:state/…` ⟶ `/state/…`) | MAJOR | Unit tests |
| C2 | A prefix **mid-path** is stripped from the gNMI path but **kept in the canonical xpath** — nothing is lost | MAJOR | Dedicated test on `…/state/openconfig-platform-transceiver:transceiver`, **plus** confirmation on real hardware (G2) |
| C3 | List keys are marked as awaiting a value (`[router-name]` ⟶ `[router-name=?]`) | MAJOR | Unit tests |
| C4 | A list with multiple keys keeps **all** of them | MAJOR | Test on `[ip-address][mac-address][pppoe-session-id]` |
| C5 | The canonical xpath is kept intact alongside the gNMI path | MAJOR | Schema check |
| C6 | Normalization is pure: same inputs, same outputs, no state | MINOR | Review + tests |

## D — Version resolution and degraded mode

| # | Criterion | Level | Verification |
|---|---|---|---|
| D1 | Exact version available ⟹ it is served, zero gap declared | MAJOR | Test: Nokia 24.3.R3 |
| D2 | Version absent, same train ⟹ closest in the train, **gap declared in the response** | MAJOR | Test: Cisco 17.3.4a ⟶ 17.3.1 |
| D3 | Train absent ⟹ closest train, gap declared with a stronger warning | MAJOR | Test: Arista 4.32.11M ⟶ 4.32.x |
| D4 | Unknown platform ⟹ explicit error, **no fallback to another vendor** | BLOCKING | Dedicated test |
| D5 | No bundle installed for a platform ⟹ message naming the command to run | MAJOR | Dedicated test |
| D6 | A response **never** hides a version gap | BLOCKING | Every response carries the bundle served; test on the three D1–D3 cases |

## E — Search and ranking

The core of the project. E4 decides its value.

| # | Criterion | Level | Verification |
|---|---|---|---|
| E1 | A search on a Nokia index returns a result in under one second | MINOR | Measurement |
| E2 | Search covers both the description **and** the path segments | MAJOR | Test: a term present only in the path is found, and vice versa |
| E3 | A term with no results returns an empty list and **says so** — never an approximate path | BLOCKING | Test with a nonsense term |
| E4 | **≥ 80% of golden-set entries place the expected path in the top 5** | MAJOR | Golden-set run |
| E5 | The golden set has at least 15 entries and covers all three platforms | MAJOR | Count |
| E6 | Every expected path in the golden set is **verified present in the index** before being included | MAJOR | Consistency test of the golden set itself |
| E7 | The four ranking failures documented in spec §3.4 are fixed | MAJOR | They're part of the golden set |
| E8 | The score is returned to the client, so a weak result can be recognized | MINOR | Response check |
| E9 | The requested limit is honored and capped at 50 | MINOR | Boundary tests |
| E10 | Removing a ranking signal measurably degrades the golden set, or the signal is removed from the code | MAJOR | Ablation measurement, one signal at a time |

## F — MCP contract

| # | Criterion | Level | Verification |
|---|---|---|---|
| F1 | The server exposes exactly two tools: `yang_chercher` and `yang_detail` | MAJOR | Query from a real MCP client |
| F2 | `yang_detail` returns the **immediate children** of a container, not its whole subtree | MAJOR | Test on `/state/port[port-id]/transceiver` |
| F3 | `yang_detail` returns the keys required to reach the path | MAJOR | Test on a multi-key path |
| F4 | `yang_detail` on an unknown path returns a clear error, never a silent empty result | MAJOR | Dedicated test |
| F5 | Tool descriptions don't repeat the platform inventory in each tool | MINOR | Description-size measurement |
| F6 | Server logs don't corrupt JSON-RPC on stdio | MAJOR | Test of a full stdio exchange |
| F7 | A response is valid JSON regardless of result size | MAJOR | Test with `limite=50` |

## G — Real-world usage by netlive

What netlive's own criteria can't cover, and which is the project's reason
for existing.

| # | Criterion | Level | Verification |
|---|---|---|---|
| G1 | A path returned by `yang_chercher` is **accepted by netlive's policy**, unmodified | BLOCKING | Golden-set paths run through `Policy.evaluate_request` |
| G2 | A returned path, filled in with its keys, **actually queries** the lab equipment and returns data | BLOCKING | End-to-end test against the containerlab |
| G3 | The `route-table` path found by yangmap closes the gap documented in the HANDOFF of 2026-08-10 | MAJOR | Real collection on `sros-lab-01`, active and inactive routes returned |
| G4 | A path returned by yangmap **never** bypasses netlive's security floor | BLOCKING | No golden-set path is a write verb; dedicated test |
| G5 | The version passed to yangmap comes from `Capabilities` actually read on the equipment | MAJOR | Lab test: `GnmiTransport.capabilities()` ⟶ version ⟶ `yang_chercher` |
| G6 | A model equipped with yangmap finds a path it couldn't find without it | MAJOR | With/without comparison, on the same questions |
| G7 | Adding yangmap doesn't grow the base context by more than the spec states | MINOR | Tool-description size measurement |

## H — Reproducibility and documentation

| # | Criterion | Level | Verification |
|---|---|---|---|
| H1 | `yangmap fetch` then `yangmap build` rebuild an index from nothing, one command each | MAJOR | Run from an empty directory |
| H2 | Bundles and indexes are not version-controlled in git | MAJOR | Check of `.gitignore` and the git index |
| H3 | The figures published in the README are accurate | MINOR | Suite run |
| H4 | Every guarantee announced in the README is backed by a test **named in the README** | BLOCKING | Line-by-line comparison |
| H5 | The full suite runs with no hardware and no network | MAJOR | Offline run |

---

## What this document deliberately does not cover

- **The quality of vendor descriptions.** yangmap serves them, doesn't rewrite
  them. A poor description stays a poor description, and no criterion can
  demand otherwise.
- **The completeness of YANG coverage.** We don't prove that every useful path
  is findable. E4 measures ranking on an assumed sample.
- **The quality of the model's reasoning.** Finding the right path is not the
  same as concluding correctly. G6 measures that the path is found, not that
  the diagnosis is correct.
- **Performance beyond E1.** No latency budget is set by the spec.
- **Golden-set completeness.** Fifteen entries is a floor. It will grow with
  failures observed in use — same logic as `netlive gaps`.
