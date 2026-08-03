import os
import shutil
import subprocess

import pytest

from . import env, run_cmd

# ---------------------------------------------------------------------------
# Prerequisite checks - skip the whole module unless qlever, riot and Docker
# are all available (same gate as test_qlever).
# ---------------------------------------------------------------------------

def _qlever_ok(): return shutil.which( "qlever" ) is not None
def _riot_ok():   return shutil.which( "riot"   ) is not None
def _docker_ok(): return subprocess.run( ["docker", "info"], capture_output = True ).returncode == 0

pytestmark = pytest.mark.skipif(
    not ( _qlever_ok() and _riot_ok() and _docker_ok() ),
    reason = "qlever, riot or docker not available",
)

# ---------------------------------------------------------------------------

QLEVER2_PORT = 7025   # avoid clash with test_qlever (7021/7023) and the bench ports
ROOT_DIR     = env["KGSTEWARD_ROOT_DIR"]
QLEVER2_YAML = os.path.join( ROOT_DIR, "doc/first_steps/qlever2.yaml" )

QLEVERFILE_TEMPLATE = """\
[data]
NAME          = first_steps
DESCRIPTION   = kgsteward qlever2 first_steps test

[index]
INPUT_FILES     = *.nt
CAT_INPUT_FILES = cat ${INPUT_FILES}

[server]
PORT         = """ + str( QLEVER2_PORT ) + """
HOST_NAME    = localhost
ACCESS_TOKEN = kgsteward_test

[runtime]
SYSTEM = docker
IMAGE  = docker.io/adfreiburg/qlever:latest
"""


@pytest.fixture( scope = "module" )
def qlever2_workdir( tmp_path_factory ):
    """A Qleverfile + an empty qleverdir; stop the server on teardown."""
    confdir    = str( tmp_path_factory.mktemp( "qlever2_conf" ) )
    workdir    = str( tmp_path_factory.mktemp( "qlever2_workdir" ) )
    qleverfile = os.path.join( confdir, "Qleverfile" )
    with open( qleverfile, "w" ) as f:
        f.write( QLEVERFILE_TEMPLATE )

    # The shipped qlever2.yaml resolves these from the environment; run_cmd
    # passes the shared `env` dict through to the kgsteward subprocess.
    env["QLEVER_FILE"] = qleverfile
    env["QLEVER_DIR"]  = workdir

    yield { "qleverfile": qleverfile, "qleverdir": workdir }

    subprocess.run( ["qlever", "stop"], cwd = workdir, capture_output = True )
    shutil.rmtree( workdir, ignore_errors = True )
    shutil.rmtree( confdir, ignore_errors = True )


def test_kgsteward_qlever2_init_complete_validate( qlever2_workdir ):
    """End-to-end -I / -C / -V against a live QLever driven purely over the
    Graph Store Protocol, with a per-dataset rebuild-index compaction.

    Mirrors test_fuseki: the same first_steps datasets (foaf ontology + data +
    a SPARQL update) are loaded, then the shipped validation queries must pass
    (query.yaml pins 445 rows for the query test, 0 for the validations).
    """
    r_init = run_cmd( ["uv", "run", "kgsteward", QLEVER2_YAML, "-I"] )
    print( r_init.stdout ); print( r_init.stderr )
    assert r_init.returncode == 0, "kgsteward -I failed"

    r_complete = run_cmd( ["uv", "run", "kgsteward", QLEVER2_YAML, "-C"] )
    print( r_complete.stdout ); print( r_complete.stderr )
    assert r_complete.returncode == 0, "kgsteward -C failed"

    r_validate = run_cmd( ["uv", "run", "kgsteward", QLEVER2_YAML, "-V"] )
    print( r_validate.stdout ); print( r_validate.stderr )
    assert r_validate.returncode == 0, "kgsteward -V failed"


def test_qlever2_data_is_served( qlever2_workdir ):
    """After the end-to-end run the live server must actually serve the loaded
    graphs (proves GSP load + per-dataset rebuild-index landed the data in the
    compacted index, not just the transient delta).  Depends on the previous
    test having populated the store."""
    from src.kgsteward.qlever2 import Qlever2Client

    ctx_ontology = "http://example.org/context/foaf_ontology"
    ctx_data     = "http://example.org/context/foaf_data"

    client = Qlever2Client(
        qlever2_workdir["qleverfile"], qlever2_workdir["qleverdir"], echo = False,
    )
    assert client.is_running, "server must still be running from the -I/-C run"

    def count_in( ctx ):
        r = client.sparql_query(
            f"SELECT ( COUNT(*) AS ?n ) WHERE {{ GRAPH <{ctx}> {{ ?s ?p ?o }} }}",
            echo = False,
        )
        return int( r.json()["results"]["bindings"][0]["n"]["value"] )

    assert count_in( ctx_ontology ) > 0, "foaf ontology graph should hold triples"
    assert count_in( ctx_data )     > 0, "foaf data graph should hold triples"
    print(
        f"\nqlever2 served: ontology={count_in(ctx_ontology)} "
        f"data={count_in(ctx_data)} triples"
    )
