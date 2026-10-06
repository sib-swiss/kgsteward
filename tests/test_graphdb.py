import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from docker.errors import DockerException
import os
import time
import requests
from pathlib import Path

from . import run_cmd, env

# Stop and delete all testcontainers: docker stop $(docker ps -a -q) && docker rm $(docker ps -a -q)
# NOTE: in case issue in rootless docker: https://github.com/testcontainers/testcontainers-python/issues/537
# TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/user/$(id -u)/docker.sock uv run pytest -s

# TRIPLESTORE_IMAGE = 'ontotext/graphdb:10.8.6' # latest 10 release with no license
TRIPLESTORE_IMAGE = 'khaller/graphdb-free:latest' # latest 10 release with no license
env["GRAPHDB_USERNAME"] = "admin"
env["GRAPHDB_PASSWORD"] = "root"

@pytest.fixture( scope="module" )
def triplestore():
    """Start GraphDB container as a fixture."""
    # Auto-detect Docker socket if DOCKER_HOST is not set, is just a path, or is the CLI socket
    if "DOCKER_HOST" not in os.environ or os.environ["DOCKER_HOST"].startswith("/") or "docker-cli.sock" in os.environ["DOCKER_HOST"]:
        # Common socket paths to check
        possible_sockets = [
            Path.home() / ".docker/run/docker.sock",  # Docker Desktop (Mac/Linux) standard
            Path("/var/run/docker.sock"),  # Standard Linux
            Path("/run/user") / str(os.getuid()) / "docker.sock",  # Rootless Linux
            Path.home() / "Library/Containers/com.docker.docker/Data/docker.sock",  # Docker Desktop for Mac (raw)
        ]
        
        # If DOCKER_HOST is set but is a path, try to use it as a socket
        if "DOCKER_HOST" in os.environ and os.environ["DOCKER_HOST"].startswith("/"):
             possible_sockets.insert(0, Path(os.environ["DOCKER_HOST"]))

        for socket_path in possible_sockets:
            if socket_path.exists():
                print(f"Discovered Docker socket at {socket_path}")
                os.environ["DOCKER_HOST"] = f"unix://{socket_path}"
                break

    try:
        container = DockerContainer(TRIPLESTORE_IMAGE)
        container.with_exposed_ports(7200).with_bind_ports(7200, 7211)
        container.with_env("JAVA_OPTS", "-Xms1g -Xmx4g")
        container.start()
    except DockerException as e:
        pytest.skip(f"Docker not available: {e}")
    except Exception as e:
        pytest.skip(f"Docker not available: {e}")
    delay = wait_for_logs(container, "Started GraphDB")
    # host = container.get_container_host_ip()
    # port = container.get_exposed_port(7200)
    # base_url = f"http://{host}:{port}"
    base_url = f"http://localhost:7211"

    print(f"GraphDB started in {delay:.0f}s at {base_url}")
    # print(container.get_logs())
    yield base_url

cmd_base = [
    "kgsteward doc/first_steps/graphdb.yaml -I -v", # Initialize repository
    "kgsteward doc/first_steps/graphdb.yaml -C -v", # Complete (populate) repository
    "kgsteward doc/first_steps/graphdb.yaml -V -v", # Validate repository
    "kgsteward doc/first_steps/graphdb.yaml -Q -v", # validate Queries 
    "rm -rf /tmp/first_steps",
    "mkdir -p /tmp/first_steps",
    "kgsteward doc/first_steps/graphdb.yaml --dump_all_select --dump_dir /tmp/first_steps -v", # Serialize all query results for testing
    "diff -r doc/first_steps/ref /tmp/first_steps",
    "rm -rf /tmp/first_steps_ds",
    "mkdir -p /tmp/first_steps_ds",
    "kgsteward doc/first_steps/graphdb.yaml --dump_all_dataset --dump_dir /tmp/first_steps_ds -v", # Dump all dataset contents
    "ls /tmp/first_steps_ds/foaf_data.tsv", # --dump_all_dataset produced the expected file
    "kgsteward doc/first_steps/graphdb.yaml --dump_dataset foaf_ontology,update_data --dump_dir /tmp/first_steps_ds -v", # Dump a subset by name
    "ls /tmp/first_steps_ds/update_data.tsv" # --dump_dataset produced the expected file
]

