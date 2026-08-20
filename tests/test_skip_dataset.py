"""Unit tests for the -s option (skip datasets for one run), implemented as the
`name_to_skip` argument of update_config() (src/kgsteward/kgsteward.py).

No server and no network needed: a stub server returns an empty status result,
and the proof that a skipped dataset is never fingerprinted is a `stamp:` of the
`$(command)` form whose side effect (creating a file) is observable.  This is the
crux of the option -- a dataset pointing at an unresponsive remote must not be
probed at all, otherwise it still blocks the run."""
import pytest

from src.kgsteward.kgsteward import update_config, name2context, context2name

CTX = "http://example.org/context/"


class StubServer:
    """Minimal stand-in: update_config only needs one status query, and an empty
    result set means 'no dataset known to the store yet'."""

    class _Response:
        @staticmethod
        def json():
            return { "results": { "bindings": [] } }

    def sparql_query( self, sparql, echo = True ):
        return self._Response()


def _dataset( name, **kwargs ):
    """A dataset record with the defaults yamlconfig would have filled in."""
    rec = {
        "name": name, "context": CTX + name, "frozen": False,
        "count": "", "date": "", "sha256": "", "status": "EMPTY",
    }
    rec.update( kwargs )
    name2context[ name ] = rec["context"]
    context2name[ rec["context"] ] = name
    return rec


def _run( datasets, skip, tmp_path ):
    config = { "kgsteward_yaml_directory": str( tmp_path ), "dataset": datasets }
    return update_config( StubServer(), config, name_to_skip = set( skip ), echo = False )


def _status( config, name ):
    return next( i["status"] for i in config["dataset"] if i["name"] == name )


def test_skipped_dataset_is_not_fingerprinted( tmp_path ):
    """The skipped dataset's stamp command must NOT run -- had it run, its
    remote equivalent (an HTTP HEAD) would have run too, and hung."""
    witness = tmp_path / "probed.txt"
    config  = _run(
        [ _dataset( "ds", stamp = [ f"$(touch {witness})" ] ) ],
        skip = [ "ds" ],
        tmp_path = tmp_path,
    )
    print( f"\nstatus  : {_status( config, 'ds' )}"
           f"\nprobed  : {witness.exists()}" )
    assert not witness.exists(), "skipped dataset must not be probed at all"
    assert _status( config, "ds" ) == "SKIPPED"
    assert "target_sha256" not in config["dataset"][0], "no checksum was computed"


def test_unskipped_sibling_still_processed( tmp_path ):
    """One skipped dataset must not stop the others -- the whole point."""
    witness = tmp_path / "probed.txt"
    config  = _run(
        [ _dataset( "dead" ), _dataset( "alive", stamp = [ f"$(touch {witness})" ] ) ],
        skip = [ "dead" ],
        tmp_path = tmp_path,
    )
    print( f"\ndead  : {_status( config, 'dead' )}"
           f"\nalive : {_status( config, 'alive' )} probed={witness.exists()}" )
    assert _status( config, "dead" )  == "SKIPPED"
    assert _status( config, "alive" ) == "UPDATE", "unknown to the store -> rebuilt"
    assert witness.exists(), "the surviving dataset was fingerprinted as usual"


def test_child_of_skipped_parent_is_not_propagated( tmp_path ):
    """As with 'frozen': whether a skipped parent changed is unknown, so its
    children must not be dragged into a rebuild."""
    # Control run, nothing skipped: the parent is unknown to the store, hence
    # UPDATE, which cascades onto the child.
    child  = _dataset( "child", parent = [ "parent" ] )
    config = _run( [ _dataset( "parent" ), child ], skip = [], tmp_path = tmp_path )
    print( f"\ncontrol -> parent : {_status( config, 'parent' )}"
           f"\ncontrol -> child  : {_status( config, 'child' )}" )
    assert _status( config, "child" ) == "PROPAGATE", "control: the cascade does happen"

    # Same setup, but the child's own inputs now match what the store holds, so
    # propagation from the parent is the only thing that could move it.
    child["sha256"] = child["target_sha256"]
    config = _run( [ _dataset( "parent" ), child ], skip = [ "parent" ], tmp_path = tmp_path )
    print( f"\nparent : {_status( config, 'parent' )}"
           f"\nchild  : {_status( config, 'child' )}" )
    assert _status( config, "parent" ) == "SKIPPED"
    assert _status( config, "child" )  == "ok", "no cascade from a skipped parent"
