# `rebuild-index`: `Assertion 'lower == upper' failed` (IndexRebuilder.cpp:112) when an update constructs a term that already exists in the base vocabulary

**Repo:** `ad-freiburg/qlever` (engine). Relates to the `rebuild-index` feature (engine issue #2621).

## Summary

`rebuild-index` aborts with

```
Rebuilding the index failed: Assertion `lower == upper` failed.
Please report this to the developers. In file "/qlever/src/index/IndexRebuilder.cpp" at line 112
```

whenever the located-triples delta contains a term that was **constructed at
update time** (via `BIND` / `CONCAT` / `IRI` / `MD5` / `STR` / ...) and that term
**already exists in the base index's vocabulary**. Such a term is stored as a
fresh *local-vocabulary* entry instead of being deduplicated against the base;
`materializeLocalVocab` then asserts that every local-vocab entry is absent from
the base and fails.

A term written **literally** in `INSERT DATA` is looked up in the vocabulary and
deduplicated, so it does **not** trigger the bug — only runtime-constructed terms do.

The rebuild does not complete (non-destructive: the server keeps serving
base+delta), but the delta can then never be compacted, so it grows until the
server eventually OOM-crashes.

## Root cause (from the source)

`src/index/IndexRebuilder.cpp`, `materializeLocalVocab` (~line 108-112):

```cpp
for (auto* entry : entries) {
    const auto& [lower, upper] = entry->positionInVocab();
    AD_CORRECTNESS_CHECK(lower == upper);      // line 112
    Id id = Id::fromBits(upper.get());
    ...
```

`positionInVocab()` returns the base-vocabulary range where the local term would
sort. `lower == upper` (empty range) means "absent from base"; a non-empty range
means the term is already in the base. The code assumes every local-vocab entry
is new to the base — but a constructed term that collides with an existing base
term violates that, so the check fires. The fix is presumably to deduplicate a
constructed term against the base vocabulary (reuse the base `Id`) rather than
keep a colliding local-vocab entry.

## Minimal reproduction

A **1-triple base** plus **one `INSERT ... WHERE`**. Complete, copy-pasteable:

```bash
mkdir qlever-repro && cd qlever-repro

cat > Qleverfile <<'EOF'
[data]
NAME            = repro
DESCRIPTION     = rebuild-index lower==upper reproducer
[index]
INPUT_FILES     = seed.nt
CAT_INPUT_FILES = cat ${INPUT_FILES}
[server]
PORT            = 7060
HOST_NAME       = localhost
ACCESS_TOKEN    = tok
[runtime]
SYSTEM          = docker
IMAGE           = docker.io/adfreiburg/qlever:latest
EOF

# Base index already contains the literal "hello":
printf '<http://ex/s> <http://ex/p> "hello" .\n' > seed.nt
qlever index
qlever start --persist-updates
sleep 2

# Insert the SAME literal, but CONSTRUCTED at runtime via BIND(CONCAT(...)) so it
# enters the delta's local vocabulary instead of being looked up in the base:
curl -s 'http://localhost:7060/?access-token=tok' \
     -H 'Content-Type: application/sparql-update' \
     --data-binary 'INSERT { <http://ex/s> <http://ex/q> ?v } WHERE { BIND(CONCAT("hel","lo") AS ?v) }'

qlever rebuild-index --access-token tok
# => Rebuilding the index failed: Assertion `lower == upper` failed ... IndexRebuilder.cpp:112

qlever stop
```

Observed variants:

| update | rebuild |
|---|---|
| control: no update | OK ("rebuilt and swapped in") |
| `INSERT DATA { <s> <q> "hello" }` (literal looked up) | **OK** |
| `INSERT { <s> <q> ?v } WHERE { BIND(CONCAT("hel","lo") AS ?v) }` (constructs `"hello"`) | **asserts** |
| `INSERT { <s> <r> ?v } WHERE { BIND(IRI(CONCAT("http://x/","base_iri")) AS ?v) }` colliding with a base IRI | **asserts** |

## Environment

- Image: `adfreiburg/qlever@sha256:6ba10ddf71e7d06ece47eaf927339213c64c342f9ac719ab6c97968d81aef186`
  (server git hash `634ebb2`, compiled 2026-08-03)
- CLI: `qlever-control` git `b64f329`, `SYSTEM=docker` (Docker on macOS; the bug is in the engine, OS-independent)

## Expected

`rebuild-index` succeeds; the constructed term reuses the existing base
vocabulary `Id`.

## Origin

Found while loading a knowledge graph (ReconXKG) live over the Graph Store
Protocol with periodic `rebuild-index` compaction. Loading was insert-only for
~33M triples (17 successful rebuilds); the first failure came from an update that
computes labels/IRIs with `BIND(CONCAT(...))` / `BIND(IRI(...))` / `MD5(...)`
over already-loaded entities, so many constructed terms collided with the base
vocabulary. Reduced to the 1-triple case above.

## Offer

Happy to test a patch or provide the original larger index if useful.
