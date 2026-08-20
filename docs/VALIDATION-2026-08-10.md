# Validation criteria run-through — 2026-08-10

> Reference: [`CRITERES-VALIDATION.md`](CRITERES-VALIDATION.md)
> Hardware: real containerlab (`sros-lab-01` SR OS 24.3.R3 over gNMI,
> `ceos-lab-01` EOS 4.32.11M with gNMI enabled for this campaign,
> `csr-lab-01` IOS-XE 17.3.4a).
> Model: Qwen3.6 27B Q5 running locally via the homelab's Ollama.

## Verdict

| | |
|---|---|
| ✅ Passed | **42** |
| ⚠️ Partial | **1** |
| ❌ Failed | **0** |
| **Total** | **43** |

| Suite | Tests |
|---|---|
| yangmap, outside the lab | **91** ✅ |
| yangmap, real indexes (`build`) | **3** ✅ |
| yangmap, real containerlab (`lab`) | **9** ✅ |
| netlive, outside the lab | **359** ✅ (including **15 added** by this campaign) |
| netlive, real containerlab | **13** ✅ |

## A — The founding boundary

| # | Criterion | State | Evidence |
|---|---|---|---|
| A1 | No network socket at runtime | ✅ | AST test on the 9 modules. **Confirmed by accident**: the yangmap venv doesn't have `pygnmi`, so the lab tests had to run from netlive's venv |
| A2 | No secrets library | ✅ | AST test, 9 modules |
| A3 | No inventory read | ✅ | Review + text test |
| A4 | Downloading isn't reachable from a tool | ✅ | `server.py` and `api.py` import neither `bundles` nor `indexer`. **Test deliberately broken** — see below |
| A5 | Starts with no network | ✅ | pyang absent from runtime dependencies; offline suite green |

**A4 protected nothing before being broken on purpose.** `from yangmap import
bundles` passed: the AST extractor picked up the *module* (`yangmap`) but
never the *imported name* (`bundles`). Fixed, then verified red before being
verified green.

## B — Ingestion and indexing

| # | Criterion | State | Measurement |
|---|---|---|---|
| B1 | Nokia: 0 errors, > 50,000 paths | ✅ | **50,772 paths**, 1/1 model, 5 s |
| B2 | Cisco IOS-XE: 0 errors | ✅ | **12,123 paths**, 120/120 models |
| B3 | Arista/OpenConfig: 0 errors | ✅ | **9,924 paths**, 89/89 models |
| B4 | Full schema per entry | ✅ | xpath, gNMI path, kind, type, description, module, keys, depth |
| B5 | Idempotent build | ✅ | Double build: same count, FTS5 table not duplicated |
| B6 | A broken model doesn't take down the others | ✅ | Injection of an invalid YANG file: the valid one is indexed, the failure reported |
| B7 | No intermediate CSV survives | ✅ | Directory check |

Description coverage measured on the real indexes: **98% / 97% / 100%**.

## C — Path normalization

| # | Criterion | State | Note |
|---|---|---|---|
| C1 | Module prefix stripped from every segment | ✅ | |
| C2 | Mid-path prefix | ✅ | **Settled by hardware**, not by reasoning — see below |
| C3 | Keys marked `=?` | ✅ | |
| C4 | Multiple keys all kept | ✅ | Real case `[ip-address][mac-address][pppoe-session-id]` |
| C5 | Canonical xpath kept | ✅ | |
| C6 | Pure normalization | ✅ | |

**C2 — the spec claimed the opposite of what the code does.** It said the
prefix was "kept"; the implementation strips it. Tested on `ceos-lab-01`:
**both forms are accepted** by the real equipment. Stripping is therefore
safe, and the spec was corrected based on the measurement.

## D — Version resolution and degraded mode

| # | Criterion | State | Measurement on real bundles |
|---|---|---|---|
| D1 | Exact version served | ✅ | Nokia 24.3.R3 → `24.3.3`, gap `exact` |
| D2 | Same train, gap declared | ✅ | Cisco 17.3.**4a** → `17.3.1` |
| D3 | Train absent, strong warning | ✅ | Tested unit-level |
| D4 | Unknown platform, no fallback | ✅ | BLOCKING criterion held |
| D5 | Message naming the command | ✅ | |
| D6 | No hidden gap | ✅ | Arista 4.32.**11M** → `4.32.2`, gap `same_train` declared — **and the path works anyway on real hardware** |

