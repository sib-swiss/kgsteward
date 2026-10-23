"""A timed-out query must not widen the status codes accepted by later calls.

``sparql_query`` declares ``status_code_ok = [ 200 ]``: a mutable default,
built once when the function is defined and shared by every call that does not
pass the argument.  The drivers used to ``.append( 503 )`` and ``.append( 500 )``
to that very list whenever ``timeout`` was set, so a single timed-out query
taught the whole process, for the rest of its life and across every
repository, to accept 503 and 500 as success -- turning a server error into a
silent empty result.

Regression guard for the graphdb, rdf4j and fuseki drivers, which now rebind
``status_code_ok`` to a fresh list instead of mutating the default.  (qlever
never appended.)
"""

import inspect

import pytest

from kgsteward import common
from kgsteward.graphdb import GraphDBClient
from kgsteward.rdf4j import RFD4JClient
from kgsteward.fuseki import FusekiClient

DRIVERS = [ GraphDBClient, RFD4JClient, FusekiClient ]

QUERY = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"


class _FakeResponse:
    def __init__( self, status_code ):
        self.status_code = status_code
        self.text = ""
        self.headers = {}


def _make_client( cls ):
    """Instantiate a driver WITHOUT its network __init__: sparql_query needs
    only the endpoint and the credentials."""
    client = object.__new__( cls )
    client.endpoint_query = "http://example.org/repo"
    client.headers = {}
    client.auth = None
    return client


def _default_status_codes( cls ):
    """The list object the signature carries -- the one that used to grow."""
    return inspect.signature( cls.sparql_query ).parameters["status_code_ok"].default


@pytest.fixture
def respond( monkeypatch ):
    """Reply to every request with a chosen status.  Also neutralises the
    drivers' post-timeout time.sleep( 1 ): they all share the one stdlib time
    module, so patching it once covers them."""
    monkeypatch.setattr( common.time, "sleep", lambda *a, **k: None )
    def install( status ):
        monkeypatch.setattr( common.requests, "request",
                             lambda **kwargs: _FakeResponse( status ) )
    return install


@pytest.mark.parametrize( "cls", DRIVERS, ids = lambda c: c.__name__ )
def test_timeout_does_not_mutate_the_shared_default( cls, respond ):
    before = list( _default_status_codes( cls ) )
    respond( 503 )
    assert _make_client( cls ).sparql_query( QUERY, echo = False, timeout = 1 ) is None
    assert list( _default_status_codes( cls ) ) == before, \
        f"{cls.__name__}: a timed-out query widened the shared default to " \
        f"{_default_status_codes( cls )}"


@pytest.mark.parametrize( "cls", DRIVERS, ids = lambda c: c.__name__ )
def test_later_query_without_timeout_still_rejects_503( cls, respond ):
    """The consequence that bites: after one timeout, an ordinary query that
    gets a 503 must still be an error, not a success with no rows."""
    client = _make_client( cls )
    respond( 503 )
    client.sparql_query( QUERY, echo = False, timeout = 1 )   # times out
    with pytest.raises( Exception, match = "HTTP request failed" ):
        client.sparql_query( QUERY, echo = False )            # no timeout: 503 is an error


@pytest.mark.parametrize( "cls", DRIVERS, ids = lambda c: c.__name__ )
def test_caller_supplied_list_is_left_alone( cls, respond ):
    """Rebinding also protects a list the caller owns and may reuse."""
    mine = [ 200 ]
    respond( 503 )
    _make_client( cls ).sparql_query( QUERY, status_code_ok = mine, echo = False, timeout = 1 )
    assert mine == [ 200 ], f"{cls.__name__}: caller's list was mutated to {mine}"
