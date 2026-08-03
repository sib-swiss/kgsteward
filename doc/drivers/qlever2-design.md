<sup>back to [TOC](../README.md)</sup>

# Design note: a second QLever driver (`qlever2`)

> Status: **design only, not implemented.** This note records the strategy,
> the evidence behind it, and the trade-offs, so the driver can be built (or
> rejected) deliberately. It does not change any existing code.

## 1. Why a second driver

The existing [`qlever`](README.md) driver treats QLever as a **static-index**
backend: every run rebuilds the *entire* on-disk index from a `MULTI_INPUT_JSON`
manifest via `qlever index`, wrapped in a `stop`/`index`/`start` dance, with
checkpoint bookkeeping to know which datasets are current. It is the most
complex driver in the project (~1400 lines) precisely because it owns that whole
lifecycle.

Two things changed the picture:

* QLever now **fully implements the SPARQL 1.1 Graph Store HTTP Protocol
  (GSP)** — verified empirically (image git `634ebb2`): `GET/HEAD/POST/PUT/DELETE`
  all work, `PUT ?graph=<iri>` is an idempotent whole-graph replace, writes need
  the access token as a query parameter, and 500 MB / multi-line-literal payloads
  round-trip byte-identically. QLever can therefore be driven exactly like a
  **live HTTP backend** (Fuseki/GraphDB/RDF4J), the family kgsteward already
  supports well.
* `qlever rebuild-index` (fixed CLI, `qlever-dev/qlever-control`) can fold the
  in-memory update delta back into a compact on-disk index and **hot-swap it in
  with no downtime** — cheaply (see the benchmark in §7).

`qlever2` is the experiment those two facts enable: **run QLever as a live
backend — load data through GSP, compact with `rebuild-index` — instead of
rebuilding a static index from files.** The goal is a much simpler driver that
shares the live-backend code path, at the cost of some QLever-specific tuning.

## 2. Strategy in one sentence

Reuse the **QLever server lifecycle** from the `qlever` driver, reuse the
**GSP chunked-load machinery** from the generic base class / Fuseki driver, and
join them: bring the server up once, load each dataset into its named graph over
GSP, and `rebuild-index` per dataset to keep the delta small.

## 3. What is reused from where

| `qlever2` responsibility | Borrowed from | Notes |
|---|---|---|
| Parse `Qleverfile`, start/stop the Docker server, access token, `ensure_running`, `_qlever(*args)` CLI runner | `qlever.py` | Server is started **once** and stays up across interactive invocations (unlike the per-rebuild stop/start of the static driver). Start with `--persist-updates` so GSP writes survive a restart. |
| Endpoint wiring | new | QLever serves query, update and store at **one** URL, differentiated by verb/params. So `super().__init__(base, base, base)` — simpler than Fuseki, which discovers three distinct paths from a config file. |
| `load_from_file` — chunked GSP load | `generic.py` (`load_from_file_using_riot` / `_flush_buf`) | `riot`→N-Triples, POST ~100 MB chunks to `?graph=<ctx>`. **One override needed**: append `&access-token=…&timeout=1800s` and set `Content-Type: application/n-triples` (the base `_flush_buf` hardcodes `text/plain`, which QLever rejects). This is essentially the only bespoke code. |
| `drop_context` | `fuseki.py` | GSP `DELETE ?graph=<ctx>&access-token=…`. |
| `sparql_update`, `sparql_query`, `list_context` | `qlever2.py` stub / `fuseki.py` | POST `update=`/`query=` bodies (+ token for writes); `SELECT DISTINCT ?g` for contexts. |
| `supports_sparql_load` | new | `False` → forces the GSP path. |
| `queue_persist` / `flush_pending` | no-ops | Durability comes from `--persist-updates`; there is no separate persist step. |
| Compaction + `finalize` | `qlever.py` (`rebuild-index`, `add-text-index`) | See §5–6. |

## 4. Load model and atomicity

For each dataset the generic workflow already does, in order: **drop the context,
load it, write the marker/checksum statement last.** That last write is what makes
the operation atomic *from kgsteward's point of view* — it is the existing,
brand-agnostic contract, so `qlever2` needs **nothing QLever-specific** for
atomicity. The only requirement (also generic) is that reload is
**replace/drop-first**, so redoing an interrupted dataset overwrites its partial
remains rather than merging onto them; GSP `PUT`/`DROP`+`POST` satisfies that.

