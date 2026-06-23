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


def test_checkpoint_sha256_currency( qlever_workdir ):
    """has_checkpoint is currency-aware: the sha256 recorded in the sidecar must
    match the one supplied, so the stopped-server -C resume can tell an
    up-to-date checkpoint from a stale one.  A None sha (or a legacy sidecar
    written before the field existed) falls back to presence-only."""
    import json
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]
    foaf_rdf   = os.path.join( env["KGSTEWARD_ROOT_DIR"], "doc/first_steps/foaf.rdf" )
    ctx = "http://example.org/context/foaf_ontology"

    client = QleverClient( qleverfile, qleverdir, echo = True )
    client.rewrite_repository( echo = True )
    client.load_from_file( foaf_rdf, ctx, echo = True )
    client.mark_rebuild( ctx, "sha-CURRENT" )   # checksum carried into the sidecar
    client.server_start( echo = True )

    # the supplied checksum lands in the sidecar alongside the graph IRI
    sidecar = client.checkpoint_path( ctx ) + ".json"
    with open( sidecar ) as f:
        meta = json.load( f )
    assert meta["graph"]  == ctx
    assert meta["sha256"] == "sha-CURRENT"

    # currency-aware matching
    assert     client.has_checkpoint( ctx, "sha-CURRENT" ), "matching checksum -> current"
    assert not client.has_checkpoint( ctx, "sha-STALE"   ), "different checksum -> stale"
    assert     client.has_checkpoint( ctx ),                "no checksum supplied -> presence-only"

    # legacy sidecar without a sha256 field -> accepted on presence
    meta.pop( "sha256" )
    with open( sidecar, "w" ) as f:
        json.dump( meta, f )
    assert client.has_checkpoint( ctx, "sha-anything" ), "legacy sidecar (no sha) -> accept on presence"


def test_update_set_offline_excludes_frozen( qlever_workdir ):
    """Stopped-server -C: update_set_offline picks datasets lacking a CURRENT
    checkpoint, but NEVER a frozen one (the 'frozen' contract: -C has no effect).
    Uses synthetic context IRIs (no checkpoints) and a local is_running override
    so the shared module server is left untouched for later tests."""
    from src.kgsteward.qlever import QleverClient

    client = QleverClient( qlever_workdir["qleverfile"], qlever_workdir["qleverdir"], echo = True )
    client.is_running = False   # exercise the offline branch without touching the server

    cfg = { "dataset": [ { "name": "live", "frozen": False },
                         { "name": "frz",  "frozen": True  } ] }
    n2c = { "live": "http://example.org/context/never_live",
            "frz":  "http://example.org/context/never_frz" }

    update = client.update_set_offline( [ "live", "frz" ], cfg, n2c, lambda n: "sha-" + n )
    assert update == { "live" }, "frozen dataset must be excluded even without a checkpoint"


def test_plan_index_scope_frozen_parent_warns_not_errors( qlever_workdir ):
    """A required parent without a checkpoint hard-errors -- UNLESS it is frozen,
    in which case it is an intentional exclusion (warn, dependants built without it).
    Synthetic context IRIs (no checkpoints); shared server untouched."""
    import pytest
    from src.kgsteward.qlever import QleverClient

    client = QleverClient( qlever_workdir["qleverfile"], qlever_workdir["qleverdir"], echo = True )
    n2c = { "child": "http://example.org/context/never_child",
            "par":   "http://example.org/context/never_par"  }

    # frozen, checkpoint-less parent -> warn + proceed; scope still set
    cfg_frozen = { "dataset": [ { "name": "child", "parent": [ "par" ] },
                                { "name": "par",   "frozen": True } ] }
    client.plan_index_scope( { "child" }, cfg_frozen, n2c )
    assert client.index_scope == { n2c["child"], n2c["par"] }

    # non-frozen, checkpoint-less required parent -> hard error (SystemExit)
    cfg_strict = { "dataset": [ { "name": "child", "parent": [ "par" ] },
                                { "name": "par",   "frozen": False } ] }
    with pytest.raises( SystemExit ):
        client.plan_index_scope( { "child" }, cfg_strict, n2c )


def test_parse_qleverfile_strips_inline_comments( tmp_path ):
    """parse_qleverfile must strip trailing '# ...' comments from values, so a
    commented TEXT_INDEX line does not corrupt the --text-index argument passed
    to add-text-index during --qlever_complete."""
    from src.kgsteward.qlever import parse_qleverfile

    qf = tmp_path / "Qleverfile"
    qf.write_text(
        "[data]\n"
        "NAME = demo                # the dataset name\n"
        "[server]\n"
        "HOST_NAME = localhost\n"
        "PORT = 7033                # chosen port\n"
        "[runtime]\n"
        "SYSTEM = docker            # container runtime\n"
        "[index]\n"
        "TEXT_INDEX = from_text_records_and_literals    # keep your preference\n"
    )
    location, repository, system, token, text_index = parse_qleverfile( str( qf ) )
    assert repository == "demo"
    assert location   == "http://localhost:7033"
    assert system     == "docker"
    assert text_index == "from_text_records_and_literals"


