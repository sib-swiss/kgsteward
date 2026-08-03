#!/usr/bin/env bash
# Minimal reproducer for:
#   rebuild-index -> Assertion `lower == upper` failed. IndexRebuilder.cpp:112
#
# Root cause: a term CONSTRUCTED at update time (BIND/CONCAT/IRI/...) that equals
# a term already in the base index vocabulary is stored as a distinct local-vocab
# entry (not deduplicated against the base). rebuild-index's materializeLocalVocab
# asserts every local-vocab term is absent from the base (lower == upper); this one
# is present, so it fires. A literal written directly in INSERT DATA is looked up
# and deduplicated, so it does NOT trigger it -- only runtime-constructed terms do.
set -eu
cd "$(dirname "$0")"

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

# Base index already contains the literal "hello".
printf '<http://ex/s> <http://ex/p> "hello" .\n' > seed.nt

qlever index
qlever start --persist-updates
sleep 2

# Insert a triple whose object is the SAME literal "hello", but CONSTRUCTED at
# runtime via BIND(CONCAT(...)) so it enters the delta's local vocabulary.
curl -s "http://localhost:7060/?access-token=tok" \
     -H 'Content-Type: application/sparql-update' \
     --data-binary 'INSERT { <http://ex/s> <http://ex/q> ?v } WHERE { BIND(CONCAT("hel","lo") AS ?v) }'
echo

# EXPECTED: index rebuilt and swapped in.
# ACTUAL:   Rebuilding the index failed: Assertion `lower == upper` failed ...
#           /qlever/src/index/IndexRebuilder.cpp at line 112
qlever rebuild-index --access-token tok

qlever stop