The fallback is indeed the **normal case on two vendors out of three**, as
the reconnaissance had predicted.

## E — Search and ranking

| # | Criterion | State | Measurement |
|---|---|---|---|
| E1 | Search < 1 s | ✅ | **3 to 100 ms** on 50,772 paths |
| E2 | Description **and** segments searched | ✅ | Tested both directions |
| E3 | Nonsense term ⇒ nothing, never a guess | ✅ | BLOCKING criterion held |
| E4 | **≥ 80% of golden set in the top 5** | ✅ | **100% (21/21)** |
| E5 | ≥ 15 entries, 3 platforms | ✅ | 21 entries: 11 Nokia, 5 Cisco, 5 Arista |
| E6 | Expected paths verified present | ✅ | Probed in the index before being added |
| E7 | The 4 failures from spec §3.4 fixed | ✅ | All in the golden set |
| E8 | Score returned | ✅ | |
| E9 | Limit honored, capped at 50 | ✅ | |
| E10 | Every signal with no effect is removed | ✅ | **Two signals removed** |

**Ranking progression: 65% → 95% → 100%.**

| Signal neutralized | Rate | Delta | Verdict |
|---|---|---|---|
| BM25 descriptions | 76% | −24% | useful |
| BM25 segments | 86% | −14% | useful |
| Exact segment match | 90% | −10% | useful |
| Depth penalty | 95% | −5% | useful |

**Two signals tried and then dropped** for lack of measurable effect at *any*
weight: boosting leaves, and term coverage. E10 forbids keeping them "just in
case."

**Two golden-set entries were fixed because they encoded an author error**,
not a code defect: the ISIS adjacency lives under `interface[]/adjacency`
(the code had found it at rank 3 — it was the expected pattern that was
wrong, copied from a stale netlive comment), and "active and inactive routes"
doesn't name any address family, so requiring `unicast` was testing an intent
the question didn't carry.

## F — MCP contract

| # | Criterion | State | Measurement |
|---|---|---|---|
| F1 | Exactly two tools | ✅ | `yang_chercher`, `yang_detail` |
| F2 | **Immediate** children, not the subtree | ✅ | |
| F3 | Required keys returned | ✅ | |
| F4 | Unknown path ⇒ clear error | ✅ | Points to `yang_chercher` |
| F5 | Short descriptions | ✅ | **< 600 characters** per tool |
| F6 | stdio JSON-RPC not corrupted | ✅ | Real subprocess, full `initialize` |
| F7 | Valid JSON at `limite=50` | ✅ | |

## G — Real-world usage by netlive

| # | Criterion | State | Evidence from the lab |
|---|---|---|---|
| G1 | Paths accepted by netlive's policy | ✅ | > 10 paths per platform, all `allow` |
| G2 | A path actually queries the equipment | ✅ | `/interfaces/interface[name=Ethernet1]/state/oper-status` → **`UP`** |
| G3 | The `route_table` gap from the HANDOFF is closed | ✅ | `direct 3/3, host 0/2, isis 1/1` — **`host` carries 2 available routes for 0 active** |
| G4 | No path crosses the floor | ✅ | BLOCKING criterion held, 5 subjects × 2 platforms |
| G5 | Version from real `Capabilities` | ✅ | `nokia-state` read on the equipment, drives the bundle choice |
| G6 | The model finds what it couldn't find before | ✅ | **Decisive on one obscure path**: 0/2 in 12 calls without, **2/2 in 3 calls with**. Neutral to costly elsewhere — see below |
| G7 | Base context not inflated | ✅ | < 1,200 characters for the 2 tools |

### The serious defect found by confronting the two tools

A path copied back with its key still a template — `[router-name=?]` — was
**accepted by the policy, sent to the equipment**, which answered with an
empty value. The core translated that into `not_configured`, meaning, to the
model, "this feature isn't enabled" — a status the system prompt orders it to
treat as a **FACT**.

**A forgotten key became a confidently wrong conclusion.**

Fixed on both sides:

| Side | Fix |
|---|---|
| netlive | A `=?` key is refused **without contacting the equipment** — `denied` in 0 ms, verified on `sros-lab-01`. The reason states how to fix it |
| yangmap | `action_requise` is emitted as soon as a result carries keys |

