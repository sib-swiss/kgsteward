import os
import shutil
import subprocess

import pytest

from . import env, run_cmd

# ---------------------------------------------------------------------------
# Prerequisite checks - skip the whole module if Docker is unavailable.
# ---------------------------------------------------------------------------

def _docker_ok():
    return subprocess.run( ["docker", "info"], capture_output = True ).returncode == 0

pytestmark = pytest.mark.skipif(
    not _docker_ok(), reason = "Docker not available"
)

# ---------------------------------------------------------------------------

FUSEKI_IMAGE  = "stain/jena-fuseki:latest"
FUSEKI_PORT   = 3034   # avoid clash with a developer's local Fuseki on 3030
ROOT_DIR      = env["KGSTEWARD_ROOT_DIR"]
FUSEKI_YAML   = os.path.join( ROOT_DIR, "doc/first_steps/fuseki.yaml" )
FUSEKI_CONFIG = os.path.join( ROOT_DIR, "doc/first_steps/fuseki.config.ttl" )


@pytest.fixture( scope = "module" )
def fuseki_url():
    """Spin up a Fuseki container with the first_steps config and tear it down at session end."""
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    # The stain/jena-fuseki image reads FUSEKI_CONF and serves whatever the
    # config file declares.  Mount the first_steps config read-only at the
    # path the env var points to.
    container = (
        DockerContainer( FUSEKI_IMAGE )
        .with_bind_ports( 3030, FUSEKI_PORT )
        .with_env( "FUSEKI_CONF", "/fuseki/fuseki.config.ttl" )
        .with_volume_mapping( FUSEKI_CONFIG, "/fuseki/fuseki.config.ttl", "ro" )
    )
    container.start()
    try:
        wait_for_logs( container, "Fuseki is available", timeout = 60 )
        base_url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(3030)}"
        print( f"\nFuseki ready at {base_url}" )
        yield base_url
    finally:
        container.stop()


def _fuseki_env( base_url ):
    """Override location so kgsteward talks to the testcontainer rather than 3030."""
    e = env.copy()
    e["KGSTEWARD_FUSEKI_URL"] = base_url
    return e


def test_kgsteward_fuseki_init_complete( fuseki_url ):
    """Run kgsteward against a fresh Fuseki to exercise -I, -C, and -V end-to-end."""
    # The shipped fuseki.yaml hardcodes http://localhost:3030 ; rewrite it on
    # the fly so the kgsteward subprocess hits the testcontainer port.
    yaml_src = open( FUSEKI_YAML ).read()
    yaml_patched = yaml_src.replace(
        "http://localhost:3030", fuseki_url,
    )
    patched_yaml = os.path.join( ROOT_DIR, "doc/first_steps/fuseki.test.yaml" )
    with open( patched_yaml, "w" ) as f:
        f.write( yaml_patched )

    try:
        r_init = run_cmd( ["uv", "run", "kgsteward", patched_yaml, "-I"] )
        print( r_init.stdout )
        print( r_init.stderr )
        assert r_init.returncode == 0, "kgsteward -I failed"

        r_complete = run_cmd( ["uv", "run", "kgsteward", patched_yaml, "-C"] )
        print( r_complete.stdout )
        print( r_complete.stderr )
        assert r_complete.returncode == 0, "kgsteward -C failed"

        r_validate = run_cmd( ["uv", "run", "kgsteward", patched_yaml, "-V"] )
        print( r_validate.stdout )
        print( r_validate.stderr )
        assert r_validate.returncode == 0, "kgsteward -V failed"
    finally:
        if os.path.exists( patched_yaml ):
            os.remove( patched_yaml )