Because each context is a **distinct named graph**, and QLever serializes writes
(single writer), per-context loads are safe to issue in any order — confirmed
empirically (8 parallel PUTs to distinct graphs, no loss).

## 5. Compaction: per-dataset `rebuild-index`

GSP writes land in QLever's in-memory **located-triples delta**, not the compact
base index. Left unbounded, the delta costs RAM and slows queries. `qlever2`
keeps it bounded by calling `qlever rebuild-index` **after each dataset** — the
delta is folded into the base index and hot-swapped in, so it returns to ~empty
before the next dataset loads.

This is the deliberately simple choice. The benchmark (§7) shows rebuild scales
with *total* index size, so per-dataset rebuild is technically **quadratic** in
total work over a full load (sum over growing totals ≈ (N/2)× a single final
rebuild). But the constant is small — for **small/medium KGs the total is still
seconds to low minutes**, and the code stays trivial (no delta-size threshold
bookkeeping). If a future workload proves large enough for the quadratic term to
hurt (~100 M+ triples), the drop-in upgrade is **threshold-triggered** compaction
(rebuild only when the delta crosses a size τ) — same mechanism, one counter.

## 6. `finalize`: recovering the QLever-specific machinery

The heavy, index-artifact-producing work is concentrated in `finalize()`, off the
interactive path:

1. Flush any pending delta, then one `rebuild-index` to guarantee a fully
   compacted base index.
2. `add-text-index` **after** compaction (the text index is built from the
   corpus; it must run once data is in the base index, and likely has to be
   re-added after any rebuild — *to be confirmed empirically*).

Everything else the static driver carries — `MULTI_INPUT_JSON`, the parallel-parsing
options, the stop/index/start choreography — is not "recovered"; GSP loading makes
it **obsolete**. That obsolescence is exactly where the simplicity comes from.

## 7. Evidence: `rebuild-index` cost

Benchmarked 2026-08-03 with the fixed CLI, Docker on amd64 **emulated** on ARM
macOS (absolutes are pessimistic — read the *scaling*, not the seconds).
Harness: `scratchpad/rebuild-bench.sh`.

Total-size axis (fixed 1 k delta):

| base triples | cold `qlever index` build | `rebuild-index` |
|---|---|---|
| 1 M | 2.72 s | 0.80 s |
| 5 M | 10.4 s | 2.28 s |
| 20 M | 41.7 s | 7.85 s |

Delta axis (fixed 5 M base): 1 k → 2.32 s, 100 k → 2.41 s, 1 M → 3.16 s.

Conclusions:

* Rebuild cost is **∝ total triples (base + delta), ~sublinear** (exponent ≈ 0.8,
  ~0.4 s/M here). Delta size barely matters on its own — it counts only as its
  share of the total, because rebuild rewrites the whole index from memory.
* Rebuild is **~5× cheaper than a cold build** of the same size (it skips
  parse/vocab, working from the in-memory state).
* **GSP cold-load is far slower than `qlever index`** (~81 B/triple, ~0.35 s/MB
  GSP → a 20 M cold load is minutes vs 42 s for the file build). So `qlever2`
  earns its keep on **incremental updates**, not first loads.

## 8. Relationship to `index`-as-cross-brand-transfer

The cold-load weakness (§7) is intentionally **out of scope** for `qlever2`.
Bulk initial loading is being reframed as a general **store-content transfer
between brands** — a mechanism that moves the managed content from one backend to
another — rather than something each driver reinvents. `qlever2` therefore
concentrates on what GSP does well (live, incremental, per-context updates) and
defers first-load bulk ingest to that shared transfer path.

## 9. Pros and cons versus the static `qlever` driver

**Pros**

* **Much simpler** — no manifest, no checkpoint/restamp machinery, no stop/index/start;
  essentially the base-class GSP loader plus one auth/content-type override.
* **Uniform with the live backends** — same `load_from_file`/`drop_context`/
  `sparql_update` surface as Fuseki/GraphDB/RDF4J; one mental model.
* **Truly incremental** — update one dataset = drop + reload its graph; others untouched.
  The static driver rebuilds the whole index on any change.
