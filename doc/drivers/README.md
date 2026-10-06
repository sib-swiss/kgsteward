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

* **qlever** — also live, but with a twist: writes land in an in-memory *delta*
  rather than in the on-disk index, so `kgsteward` folds the delta back into the
  index with `qlever rebuild-index` and manages the server process itself.

Most of the per-backend remarks below were gathered while scaling real research
projects up; see also the [user guide](../user_guide/README.md).

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

#### Reclaiming the autocomplete index — `--graphdb_reset_autocomplete`

GraphDB's autocomplete plugin maintains a Lucene suggester under
`<data>/repositories/<repo>/storage/autocomplete/v2/index`. `kgsteward` switches
the plugin on whenever it creates a repository (`-I`), and nothing in the normal
lifecycle ever reclaims what that index accumulates afterwards. On a large
repository rebuilt many times it has been measured at **114 GB**, outweighing
everything else in the data directory — the same repository's Lucene *connector*
index was 823 MB. Short of deleting the repository there was no way to get the
space back.

Switching the plugin off does **not** free anything: it only flips a
configuration flag, and the Lucene segments stay on disk. What releases them is
rebuilding the index with nothing configured, which is what this flag does,
entirely over HTTP — so it works against a server whose filesystem is out of
reach as well:

1. switch the plugin on — `reIndex` refuses to run while it is off, and a
   repository left disabled with a huge index is exactly the case to clean;
2. interrupt any indexing in progress, with retries, as that request may itself
   have to wait behind a running build;
3. remove every configured label predicate, then set `indexIRIs` to false;
4. rebuild, **in a request of its own**;
5. poll the plugin status until it leaves `BUILDING`;
6. restore the on/off state the repository was found in.

The flag runs right after the repository rewrite and *before* any data is
loaded, so the reclaimed space is available to the ingest that follows.

Measured on a test repository of 600k labels over two predicates plus IRI local
names, the index went from 74 MB and 38 Lucene files to 8 KB and a single empty
`segments_*` file.

Two traps are worth knowing, as neither of them produces an error. With
`auto:` standing for `http://www.ontotext.com/plugins/autocomplete#`:

* a rebuild batched into the same `INSERT DATA` as the configuration it depends
  on runs against the **previous** configuration;
* `auto:reIndex` returns within seconds while the rebuild goes on for hours, so
  completion has to be polled on `auto:status`, which reads `BUILDING`, `READY`,
  `NONE` (plugin off) or `CANCELED` — the last being sticky, an interrupted
  build never turning `READY` by itself. While a large build runs the server may
  stop answering plugin queries altogether, so an empty result means nothing.

Autocomplete stops suggesting afterwards, since the label predicates are gone —
which is precisely what frees the disk. Configure them again from the Workbench,
or with `INSERT DATA { <predicate> auto:addLabelConfig "" }`, which starts a
fresh build. That build is expensive, hours at hundreds of MB per minute, so
avoid driving the configuration from an ordinary `update:` dataset: an edit to
the list of predicates would silently launch it inside a routine run.

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

## qlever

QLever serves queries from a compact on-disk index. Writes (Graph Store Protocol
loads and SPARQL updates) do not touch that index: they accumulate in an
in-memory **delta** which is merged into every query result. `kgsteward` starts
the server with `--persist-updates`, so the delta survives a restart, and folds
it into the index with `qlever rebuild-index` — a hot swap, with no downtime.

### Bounding the delta

An unbounded delta is the failure mode of this design: it costs RAM and slows
every query, and past a few tens of millions of triples the server process is
killed. `kgsteward` therefore compacts on two triggers:

* **per dataset** — `queue_persist` + `flush_pending` rebuild the index once a
  dataset has finished loading;
* **mid-operation** — a running count crosses `_COMPACT_THRESHOLD_TRIPLES`
  (10 M) during a long load *or* a long drop, and a rebuild drains it there and
  then.

Dropping a graph needs the same care as loading one, because a drop writes one
deletion marker per triple. A Graph Store Protocol `DELETE` (and SPARQL
`DROP GRAPH`, measured to behave identically) is a single unbounded operation
that no threshold can interrupt, so `drop_context` deletes through a `LIMIT`ed
subselect instead, compacting between chunks.

### Loading

QLever has no usable SPARQL `LOAD`, so `url:` datasets must be downloaded first:
use `url_loader: {method: curl_riot_chunk_store}`. Files go in over the Graph
Store Protocol, chunked through `riot`
(`file_loader: {method: riot_chunk_store}`).

The index itself is only ever an **empty bootstrap** built from a stub input
file, so that the server has something to serve before any data lands; real data
never goes through the Qleverfile `INPUT_FILES`.

### `--qlever_complete`

Builds the text index at the end of the session, if `TEXT_INDEX` is set in the
Qleverfile. Without it the text index is absent, which only affects
`?x ql:contains-word ...` queries.

## Driver comparison

| | GraphDB / RDF4J / Fuseki | qlever |
|---|---|---|
| ingestion (`load_from_file`) | HTTP POST / graph-store to the running server | graph-store POST, chunked through `riot` |
| `sparql_update` | HTTP POST, persisted immediately | HTTP POST into the delta, persisted, compacted later |
| named graphs | standard SPARQL `INTO GRAPH` at load time | `?graph=` on the graph-store endpoint |
| `rewrite_repository` (`-I`) | drop + recreate the repository | wipe `qleverdir`, rebuild the empty bootstrap index |
| `drop_context` | `DROP GRAPH` via SPARQL | `DELETE` in bounded chunks, compacting between them |
| URL datasets | SPARQL `LOAD` | must be downloaded first (`curl_riot_chunk_store`) |
| server lifecycle | external, unmanaged | managed via `qlever start` / `stop` / `rebuild-index` |
| served vs managed | identical (status read from the live store) | identical |

## Other servers

* Many stores were *de facto* excluded because they do not support SPARQL update
  and/or named graphs (a.k.a. contexts), both of which `kgsteward` relies on.

<sup>back to [TOC](../README.md)</sup>
