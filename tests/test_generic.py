"""GenericClient polymorphic-hook defaults.

The brand-agnostic kgsteward workflow calls these hooks unconditionally, so the
GenericClient defaults must be safe no-ops / sane values for a live HTTP backend
(graphdb / fuseki / rdf4j).  No server or docker needed -- pure contract test."""

from src.kgsteward.generic import GenericClient


def _client():
    return GenericClient( "http://x/query", "http://x/update", "http://x/store" )


def test_default_hooks_are_safe_noops():
    c = _client()
    n2c = { "a": "http://example.org/context/a" }

    # live backends ingest via SPARQL LOAD
    assert c.supports_sparql_load is True

    # lifecycle hooks are no-ops: must not raise and return None
    assert c.queue_persist( n2c["a"], "sha" )                 is None
    assert c.flush_pending( echo = False )                    is None
    assert c.finalize( True,  echo = False )                  is None
    assert c.finalize( False, echo = False )                  is None
    assert c.ensure_running( echo = False )                   is None
