"""--drop_unknown against a live QLever (src/kgsteward/kgsteward.py).

tests/test_drop_unknown.py covers which graphs find_unknown_contexts() picks,
with a stub server; nothing exercised the drop itself.  QLever is the backend
where that matters most: its drop_context() deletes in bounded chunks over the
Graph Store Protocol and queues a rebuild-index compaction, rather than issuing
one DROP GRAPH.

The run loads the three first_steps datasets, then re-runs against a config
from which foaf_ontology has been removed, with --drop_unknown.  Its graph must
be gone from the store and reported DROPPED, and the graphs still in the config
must be untouched.
"""

import os
import shutil
import subprocess

import pytest

from . import env, run_cmd

def _qlever_ok(): return shutil.which( "qlever" ) is not None
def _riot_ok():   return shutil.which( "riot"   ) is not None
def _docker_ok(): return subprocess.run( ["docker", "info"], capture_output = True ).returncode == 0

pytestmark = pytest.mark.skipif(
    not ( _qlever_ok() and _riot_ok() and _docker_ok() ),
    reason = "qlever, riot or docker not available",
)

QLEVER_PORT = 7026   # test_qlever.py holds 7025
ROOT_DIR    = env["KGSTEWARD_ROOT_DIR"]
FIRST_STEPS = os.path.join( ROOT_DIR, "doc/first_steps" )
QLEVER_YAML = os.path.join( FIRST_STEPS, "qlever.yaml" )

CTX_BASE     = "http://example.org/context/"
CTX_ONTOLOGY = CTX_BASE + "foaf_ontology"      # the one that leaves the config
CTX_DATA     = CTX_BASE + "foaf_data"
CTX_UPDATE   = CTX_BASE + "update_data"

QLEVERFILE_TEMPLATE = """\
[data]
NAME          = drop_unknown
DESCRIPTION   = kgsteward qlever --drop_unknown test

[index]
INPUT_FILES     = *.nt
CAT_INPUT_FILES = cat ${INPUT_FILES}

[server]
PORT         = """ + str( QLEVER_PORT ) + """
HOST_NAME    = localhost
ACCESS_TOKEN = kgsteward_test

[runtime]
SYSTEM = docker
IMAGE  = docker.io/adfreiburg/qlever:latest
"""

# foaf_ontology removed.  Every path is absolute: this config does not sit in
# doc/first_steps, so the relative paths of the shipped dataset.yaml would not
# resolve.
TRIMMED_YAML = """\
version: kgsteward_yaml_3
server:
  brand      : qlever
  qleverfile : ${QLEVER_FILE}
  qleverdir  : ${QLEVER_DIR}
context_base_IRI: http://example.org/context/
file_loader:
  method: riot_chunk_store
url_loader:
  method: curl_riot_chunk_store
queries: []
dataset:
  - name: foaf_data
    file:
      - ${KGSTEWARD_ROOT_DIR}/doc/first_steps/data/Alice.ttl
      - ${KGSTEWARD_ROOT_DIR}/doc/first_steps/data/Bob.ttl
      - ${KGSTEWARD_ROOT_DIR}/doc/first_steps/data/c*mpany.ttl
      - ${KGSTEWARD_ROOT_DIR}/doc/first_steps/data/pr*duct.ttl
  - name: update_data
    parent:
      - foaf_data
    update:
      - ${KGSTEWARD_ROOT_DIR}/doc/first_steps/sparql/update/a_blue_car_for_Alice.rq
"""


@pytest.fixture( scope = "module" )
def qlever_workdir( tmp_path_factory ):
    """A Qleverfile, an empty qleverdir and the trimmed config; stop the
    server on teardown."""
    confdir = str( tmp_path_factory.mktemp( "qlever_drop_conf" ) )
    workdir = str( tmp_path_factory.mktemp( "qlever_drop_workdir" ) )

    qleverfile = os.path.join( confdir, "Qleverfile" )
    with open( qleverfile, "w" ) as f:
        f.write( QLEVERFILE_TEMPLATE )

    trimmed = os.path.join( confdir, "qlever_trimmed.yaml" )
    with open( trimmed, "w" ) as f:
        f.write( TRIMMED_YAML )

    env["QLEVER_FILE"] = qleverfile
    env["QLEVER_DIR"]  = workdir

    yield { "qleverfile": qleverfile, "qleverdir": workdir, "trimmed": trimmed }

    subprocess.run( ["qlever", "stop"], cwd = workdir, capture_output = True )
    shutil.rmtree( workdir, ignore_errors = True )
    shutil.rmtree( confdir, ignore_errors = True )