def test_update_dataset_info_idempotent( qlever_workdir, monkeypatch ):
    """update_dataset_info must converge to EXACTLY ONE kgsteward:Dataset metadata
    set, no matter how many times it runs or what stale state it starts from.

    Regression for the pept_cluster bug: the old INSERT-only form left 8 metadata
    triples (2 stacked sets) after two -C runs.  The DELETE-then-INSERT form must
    collapse any prior metadata -- including a duplicate stacked state -- into a
    single fresh set.  This also exercises the combined DELETE/INSERT/OPTIONAL
    update against a live qlever server (qlever is spec-strict, so a passing run
    here is the real proof the rewritten SPARQL is accepted).

    Runs against the server left up by test_index_rdf_file (foaf graph + its
    void:dataDump triple already present under ctx).
    """
    from src.kgsteward import kgsteward as kg
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]
    ctx        = "http://example.org/context/foaf_ontology"

    client = QleverClient( qleverfile, qleverdir, echo = True )
    assert client.is_running, "Server must be running (depends on test_index_rdf_file)"

    # Wire the module globals update_dataset_info reads; stub the heavy checksum
    # computation (file reads + HTTP HEAD) with a fixed value.
    name = "foaf"
    kg.name2context[ name ] = ctx
    config = { "dataset": [ { "name": name, "context": ctx } ] }
    monkeypatch.setattr( kg, "get_sha256", lambda *a, **k: "deadbeef" )

    # One kgsteward:checksum triple == one metadata set (checksum is the
    # per-set fingerprint; rdf:type would de-dup across sets).
    def n_sets():
        r = client.sparql_query(
            "PREFIX kgsteward: <https://purl.expasy.org/kgsteward/>\n"
            f"SELECT ( COUNT(*) AS ?n ) WHERE {{ GRAPH <{ctx}> {{ <{ctx}> kgsteward:checksum ?o }} }}",
            echo = False,
        )
        return int( r.json()["results"]["bindings"][0]["n"]["value"] )

    def stamp():
        kg.update_dataset_info( client, config, name, echo = True )  # queues the update
        client.server_start( echo = True )                          # flushes it live

    assert n_sets() == 0, "fresh foaf graph should carry no kgsteward:Dataset metadata"

    stamp()
    assert n_sets() == 1, f"first stamp should leave exactly one metadata set, got {n_sets()}"

    stamp()
    assert n_sets() == 1, f"re-stamp must not accumulate metadata, got {n_sets()}"

    # Simulate the pept_cluster bug: inject a second, distinct metadata set.
    client._do_sparql_update(
        "PREFIX kgsteward: <https://purl.expasy.org/kgsteward/>\n"
        "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"
        f"INSERT DATA {{ GRAPH <{ctx}> {{ <{ctx}> a kgsteward:Dataset ; "
        "kgsteward:triples 999 ; "
        "kgsteward:modified \"2000-01-01T00:00:00\"^^xsd:dateTime ; "
        "kgsteward:checksum \"stale\" . }}",
        echo = True,
    )
    assert n_sets() == 2, f"sanity: expected a duplicate stacked set, got {n_sets()}"

    stamp()
    assert n_sets() == 1, f"DELETE-then-INSERT must collapse duplicates to one set, got {n_sets()}"

    print( "\nupdate_dataset_info idempotent: 0 -> 1 -> 1 -> (dup=2) -> 1 metadata set(s)" )


def test_sparql_update_connection_drop_is_reported( qlever_workdir, monkeypatch ):
    """A server crash mid-update (RemoteDisconnected) must surface as a clear
    stop_error, not a raw ConnectionError traceback.

    Regression for finding #4: qlever-server OOM-crashes on a heavy INSERT/DELETE
    materialization, slamming the socket shut.  _do_sparql_update must catch the
    requests.exceptions.ConnectionError, mark the server not-running, record a
    CONNECTION_LOST stats row, and stop_error (sys.exit) with actionable guidance
    -- never let the raw traceback escape.  http_call is monkeypatched so this
    test does not depend on actually OOM-killing a real server.
    """
    import requests
    from src.kgsteward import qlever as qmod
    from src.kgsteward.qlever import QleverClient

    client = QleverClient( qlever_workdir["qleverfile"], qlever_workdir["qleverdir"], echo = True )

    def boom( *a, **k ):
        raise requests.exceptions.ConnectionError(
            "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
        )
    monkeypatch.setattr( qmod, "http_call", boom )

    n_before = len( client.sparql_update_stats )
    with pytest.raises( SystemExit ):
        client._do_sparql_update(
            "INSERT DATA { GRAPH <http://x/g> { <http://x/s> <http://x/p> <http://x/o> } }",
            echo = True,
        )
    assert client.is_running is False, "client must mark server stopped after a connection drop"
    assert len( client.sparql_update_stats ) == n_before + 1, "crash should append one stats row"
    assert client.sparql_update_stats[-1]["http_status"] == "CONNECTION_LOST"
    print( "\nconnection drop mid-update -> clean stop_error + CONNECTION_LOST stats row" )


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