* **No serving downtime** — the server stays up; loads are live, `rebuild-index` hot-swaps.
* **More robust under Ctrl-C** — the interrupt hits the *client* between atomic GSP
  requests; the server keeps a consistent set of completed writes. Contrast a
  half-finished `qlever index`, which can leave a corrupt on-disk index needing
  `--overwrite-existing` recovery.

**Cons**

* **Quadratic rebuild work** on a full load with per-dataset compaction — fine at
  small/medium scale, needs the threshold upgrade at large scale.
* **Slow cold bulk load** over GSP — mitigated by delegating first loads to the
  cross-brand transfer mechanism (§8).
* **RAM/perf while the delta is live** — bounded by per-dataset rebuild, but the
  peak is one dataset's worth of delta.
* **`--persist-updates` replay** on restart grows with delta size (another reason
  to keep it compacted).
* Loses direct use of QLever-specific ingest tuning (parallel parsing, manifest
  ordering) that the static driver exposes.

## 10. Open questions (deferred, not blocking)

* Does QLever implement SPARQL `MOVE`/`COPY`/`ADD`? If so, load into a staging
  graph then `MOVE` gives atomic whole-graph replace even with chunked input —
  a stronger guarantee than the marker contract alone.
* Does `add-text-index` require the delta compacted first, and does it survive a
  later `rebuild-index`? Determines the exact `finalize` ordering.
* Does `--persist-updates` replay tolerate a truncated tail after a hard server
  kill? (The marker-last contract is the backstop regardless.)

## 11a. Real-world validation (ReconXKG, 2026-08-03)

Run against the production ReconXKG config (29 datasets), Docker on amd64
emulated on ARM macOS, 15.4 GiB Docker VM.

* **Delta-pressure crash: solved.** A first attempt (before the fixes) crashed
  the qlever-server process at ~20M triples while streaming `SwissProt_Human`
  into the delta, and the delta was lost on the auto-restart (the server had
  been started without `--persist-updates`). After adding **`--persist-updates`**
  and **mid-load threshold compaction** (`rebuild-index` every N triples,
  N = 10M here), `SwissProt_Human` loaded in full — **32.7M triples** — plus
  `SwissProt_vocab`; ~34M triples served, 17 compactions, zero crashes.

* **Upstream ceiling: QLever `rebuild-index`.** On the 4th dataset
  (`pept_cluster`, generated by a `GROUP BY`/`MIN` SPARQL update) `rebuild-index`
  hit an **engine assertion** — `Assertion 'lower == upper' failed ... IndexRebuilder.cpp:112` — deterministically, on the accumulated state.
  Because the offending data stays in the state, every subsequent compaction
  fails, so the delta can no longer be drained: it grows, GSP inserts slow to
  ~50 s/chunk (O(delta) located-triples insertion), and the server eventually
  crashes again under delta pressure (~16M triples, with a 34M base already
  resident). This is upstream (same fragile `rebuild-index` area as the CLI bug
  in [qlever-rebuild-index-findings]); it must be fixed in QLever or the
  triggering data avoided.

* **Robustness behaviours confirmed.** Compaction is treated as non-fatal
  (a `rebuild-index` failure warns and continues, data safe in the persisted
  delta); a mid-load server crash is caught (`ConnectionError`) and reported
  with actionable guidance instead of a raw traceback; and a `-C` resume
  correctly skipped the already-loaded datasets and continued.

**Bottom line:** qlever2's own mechanics work — it solved the delta-pressure
problem and behaves safely under failure — but a *full* build of a large KG is
gated by the reliability of QLever's `rebuild-index`. Until that is solid, use
the static `qlever` driver (`qlever index` from files, no `rebuild-index`) for
full cold builds; qlever2 fits incremental / small-medium updates whose
per-dataset compaction does not trip the engine bug.

## 11. Recommendation

Build `qlever2` as a **sibling** of `qlever` (selected via `brand: qlever2`),
keeping the static driver intact, and **benchmark both on a real project** (load
time, RAM, query latency) before deciding whether it replaces the static driver
for any class of workload. Its clear wins are simplicity, incremental updates and
Ctrl-C robustness; its clear limit is large-scale cold loads, which the
cross-brand transfer mechanism is meant to cover.