def _client( wd ):
    from src.kgsteward.qlever import QleverClient
    return QleverClient( wd["qleverfile"], wd["qleverdir"], echo = False )


def _count_in( client, ctx ):
    r = client.sparql_query(
        f"SELECT ( COUNT(*) AS ?n ) WHERE {{ GRAPH <{ctx}> {{ ?s ?p ?o }} }}",
        echo = False,
    )
    return int( r.json()["results"]["bindings"][0]["n"]["value"] )


def test_drop_unknown_removes_the_graph_that_left_the_config( qlever_workdir ):
    # 1. load all three datasets: -I only bootstraps the empty index, -C loads
    r = run_cmd( ["uv", "run", "kgsteward", QLEVER_YAML, "-I"] )
    print( r.stdout ); print( r.stderr )
    assert r.returncode == 0, "kgsteward -I failed"

    r = run_cmd( ["uv", "run", "kgsteward", QLEVER_YAML, "-C"] )
    print( r.stdout ); print( r.stderr )
    assert r.returncode == 0, "kgsteward -C failed"

    client = _client( qlever_workdir )
    before = { c: _count_in( client, c ) for c in ( CTX_ONTOLOGY, CTX_DATA, CTX_UPDATE ) }
    print( f"\nbefore: {before}" )
    assert before[ CTX_ONTOLOGY ] > 0, "foaf_ontology must be loaded to be dropped"
    assert before[ CTX_DATA ]     > 0

    # 2. same store, config without foaf_ontology, with the flag
    r = run_cmd( ["uv", "run", "kgsteward", qlever_workdir["trimmed"],
                  "-C", "--drop_unknown"] )
    print( r.stdout ); print( r.stderr )
    assert r.returncode == 0, "kgsteward -C --drop_unknown failed"
    assert "DROPPED" in r.stdout, "the dropped graph must be reported as DROPPED"
    assert CTX_ONTOLOGY in r.stdout

    # 3. the store must agree with the report
    after = { c: _count_in( client, c ) for c in ( CTX_ONTOLOGY, CTX_DATA, CTX_UPDATE ) }
    print( f"after:  {after}" )
    assert after[ CTX_ONTOLOGY ] == 0, \
        f"foaf_ontology still holds {after[CTX_ONTOLOGY]} triples after --drop_unknown"
    assert after[ CTX_DATA ] == before[ CTX_DATA ], "a configured graph was altered"
    assert CTX_ONTOLOGY not in client.list_context( echo = False ), \
        "the dropped graph must no longer be listed"


def test_second_run_drops_nothing( qlever_workdir ):
    """Idempotence: the graph is gone, so there is nothing left to drop."""
    r = run_cmd( ["uv", "run", "kgsteward", qlever_workdir["trimmed"],
                  "-C", "--drop_unknown"] )
    print( r.stdout ); print( r.stderr )
    assert r.returncode == 0
    assert "DROPPED" not in r.stdout, "nothing should be dropped on the second run"


def test_graph_without_kgsteward_record_is_left_alone( qlever_workdir ):
    """A graph kgsteward never loaded carries no kgsteward:Dataset record and
    must survive --drop_unknown, however unknown it looks."""
    client = _client( qlever_workdir )
    foreign = CTX_BASE + "written_by_hand"
    client.sparql_update(
        f"INSERT DATA {{ GRAPH <{foreign}> {{ <http://s> <http://p> <http://o> }} }}",
        echo = False,
    )
    assert _count_in( client, foreign ) == 1, "the foreign graph must be in place"

    r = run_cmd( ["uv", "run", "kgsteward", qlever_workdir["trimmed"],
                  "-C", "--drop_unknown"] )
    print( r.stdout ); print( r.stderr )
    assert r.returncode == 0
    assert _count_in( client, foreign ) == 1, \
        "a graph kgsteward never loaded must not be dropped"
