"""Unit tests for --drop_unknown: which graphs find_unknown_contexts() selects
(src/kgsteward/kgsteward.py).

No server needed: a stub returns the graphs that hold kgsteward's own record,
as the store would answer the selection query."""
from src.kgsteward.kgsteward import find_unknown_contexts

CTX = "http://example.org/context/"


class StubServer:
    """Answers the selection query with the given graphs, as a store would."""

    def __init__( self, recorded ):
        self.recorded = recorded

    def sparql_query( self, sparql, echo = True ):
        bindings = [ { "context": { "type": "uri", "value": c } } for c in self.recorded ]

        class _Response:
            @staticmethod
            def json():
                return { "results": { "bindings": bindings } }

        return _Response()


def _config( *names ):
    return { "dataset": [ { "name": n, "context": CTX + n } for n in names ] }


def test_graph_that_left_the_config_is_selected():
    """'animals' was loaded by kgsteward, then removed from the YAML."""
    server = StubServer( [ CTX + "plants", CTX + "animals" ] )
    assert find_unknown_contexts( server, _config( "plants" ), echo = False ) == [ CTX + "animals" ]


def test_configured_graphs_are_kept():
    server = StubServer( [ CTX + "plants", CTX + "animals" ] )
    assert find_unknown_contexts( server, _config( "plants", "animals" ), echo = False ) == []


def test_graph_without_kgsteward_record_is_never_selected():
    """A graph written by hand has no kgsteward:Dataset record, so the store
    does not return it, whatever the config says."""
    server = StubServer( [ CTX + "plants" ] )
    assert find_unknown_contexts( server, _config( "plants" ), echo = False ) == []