def test_scoped_index_then_complete_index( qlever_workdir ):
    """index_scope restricts an incremental rebuild to a subset of checkpoints
    (partial index); complete_index() reassembles ALL checkpoints (full index).

    Build three independent graphs A, B, C, each with its own checkpoint.  Then
    rebuild with index_scope = {A, B}: the served index must contain A and B but
    NOT C — even though C's checkpoint stays on disk.  Finally complete_index()
    rebuilds from every checkpoint, so C becomes queryable again.

    Self-contained: starts from a clean rewrite_repository, so it does not
    depend on (and is not depended on by) the foaf graph the earlier tests use.
    Placed just before the wipe test, which it leaves a fresh index for.
    """
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]
    foaf_rdf   = os.path.join( env["KGSTEWARD_ROOT_DIR"], "doc/first_steps/foaf.rdf" )
    assert os.path.isfile( foaf_rdf ), f"Test data not found: {foaf_rdf}"

    ctxA = "http://example.org/context/scope_A"
    ctxB = "http://example.org/context/scope_B"
    ctxC = "http://example.org/context/scope_C"

    client = QleverClient( qleverfile, qleverdir, echo = True )
    client.rewrite_repository( echo = True )   # clean slate

    # Build an unscoped checkpoint for each graph (same source bytes, distinct
    # graph IRI is all we need to tell them apart in the index).
    for ctx in ( ctxA, ctxB, ctxC ):
        client.load_from_file( foaf_rdf, ctx, echo = True )
        client.mark_rebuild( ctx )
        client.server_start( echo = True )     # _finalize_index (scope None) + dump
        assert client.has_checkpoint( ctx ), f"checkpoint should exist for {ctx}"

    def graphs_in_index():
        r = client.sparql_query( "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }", echo = False )
        return { b["g"]["value"] for b in r.json()["results"]["bindings"] }

    assert { ctxA, ctxB, ctxC } <= graphs_in_index(), "all three graphs present after unscoped builds"

    # Scoped rebuild: restrict to {A, B}.  Re-stage A so pending_files is
    # non-empty and server_start triggers _finalize_index under the scope.
    client.index_scope = { ctxA, ctxB }
    client.load_from_file( foaf_rdf, ctxA, echo = True )
    client.mark_rebuild( ctxA )
    client.server_start( echo = True )

    g = graphs_in_index()
    assert ctxA in g and ctxB in g, f"scoped index must keep A and B; got {sorted(g)}"
    assert ctxC not in g, f"scoped index must EXCLUDE out-of-scope C; got {sorted(g)}"
    assert client.has_checkpoint( ctxC ), "C's checkpoint must remain on disk, only excluded from the index"

    # complete_index ignores index_scope and reassembles every checkpoint.
    client.complete_index( echo = True )
    g = graphs_in_index()
    assert { ctxA, ctxB, ctxC } <= g, f"complete_index must restore all graphs; got {sorted(g)}"
    print( "\nscoped rebuild excluded C; complete_index restored A, B, C" )


QLEVER_PORT_BOOTSTRAP = 7023   # separate port to avoid clash with the module-scoped fixture


