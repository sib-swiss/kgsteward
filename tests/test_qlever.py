import pytest
import shutil
import subprocess
import os
from pathlib import Path

from . import env

# ─── prerequisite checks ─────────────────────────────────────────────────────

def _qlever_ok(): return shutil.which( "qlever" ) is not None
def _riot_ok():   return shutil.which( "riot"   ) is not None
def _docker_ok(): return subprocess.run( ["docker", "info"], capture_output=True ).returncode == 0

pytestmark = pytest.mark.skipif(
    not ( _qlever_ok() and _riot_ok() and _docker_ok() ),
    reason = "qlever, riot or docker not available"
)

# ─── Qleverfile template ──────────────────────────────────────────────────────

QLEVER_PORT = 7021   # avoid clash with the default 7019

QLEVERFILE_TEMPLATE = """\
[data]
NAME          = first_steps
DESCRIPTION   = kgsteward first_steps test

[index]
INPUT_FILES     = *.ttl
CAT_INPUT_FILES = cat ${INPUT_FILES}
SETTINGS_JSON   = { "num-triples-per-batch": 1000000 }

[server]
PORT         = """ + str( QLEVER_PORT ) + """
HOST_NAME    = localhost
ACCESS_TOKEN = kgsteward_test

[runtime]
SYSTEM = docker
IMAGE  = docker.io/adfreiburg/qlever:latest
"""

# ─── fixture ─────────────────────────────────────────────────────────────────

@pytest.fixture( scope = "module" )
def qlever_workdir( tmp_path_factory ):
    """Create a temporary qleverdir and a separate Qleverfile; stop qlever on teardown."""
    confdir    = str( tmp_path_factory.mktemp( "qlever_conf" ))
    workdir    = str( tmp_path_factory.mktemp( "qlever_workdir" ))
    qleverfile = os.path.join( confdir, "Qleverfile" )
    with open( qleverfile, "w" ) as f:
        f.write( QLEVERFILE_TEMPLATE )

    env["QLEVER_FILE"] = qleverfile
    env["QLEVER_DIR"]  = workdir

    yield { "qleverfile": qleverfile, "qleverdir": workdir }

    # Teardown: stop qlever server if it is still running
    subprocess.run( ["qlever", "stop"], cwd = workdir, capture_output = True )
    shutil.rmtree( workdir, ignore_errors = True )
    shutil.rmtree( confdir, ignore_errors = True )

# ─── tests ───────────────────────────────────────────────────────────────────

def test_index_rdf_file( qlever_workdir ):
    """Stage foaf.rdf (RDF/XML → riot → N-Triples), build qlever index,
    start the server, and verify the triple count via SPARQL."""
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]
    foaf_rdf   = os.path.join( env["KGSTEWARD_ROOT_DIR"], "doc/first_steps/foaf.rdf" )
    assert os.path.isfile( foaf_rdf ), f"Test data not found: {foaf_rdf}"

    ctx = "http://example.org/context/foaf_ontology"

    client = QleverClient( qleverfile, qleverdir, echo = True )
    client.rewrite_repository( echo = True )
    client.load_from_file( foaf_rdf, ctx, echo = True )
    client.mark_rebuild( ctx )           # queue a dump_checkpoint sentinel
    client.server_start( echo = True )   # triggers _finalize_index + dump

    assert client.is_running, "Server should be running after server_start"
    assert client.has_checkpoint( ctx ), "Checkpoint sidecar should exist after server_start"

    r = client.sparql_query(
        "SELECT ( COUNT(*) AS ?n ) WHERE { ?s ?p ?o }",
        echo = True
    )
    assert r is not None
    n = int( r.json()["results"]["bindings"][0]["n"]["value"] )
    assert n > 0, f"Expected triples after indexing foaf.rdf, got {n}"
    print( f"\nfoaf.rdf indexed: {n} triples; checkpoint saved" )


def test_drop_context_is_noop_and_invalidate_clears_checkpoint( qlever_workdir ):
    """drop_context is intentionally a no-op for qlever — verify its documented
    semantics, and that invalidate_checkpoint is the real removal path.

    Rationale: qlever does not support DROP GRAPH, and a DELETE WHERE on a
    large graph can OOM-kill the server.  In the per-dataset architecture a
    context is removed by (a) calling invalidate_checkpoint to drop the
    ``.nt.gz`` and its sidecar, and (b) letting the next _finalize_index
    rebuild the index from the remaining checkpoints — the dropped context
    is simply absent from the rebuild.
    """
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]
    ctx        = "http://example.org/context/foaf_ontology"

    client = QleverClient( qleverfile, qleverdir, echo = True )
    assert client.is_running, "Server must be running (depends on test_index_rdf_file)"

    r = client.sparql_query( f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{ctx}> {{ ?s ?p ?o }} }}", echo = False )
    n_before = int( r.json()["results"]["bindings"][0]["n"]["value"] )
    assert n_before > 0, "graph should have triples before drop"

    # drop_context: no-op; the live server still serves the data
    client.drop_context( ctx, echo = True )
    r = client.sparql_query( f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{ctx}> {{ ?s ?p ?o }} }}", echo = False )
    n_after_noop = int( r.json()["results"]["bindings"][0]["n"]["value"] )
    assert n_after_noop == n_before, (
        f"drop_context should be a no-op for qlever; got {n_before} → {n_after_noop}"
    )

    # The actual removal path: invalidate the checkpoint sidecar so the next
    # _finalize_index rebuild excludes this context.
    assert client.has_checkpoint( ctx ), "checkpoint should exist before invalidate"
    client.invalidate_checkpoint( ctx )
    assert not client.has_checkpoint( ctx ), "checkpoint should be gone after invalidate"
    print( f"\ndrop_context no-op (data stays at {n_after_noop} triples) + checkpoint invalidated" )
