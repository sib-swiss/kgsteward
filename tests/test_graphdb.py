import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

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
    container = DockerContainer(TRIPLESTORE_IMAGE)
    container.with_exposed_ports(7200).with_bind_ports(7200, 7200)
    container.with_env("JAVA_OPTS", "-Xms1g -Xmx4g")
    container.start()
    delay = wait_for_logs(container, "Started GraphDB")
    # host = container.get_container_host_ip()
    # port = container.get_exposed_port(7200)
    # base_url = f"http://{host}:{port}"
    base_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(7200)}"

    print(f"GraphDB started in {delay:.0f}s at {base_url}")
    # print(container.get_logs())
    yield base_url

cmd_base = [
    "kgsteward doc/first_steps/graphdb.yaml -I -v", # Initialize repository
    "kgsteward doc/first_steps/graphdb.yaml -C -v", # Complete (populate) repository
    "kgsteward doc/first_steps/graphdb.yaml -V -v", # Validate repository
    "kgsteward doc/first_steps/graphdb.yaml -Q -v", # validate Queries 
    "mkdir -p tmp/first_steps",
    "rm -f tmp/first_steps/*.tsv",
    "kgsteward doc/first_steps/graphdb.yaml -x tmp/first_steps -v", # Serialize query results for testing
    "diff -r doc/first_steps/ref tmp/first_steps"
]

cmd_graphdb = [
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_upload_queries -v",
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_upload_prefixes -v",
    "kgsteward doc/first_steps/graphdb.yaml --graphdb_free_access -v",
]

@pytest.mark.parametrize( "cmd", cmd_base + cmd_graphdb )
def test_run_cmd_graphdb( triplestore , cmd):
    print( "##############################################################################" )
    print( "### " + cmd )
    print( "##############################################################################" )
    res = run_cmd( cmd.split( " " ), env )
    print(res.stdout)
    print(res.stderr)
    assert res.returncode == 0
