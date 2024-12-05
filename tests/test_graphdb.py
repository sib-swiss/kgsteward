import os
import pytest
import subprocess
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

# Stop and delete all testcontainers: docker stop $(docker ps -a -q) && docker rm $(docker ps -a -q)
# NOTE: in case issue in rootless docker: https://github.com/testcontainers/testcontainers-python/issues/537
# TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/run/user/$(id -u)/docker.sock pytest -s

TRIPLESTORE_IMAGE = 'ontotext/graphdb:10.8.1'

env = os.environ.copy()
env["GRAPHDB_USERNAME"] = "admin"
env["GRAPHDB_PASSWORD"] = "root"
env["KGSTEWARD_ROOT_DIR"] = os.getcwd()

@pytest.fixture(scope="module")
def triplestore():
    """Start GraphDB container as a fixture."""
    container = DockerContainer(TRIPLESTORE_IMAGE)
    container.with_exposed_ports(7200).with_bind_ports(7200, 7200)
    container.start()
    delay = wait_for_logs(container, "Started GraphDB")
    host = container.get_container_host_ip()
    port = container.get_exposed_port(7200)
    base_url = f"http://{host}:{port}"
    print(f"GraphDB started in {delay:.0f}s at {base_url}")
    # print(container.get_logs())
    yield base_url


def run_cmd(cmd: list[str]):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )

def test_cli(triplestore):
    res_init = run_cmd(["kgsteward", "example/first_steps/first_steps_graphdb.yaml", "-I"])
    assert res_init.returncode == 0
    print(res_init.stdout)

    res_complete = run_cmd(["kgsteward", "example/first_steps/first_steps_graphdb.yaml", "-C"])
    assert res_complete.returncode == 0
    print(res_complete.stdout)

    res_validate = run_cmd(["kgsteward", "example/first_steps/first_steps_graphdb.yaml", "-V"])
    assert res_validate.returncode == 0
    print(res_validate.stdout)
