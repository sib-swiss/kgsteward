"""Unit tests for the `$(command)` command-capture form of the `stamp:` field,
hashed into the dataset fingerprint by get_sha256() (src/kgsteward/kgsteward.py).
No server needed — get_sha256 is pure given a config dict + name2context."""
import pytest

from src.kgsteward.kgsteward import get_sha256, name2context

CTX = "http://example.org/context/ds"


def _sha( stamp, yaml_dir = "/tmp" ):
    name2context[ "ds" ] = CTX
    config = {
        "kgsteward_yaml_directory": yaml_dir,
        "dataset": [ { "name": "ds", "context": CTX, "stamp": stamp } ],
    }
    return get_sha256( config, "ds", echo = False )


def test_stamp_command_stable_and_output_sensitive():
    """Same command form → stable fingerprint; different output → different."""
    hello_1 = _sha( [ "$(echo hello)" ] )
    hello_2 = _sha( [ "$(echo hello)" ] )
    world   = _sha( [ "$(echo world)" ] )
    print( f"\n$(echo hello) #1 : {hello_1}"
           f"\n$(echo hello) #2 : {hello_2}"
           f"\n$(echo world)    : {world}" )
    assert hello_1 == hello_2, "same command output → stable fingerprint"
    assert hello_1 != world,   "different command output → different fingerprint"


def test_stamp_command_hashes_stdout_not_just_text( tmp_path ):
    """Identical command text but changed stdout must change the fingerprint —
    proving the command's OUTPUT (not merely the literal string) is hashed."""
    token = tmp_path / "token.txt"
    cmd   = [ f"$(cat {token})" ]
    token.write_text( "2026-01" )
    jan = _sha( cmd )
    token.write_text( "2026-02" )
    feb = _sha( cmd )
    print( f"\n$(cat token)=2026-01 : {jan}\n$(cat token)=2026-02 : {feb}" )
    assert jan != feb, "same command, different stdout → different fingerprint"


def test_stamp_command_failure_aborts():
    """A non-zero exit must fail fast (stop_error → SystemExit)."""
    with pytest.raises( SystemExit ):
        _sha( [ "$(false)" ] )


def test_botched_command_stamp_warns_and_is_treated_as_path( capsys ):
    """A `$(...)` with surrounding text (e.g. a path prefix) is NOT a command:
    it falls back to the file branch, emits a targeted hint, and runs nothing."""
    botched = "/tmp/does-not-exist//$(echo hi)"
    s1 = _sha( [ botched ] )
    s2 = _sha( [ botched ] )
    cap = capsys.readouterr()
    out = cap.out + cap.err
    assert s1 == s2, "stable — no command executed, missing file silently skipped"
    assert "looks like a $(command)" in out, "targeted hint emitted"
    assert s1 != _sha( [ "$(echo hi)" ] ), "not equal to actually running the command"


def test_file_stamp_unaffected( tmp_path ):
    """Backward compatibility: a plain local-file stamp still hashes file content
    and is stable; it is NOT mistaken for a command."""
    f = tmp_path / "stamp.txt"
    f.write_text( "content-A" )
    s1 = _sha( [ str( f ) ], yaml_dir = str( tmp_path ) )
    s2 = _sha( [ str( f ) ], yaml_dir = str( tmp_path ) )
    assert s1 == s2, "unchanged file stamp → stable fingerprint"
    assert s1 != _sha( [ "$(echo hello)" ] ), "file stamp differs from command stamp"