### G6 — what the campaign actually showed

The reference question is the one that failed on 2026-08-10: "how many active
and inactive routes on `sros-lab-01`". Three passes:

| Pass | WITHOUT yangmap | WITH yangmap |
|---|---|---|
| 1 — initial state | failure: `denied` in a loop | failure: calls yangmap, then falls back to CLI |
| 2 — after the key safeguard | failure | failure |
| 3 — after the transport description | ✅ **correct figures** | ✅ **correct figures** |

**It's the description fix that unblocked it, not yangmap.** Nothing told the
model that a gNMI-only device refuses all CLI; it spent its calls rephrasing
`show router route-table …` variants, all refused, then concluded "I can't
answer." Once informed of the expected *shape*, it found the Nokia path on
its own — without yangmap.

This is an honest and useful result: **on paths the model already knows,
yangmap adds nothing.**

### The battery that settles G6

Three questions of increasing difficulty, ground truth read directly via gNMI
**before** the campaign, six full passes:

| Question | Config | Expected values found | Calls | yangmap called | Duration |
|---|---|---|---|---|---|
| **Q1** transceiver on port 1/1/c1 | WITHOUT | **0/2** | **12** (budget exhausted) | — | **476 s** |
| | WITH | **2/2** | **3** | yes | **38 s** |
| **Q2** ISIS prefix-SID | WITHOUT | 2/2 | 1 | — | 22 s |
| | WITH | 2/2 | 2 | **no** | 30 s |
| **Q3** LDP sessions (negative answer) | WITHOUT | — correct | 6 | — | 123 s |
| | WITH | — correct | 9 | yes | 216 s |

**Q1 is the case where yangmap is decisive.** Without it, the model invented
plausible, nonexistent Nokia paths — `/state/optical-module` (three times),
`/state/interface`, `/state/transceiver`, `/components` — burned through its
twelve calls, and concluded it had no information. **Eight minutes and twelve
human approvals for nothing.** With yangmap: three calls, thirty-eight
seconds, `qsfp` and `1302 nm`, exact.

**Q2 shows the limit.** `segment_routing` is a named collector in the
catalog: the model used it directly and didn't even call yangmap. Good
instinct — but the extra call to `netlive_instances` cost 8 more seconds.

**Q3 shows the cost when yangmap doesn't help.** Correct answer on both
sides, but 9 calls and 216 s with it, versus 6 and 123 s without: the extra
exploration is wasted effort on a question whose answer is negative.

**Conclusion — G6 ✅, with its caveat:** yangmap is decisive where no named
collector exists and the path is obscure. It's neutral when the catalog
already covers the need, and **costly when it doesn't help**. It complements
the catalog; it doesn't replace it.

## H — Reproducibility

| # | Criterion | State | Measurement |
|---|---|---|---|
| H1 | `fetch` then `build` from nothing | ✅ | Arista from an empty directory: **3.2 s + 2.3 s** |
| H2 | Bundles and indexes not version-controlled | ✅ | `.gitignore` + `git ls-files` |
| H3 | README figures accurate | ✅ | Taken from the measurements above |
| H4 | Every README guarantee has its named test | ✅ | 5 lines, 5 tests |
| H5 | Suite runs without hardware or network | ✅ | 91 tests, `lab`/`build` marks kept separate |

## What remains open

| # | State | Decision |
|---|---|---|
| E4 | ⚠️ | 100% on 21 cases is a good signal, not proof of generality. The golden set will grow with failures observed in use — same logic as `netlive gaps` |

**Avenue opened by Q3**: yangmap costs extra calls when it doesn't help. The
`yang_chercher` description could suggest trying named collectors first. To
be measured before writing it — that's this project's discipline.

## Side effects on netlive

Three changes, all born from this confrontation, all covered by tests:

| Change | Why |
|---|---|
| `LiaisonMultiple` | Several MCP servers presented to the agent as one, without touching the loop |
| `=?` key refused without contact | Prevented a false `not_configured` — the most serious defect of the campaign |
| `netlive_run` described by transport | The model didn't know a gNMI-only device refuses all CLI |

**359 tests outside the lab on the netlive side (+15), 13 against the lab, no
regressions.**