cmd_graphdb = [
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_upload_queries -v",
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_upload_prefixes -v",
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_free_access -v",
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_reset_autocomplete -v",
]

@pytest.mark.parametrize( "cmd", cmd_base + cmd_graphdb )
def test_run_cmd_graphdb( triplestore , cmd):
    print( "##############################################################################" )
    print( "### " + cmd )
    print( "##############################################################################" )
    res = run_cmd( cmd.split( " " ), env )
    print(res.stdout)
    print(res.stderr)
    assert res.returncode == 0, f"Command failed found:\\n{res.stdout}\\n{res.stderr}"

def test_dump_unknown_dataset_name_errors( triplestore ):
    """--dump_dataset with an unknown name must abort and report it."""
    cmd = "kgsteward doc/first_steps/graphdb.yaml --dump_dataset does_not_exist --dump_dir /tmp -v"
    res = run_cmd( cmd.split( " " ), env )
    print(res.stdout)
    print(res.stderr)
    assert res.returncode != 0, "expected non-zero exit on unknown dataset name"
    assert "Unknown dataset name(s): does_not_exist" in ( res.stdout + res.stderr )


AUTO = "http://www.ontotext.com/plugins/autocomplete#"

def test_graphdb_reset_autocomplete( triplestore ):
    """The autocomplete index is emptied and the plugin left as it was found.

    Everything is asserted over HTTP, as the flag itself works: the Lucene
    segments on disk are not reachable from here, but a suggester that stops
    answering with no label predicate left configured is what releases them."""
    auth = ( env["GRAPHDB_USERNAME"], env["GRAPHDB_PASSWORD"] )
    repo = triplestore + "/repositories/first_steps"

    def update( triple ):
        r = requests.post( repo + "/statements", auth = auth,
                           data = { "update": "INSERT DATA { " + triple + " . }" } )
        assert r.status_code == 204, r.text

    def select( sparql ):
        r = requests.post( repo, auth = auth, data = { "query": sparql },
                           headers = { "Accept": "application/sparql-results+json" } )
        assert r.status_code == 200, r.text
        return r.json()["results"]["bindings"]

    def enabled():
        r = requests.get( triplestore + "/rest/autocomplete/enabled", auth = auth,
                          headers = { "X-GraphDB-Repository": "first_steps" } )
        return r.text.strip().lower() == "true"

    # Index the first_steps data, the configuration and the rebuild being sent
    # separately, as a rebuild batched with the configuration it depends upon
    # would run against the previous one.
    update( f'[] <{AUTO}enabled> true' )
    update( f'<http://xmlns.com/foaf/0.1/name> <{AUTO}addLabelConfig> ""' )
    update( f'[] <{AUTO}indexIRIs> true' )
    update( f'[] <{AUTO}reIndex> ""' )
    for _ in range( 120 ):
        status = select( f"SELECT ?o WHERE {{ ?s <{AUTO}status> ?o }}" )
        if status and status[0]["o"]["value"] == "READY":
            break
        time.sleep( 1 )
    else:
        pytest.fail( "autocomplete index did not build" )
    assert select( f"SELECT ?p WHERE {{ ?p <{AUTO}labelConfig> ?lang }}" ), "nothing configured to index"
    assert select( f'SELECT ?s WHERE {{ ?s <{AUTO}query> "Ali" }}' ), "suggester answers nothing to start with"
    assert enabled()

    res = run_cmd( "kgsteward doc/first_steps/graphdb.yaml --graphdb_reset_autocomplete".split( " " ), env )
    print( res.stdout )
    print( res.stderr )
    assert res.returncode == 0, f"Command failed:\n{res.stdout}\n{res.stderr}"

    assert select( f"SELECT ?p WHERE {{ ?p <{AUTO}labelConfig> ?lang }}" ) == [], "label configuration not emptied"
    assert select( f'SELECT ?s WHERE {{ ?s <{AUTO}query> "Ali" }}' ) == [], "suggester still answering"
    assert enabled(), "plugin was switched on, it must be left on"
