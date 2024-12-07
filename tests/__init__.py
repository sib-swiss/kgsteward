import subprocess
import os

env = os.environ.copy()
env["KGSTEWARD_ROOT_DIR"] = os.getcwd()

def run_cmd( cmd: list[str], env: dict[ str, str ] = env ):
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )
