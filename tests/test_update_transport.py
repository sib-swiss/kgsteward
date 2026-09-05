"""SPARQL 1.1 Protocol conformance for updates (section 2.2, update via
URL-encoded POST): the ``update`` payload MUST travel in the POST *body*
(application/x-www-form-urlencoded), never in the URL query string.

Regression guard for the graphdb and rdf4j drivers, which formerly handed
``http_call`` a ``params=`` dict (requests appends that to the URL) instead of
``data=`` (request body).  The fuseki and qlever drivers already use ``data=``.
"""

import requests
import pytest

from kgsteward import common
from kgsteward.graphdb import GraphDBClient
from kgsteward.rdf4j import RFD4JClient

UPDATE = "INSERT DATA { GRAPH <http://g> { <http://s> <http://p> <http://o> } }"


class _FakeResponse:
    def __init__( self, status_code ):
        self.status_code = status_code
        self.text = ""
        self.headers = {}


def _make_client( cls ):
    """Instantiate a driver WITHOUT its network __init__: sparql_update only
    needs endpoint_update + headers, and the log state initialises lazily."""
    client = object.__new__( cls )
    client.endpoint_update = "http://example.org/repo/statements"
    client.headers = {}
    return client


@pytest.fixture
def capture_request( monkeypatch ):
    """Record the kwargs of the single requests.request() that http_call issues."""
    captured = {}
    def fake_request( **kwargs ):
        captured.clear()
        captured.update( kwargs )
        return _FakeResponse( 204 )
    monkeypatch.setattr( common.requests, "request", fake_request )
    return captured


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
def test_update_sent_via_body_not_query_string( cls, capture_request ):
    _make_client( cls ).sparql_update( UPDATE, echo = False )
    assert capture_request["method"] == "POST"
    assert capture_request.get( "data" ) == { "update": UPDATE }, \
        f"{cls.__name__}: update must be sent via data= (POST body)"
    assert "params" not in capture_request, \
        f"{cls.__name__}: update must NOT be sent via params= (URL query string)"


@pytest.mark.parametrize( "cls", [ GraphDBClient, RFD4JClient ] )
def test_prepared_request_is_conformant( cls, capture_request ):
    """Prepare the captured request and check the actual bytes on the wire."""
    _make_client( cls ).sparql_update( UPDATE, echo = False )
    prepared = requests.Request(
        method  = capture_request["method"],
        url     = capture_request["url"],
        headers = capture_request.get( "headers" ) or {},
        data    = capture_request.get( "data" ),
        params  = capture_request.get( "params" ),
    ).prepare()

    assert "?" not in prepared.url, \
        f"{cls.__name__}: update leaked into the URL query string: {prepared.url}"
    body = prepared.body.decode() if isinstance( prepared.body, bytes ) else prepared.body
    assert body is not None and "update=" in body
    assert prepared.headers.get( "Content-Type" ) == "application/x-www-form-urlencoded"


def test_requests_params_vs_data_semantics():
    """Anchor documenting WHY the fix matters: params -> URL, data -> body."""
    q = "DROP GRAPH <http://g>"
    via_params = requests.Request( "POST", "http://x/y", params = { "update": q } ).prepare()
    via_data   = requests.Request( "POST", "http://x/y", data   = { "update": q } ).prepare()
    data_body = via_data.body.decode() if isinstance( via_data.body, bytes ) else via_data.body
    assert "update=" in via_params.url and via_params.body is None    # old, non-conformant
    assert via_data.url == "http://x/y" and "update=" in data_body    # new, conformant
