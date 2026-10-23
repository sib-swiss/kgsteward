"""SPARQL 1.1 Protocol conformance for queries (section 2.1.3, query via
URL-encoded POST) and updates (section 2.2): the ``query`` and ``update``
payloads MUST travel in the POST *body* (application/x-www-form-urlencoded),
never in the URL query string.

Regression guard for the graphdb and rdf4j drivers, which formerly handed
``http_call`` a ``params=`` dict (requests appends that to the URL) instead of
``data=`` (request body).  A query in the URL overruns GraphDB's 8192-byte
request line and comes back as a bare HTTP 400 naming neither the query nor
the length.  The fuseki and qlever drivers already use ``data=``.
"""

from collections import namedtuple

import requests
import pytest

from kgsteward import common
from kgsteward.graphdb import GraphDBClient
from kgsteward.rdf4j import RFD4JClient

QUERY  = "SELECT * WHERE { ?s ?p ?o } LIMIT 1"
UPDATE = "INSERT DATA { GRAPH <http://g> { <http://s> <http://p> <http://o> } }"

Op = namedtuple( "Op", "key sparql method status" )

OPS = [
    Op( "query",  QUERY,  "sparql_query",  200 ),
    Op( "update", UPDATE, "sparql_update", 204 ),
]


class _FakeResponse:
    def __init__( self, status_code ):
        self.status_code = status_code
        self.text = ""
        self.headers = {}


def _make_client( cls ):
    """Instantiate a driver WITHOUT its network __init__: sparql_query and
    sparql_update only need the endpoints + headers, and the log state
    initialises lazily."""
    client = object.__new__( cls )
    client.endpoint_query  = "http://example.org/repo"
    client.endpoint_update = "http://example.org/repo/statements"
    client.headers = {}
    return client


@pytest.fixture
def capture_request( monkeypatch ):
    """Install a fake requests.request() replying with `status`, and hand back
    the dict in which its kwargs are recorded."""
    captured = {}
    def install( status ):
        def fake_request( **kwargs ):
            captured.clear()
            captured.update( kwargs )
            return _FakeResponse( status )
        monkeypatch.setattr( common.requests, "request", fake_request )
        return captured
    return install


def _call( cls, op ):
    getattr( _make_client( cls ), op.method )( op.sparql, echo = False )


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
@pytest.mark.parametrize( "op", OPS, ids = lambda op: op.key )
def test_sent_via_body_not_query_string( cls, op, capture_request ):
    captured = capture_request( op.status )
    _call( cls, op )
    assert captured["method"] == "POST"
    assert captured.get( "data" ) == { op.key: op.sparql }, \
        f"{cls.__name__}.{op.method}: must be sent via data= (POST body)"
    assert "params" not in captured, \
        f"{cls.__name__}.{op.method}: must NOT be sent via params= (URL query string)"


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
@pytest.mark.parametrize( "op", OPS, ids = lambda op: op.key )
def test_prepared_request_is_conformant( cls, op, capture_request ):
    """Prepare the captured request and check the actual bytes on the wire."""
    captured = capture_request( op.status )
    _call( cls, op )
    prepared = requests.Request(
        method  = captured["method"],
        url     = captured["url"],
        headers = captured.get( "headers" ) or {},
        data    = captured.get( "data" ),
        params  = captured.get( "params" ),
    ).prepare()

    assert "?" not in prepared.url, \
        f"{cls.__name__}.{op.method}: leaked into the URL query string: {prepared.url}"
    body = prepared.body.decode() if isinstance( prepared.body, bytes ) else prepared.body
    assert body is not None and f"{op.key}=" in body
    assert prepared.headers.get( "Content-Type" ) == "application/x-www-form-urlencoded"


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
def test_long_query_leaves_the_request_line_short( cls, capture_request ):
    """The failure seen in the wild: a 10 kB .rq percent-encodes to ~12 kB of
    URL, overruns Tomcat's 8192-byte request line and is rejected as a bare
    HTTP 400.  In the body the request line stays a few dozen bytes."""
    long_query = "# " + "x" * 10000 + "\n" + QUERY
    captured = capture_request( 200 )
    _make_client( cls ).sparql_query( long_query, echo = False )
    prepared = requests.Request(
        method  = captured["method"],
        url     = captured["url"],
        headers = captured.get( "headers" ) or {},
        data    = captured.get( "data" ),
        params  = captured.get( "params" ),
    ).prepare()
    assert len( prepared.url ) < 8192, \
        f"{cls.__name__}: query inflated the request line to {len( prepared.url )} bytes"
    body = prepared.body.decode() if isinstance( prepared.body, bytes ) else prepared.body
    assert len( body ) > 10000


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
def test_query_timeout_travels_in_the_body( cls, capture_request ):
    """`timeout` is form-encoded alongside the query; GraphDB answers 503 when
    it fires, which the driver turns into None."""
    captured = capture_request( 503 )
    r = _make_client( cls ).sparql_query( QUERY, status_code_ok = [ 200 ], echo = False, timeout = 1 )
    assert captured.get( "data" ) == { "query": QUERY, "timeout": 1 }
    assert "params" not in captured
    assert r is None


@pytest.mark.parametrize( "key", [ "query", "update" ] )
def test_requests_params_vs_data_semantics( key ):
    """Anchor documenting WHY the fix matters: params -> URL, data -> body."""
    sparql = "DROP GRAPH <http://g>"
    via_params = requests.Request( "POST", "http://x/y", params = { key: sparql } ).prepare()
    via_data   = requests.Request( "POST", "http://x/y", data   = { key: sparql } ).prepare()
    data_body = via_data.body.decode() if isinstance( via_data.body, bytes ) else via_data.body
    assert f"{key}=" in via_params.url and via_params.body is None    # old, non-conformant
    assert via_data.url == "http://x/y" and f"{key}=" in data_body    # new, conformant