@pytest.fixture( scope = "module" )
def qlever_workdir_bootstrap( tmp_path_factory ):
    """Isolated workdir for test_upload_quads.

    Two small TTL files (one triple each) are placed directly inside qleverdir so
    they survive ``rewrite_repository``'s selective wipe and are accessible when
    the qlever docker container mounts qleverdir.  The Qleverfile uses
    MULTI_INPUT_JSON to assign each file to a distinct named graph, bypassing
    the normal _stage_file / INPUT_FILES path.
    """
    confdir = str( tmp_path_factory.mktemp( "qlever_boot_conf" ) )
    workdir = str( tmp_path_factory.mktemp( "qlever_boot_workdir" ) )

    ctx_a = "http://example.org/context/boot_A"
    ctx_b = "http://example.org/context/boot_B"

    # A single N-Quads file dropped into qleverdir — it survives rewrite_repository
    # (only *.nt.gz, *.nt.gz.json, <repo>.*, input/, previous.*, rebuild.* are wiped).
    # Quad format (nq) carries the graph IRI inline; no "-g" workaround needed.
    nq_file = os.path.join( workdir, "boot_data.nq" )
    with open( nq_file, "w" ) as f:
        f.write( f"<{ctx_a}/s> <{ctx_a}/p> <{ctx_a}/o> <{ctx_a}> .\n" )
        f.write( f"<{ctx_b}/s> <{ctx_b}/p> <{ctx_b}/o> <{ctx_b}> .\n" )

    qleverfile = os.path.join( confdir, "Qleverfile" )
    with open( qleverfile, "w" ) as f:
        f.write(
            "[data]\n"
            "NAME          = boot_test\n"
            "DESCRIPTION   = kgsteward bootstrap test\n"
            "FORMAT        = nq\n"
            "\n"
            "[index]\n"
            "INPUT_FILES     = boot_data.nq\n"
            "CAT_INPUT_FILES = cat ${INPUT_FILES}\n"
            "\n"
            "[server]\n"
            f"PORT         = {QLEVER_PORT_BOOTSTRAP}\n"
            "HOST_NAME    = localhost\n"
            "ACCESS_TOKEN = kgsteward_test\n"
            "\n"
            "[runtime]\n"
            "SYSTEM = docker\n"
            "IMAGE  = docker.io/adfreiburg/qlever:latest\n"
        )

    yield { "qleverfile": qleverfile, "qleverdir": workdir, "ctx_a": ctx_a, "ctx_b": ctx_b }

    subprocess.run( ["qlever", "stop"], cwd = workdir, capture_output = True )
    shutil.rmtree( workdir, ignore_errors = True )
    shutil.rmtree( confdir, ignore_errors = True )


def test_upload_quads( qlever_workdir_bootstrap ):
    """--qlever_upload_quads: bulk-load a quad dump, verify graph reconciliation,
    assert one checkpoint + sidecar per matched graph.

    Two named graphs (boot_A, boot_B) are loaded from tiny TTL files embedded in
    qleverdir via MULTI_INPUT_JSON.  The YAML name2context includes a third dataset
    (boot_C) that is absent from the dump, exercising the 'missing' warning path.
    Sidecars for the two matched graphs must exist; no checkpoint for boot_C.
    """
    from src.kgsteward.qlever import QleverClient

    fix       = qlever_workdir_bootstrap
    ctx_a     = fix["ctx_a"]
    ctx_b     = fix["ctx_b"]
    ctx_c     = "http://example.org/context/boot_C"
    n2c       = { "boot_A": ctx_a, "boot_B": ctx_b, "boot_C": ctx_c }

    client = QleverClient( fix["qleverfile"], fix["qleverdir"], echo = True )

    dumped = client.upload_quads( n2c, echo = True )

    assert set( dumped ) == { ctx_a, ctx_b }, (
        f"upload_quads must return IRIs of matched graphs; got {sorted( dumped )}"
    )
    assert client.is_running, "Server must be running after upload_quads"

    # Each matched graph must have a checkpoint (and its sidecar as completeness marker)
    assert client.has_checkpoint( ctx_a ), "checkpoint sidecar must exist for boot_A"
    assert client.has_checkpoint( ctx_b ), "checkpoint sidecar must exist for boot_B"

    # Missing dataset (in YAML but not in dump) must NOT produce a checkpoint
    assert not client.has_checkpoint( ctx_c ), "no checkpoint for a dataset absent from the dump"

    print( f"\nupload_quads: {len(dumped)} graph(s) bootstrapped; boot_C correctly absent" )


def test_rewrite_repository_full_wipe( qlever_workdir ):
    """rewrite_repository must wipe EVERYTHING qlever or kgsteward owns.

    Runs last in the module so we can verify against the populated state
    that test_index_rdf_file produced.  After the call the qleverdir
    should contain nothing but the freshly-copied Qleverfile, and the
    server should be stopped.
    """
    from src.kgsteward.qlever import QleverClient

    qleverfile = qlever_workdir["qleverfile"]
    qleverdir  = qlever_workdir["qleverdir"]

    client = QleverClient( qleverfile, qleverdir, echo = True )

    # Sanity: prior tests left an on-disk index behind.
    files_before = set( os.listdir( qleverdir ) )
    assert any( f.startswith( "first_steps.index." ) for f in files_before ), (
        f"sanity: expected first_steps.index.* before wipe; got {sorted(files_before)}"
    )

    client.rewrite_repository( echo = True )

    files_after = set( os.listdir( qleverdir ) )
    assert files_after == { "Qleverfile" }, (
        f"rewrite_repository left junk behind: {sorted(files_after - {'Qleverfile'})}"
    )
    assert not client.is_running, "Server should be stopped after rewrite_repository"
    print( f"\nrewrite_repository: {len(files_before)} files → {len(files_after)} (only Qleverfile remains)" )
