import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from . import run_cmd, env

# https://hub.docker.com/r/eclipse/rdf4j-workbench
TRIPLESTORE_IMAGE = 'eclipse/rdf4j-workbench:5.1.0'

@pytest.fixture(scope="module")
def triplestore():
    """Start RDF4J container as a fixture."""
    container = DockerContainer(TRIPLESTORE_IMAGE)
    container.with_exposed_ports(8080).with_bind_ports(8080, 8080)
    container.with_env("JAVA_OPTS", "-Xms1g -Xmx4g")
    container.start()
    delay = wait_for_logs(container, "Server startup in")
    base_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8080)}"
    print(f"RDF4J started in {delay:.0f}s at {base_url}")
    # print(container.get_logs())
    yield base_url

def test_cli_rdf4j( triplestore ):
    res_init = run_cmd([ "kgsteward", "doc/first_steps/rdf4j.yaml", "-I"], env)
    print(res_init.stdout)
    assert res_init.returncode == 0

    res_complete = run_cmd([ "kgsteward", "doc/first_steps/rdf4j.yaml", "-C"], env)
    print(res_complete.stdout)
    assert res_complete.returncode == 0

    res_validate = run_cmd([ "kgsteward", "doc/first_steps/rdf4j.yaml", "-V"], env)
    print(res_validate.stdout)
    assert res_validate.returncode == 0
