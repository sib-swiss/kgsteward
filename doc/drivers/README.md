<sup>back to [TOC](../README.md)</sup>

# Triplestore drivers

## One workflow, many backends

`kgsteward` drives every triplestore through a single, brand-agnostic workflow.
The `server` object is polymorphic: the generic workflow only ever calls methods
on it (load a file, run an update, list contexts, persist, finalise, …), and
each backend — its *driver* — implements those methods for its own technology.
The `config["server"]["brand"]` value (`graphdb`, `rdf4j`, `fuseki` or `qlever`)
selects which driver is constructed; after that the workflow no longer cares
which one it is talking to.

The drivers fall into two families that behave very differently:

* **Live HTTP backends** — GraphDB, RDF4J, Fuseki. A long-running server is
  contacted over HTTP. Data is ingested with SPARQL `LOAD` / the graph-store
  protocol, and `INSERT`/`DELETE` updates are persisted immediately. **What the
  server serves *is* what `kgsteward` manages**, so a dataset's status can be
  read back directly from the live store.

* **Static-index backend** — qlever. There is no live mutation: every
  `qlever index` invocation rebuilds the *entire* index from scratch from a
  manifest, and SPARQL updates only modify an in-memory delta that is lost when
  the server stops. `kgsteward` therefore keeps the authoritative state on disk
  (one checkpoint file per dataset) and assembles the served index from it.

Most of the per-backend remarks below were gathered while scaling real research
projects up; see also [scaling up](../scaling_up/README.md).

## Live HTTP backends

### GraphDB

* `kgsteward` was developed using GraphDB as its server. Over several years
  GraphDB free edition proved (i) extremely robust (it never crashes),
  (ii) very well aligned with the W3C RDF/SPARQL specifications and
  (iii) trouble-free across software updates.
* The *context index* should be turned **ON** (it is off by default) to increase
  the reactivity of `kgsteward` — the status query enumerates named graphs, which
  is far cheaper with that index.
* Ingestion is immediate: `load_from_file` does an HTTP POST to the running
  server, and each `sparql_update` is persisted as it is sent.

### RDF4J

* GraphDB is built on top of RDF4J, so one might have expected the migration from
  GraphDB to RDF4J to be effortless. It was not really the case — the driver has
  its own quirks to accommodate.

### Fuseki

* Fuseki ships with two on-disk index backends, **TDB** and **TDB2**. Although
  TDB2 is more modern and should allow faster queries, **TDB is currently the
  better choice** with `kgsteward`: TDB2's copy-on-modify indexes grow rapidly
  under many sequential updates or deletions, whereas TDB does not exhibit this.
  TDB2 indexes can be compacted, but that is time-consuming and inconvenient as
  the sizes are otherwise uncontrolled.
* Fuseki applies HTTP basic authentication on every call.

## Static-index backend: qlever

qlever is the most different of the drivers, because it is not a live, mutable
store. The driver mimics the GraphDB-style "process each dataset eagerly" model
on top of a static index.

### Checkpoints are the source of truth

For each managed dataset, `kgsteward` keeps a per-graph **checkpoint** in
`qleverdir`:

* `<safe>_<h8>.nt.gz` — the dataset's full, current content as gzipped
  N-Triples (`<safe>` is a sanitised tail of the context IRI, `<h8>` an IRI-derived
  hash for disambiguation).
* `<safe>_<h8>.nt.gz.json` — a **sidecar** written *after* the `.nt.gz`. Its
  presence is the atomic completeness marker (a crash mid-dump leaves the old
  checkpoint intact), and it records the named-graph IRI and the dataset's
  `kgsteward` checksum so an out-of-date checkpoint can be told from a current one.

The qlever index itself (`<repository>.*`), the `input/` staging area and any
`previous.*`/`rebuild.*` snapshots are **derived artifacts**, fully rebuildable
from the checkpoints. See the YAML reference for the `qleverfile` / `qleverdir`
fields — in particular, the source Qleverfile must live **outside** the
`kgsteward`-managed `qleverdir`.

### Per-dataset flow

For each dataset that is (re)processed: stage its files into `input/`, queue any
`update:` SPARQL, then rebuild the index from all checkpoints (plus the fresh
files), restart the server, replay the queued updates against it, and finally
dump the new checkpoint (which captures index + in-memory delta). An incremental
run (`-C` / `-d`) restricts the rebuilt index to the dependency closure of the
datasets it touches, so unrelated checkpoints stay on disk but out of the served
index until the index is reassembled in full.

### Two extra steps to reach production

Because the served index is only ever a *subset* unless explicitly reassembled,
qlever exposes two driver-specific options:

* `--qlever_complete` — at the end of the session, assemble the **complete**
  index from every checkpoint and build the text index (if `TEXT_INDEX` is set in
  the Qleverfile). This is the only run that guarantees a complete, queryable,
  text-indexed server.
* `--qlever_upload_quads` — a one-shot **bootstrap** from an externally produced
  quad dump (e.g. a big `.nq.gz`): build the index natively from the Qleverfile's
  `INPUT_FILES`, verify the named graphs against the YAML, and capture every graph
  as a checkpoint. ⚠️ This **wipes the entire content of `qleverdir`** first.

### Status: the `READY` state

Because of the assemble-to-publish step, qlever adds a status value the live
backends never need:

```
EMPTY / UPDATE  ──(-C / -d / --qlever_upload_quads)──▶  READY  ──(--qlever_complete)──▶  ok
```

`READY` means *a current checkpoint exists on disk, but the complete
(text-indexed) production index has not been assembled yet*. It is reported, not
acted upon: it tells you the data is staged and up to date, and that a
`--qlever_complete` run is what will put it into production (`ok`).

## Driver comparison

| | Live HTTP backends (GraphDB / RDF4J / Fuseki) | qlever |
|---|---|---|
| ingestion (`load_from_file`) | HTTP POST / graph-store to the running server, immediately | stage file into `input/`, defer to the next index build |
| `sparql_update` | HTTP POST, persisted immediately | queued, applied after the rebuild, then captured into a checkpoint |
| named graphs | standard SPARQL `INTO GRAPH` at load time | `multi_input_json` `graph` key at index time |
| `rewrite_repository` (`-I`) | drop + recreate the repository | wipe `qleverdir`, restore the Qleverfile |
| `drop_context` | `DROP GRAPH` via SPARQL | no-op (the context is simply excluded from the next rebuild) |
| server lifecycle | external, unmanaged | managed via `qlever start` / `stop` / index rebuild |
| served vs managed | identical (status read from the live store) | served index is a subset of the checkpoints; hence the `READY` status |

## Other servers

* Many stores were *de facto* excluded because they do not support SPARQL update
  and/or named graphs (a.k.a. contexts), both of which `kgsteward` relies on.

<sup>back to [TOC](../README.md)</sup>
