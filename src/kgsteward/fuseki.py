"""Apache Jena Fuseki driver for kgsteward.

Mirrors the GraphDBClient pattern: credentials are passed in at __init__
time and propagated to every HTTP call through ``self.auth`` (a
``(username, password)`` tuple consumed by ``requests`` as basic auth).
When ``self.auth`` is ``None`` (no credentials configured), the same
attribute is passed and ``requests`` simply skips the Authorization
header — anonymous Fuseki works unchanged.

The previous implementation used a cookie-based pseudo-login that was
both inadequate (Fuseki's admin endpoints want Basic Auth, not cookies)
and unreachable (no ``/$/server`` GET succeeds anonymously on a default
Fuseki), so all update operations failed with HTTP 401.
"""

import re
import urllib

import rdflib

from .common import *
from .generic import GenericClient


# FIXME: implement curl -XPOST http://localhost:3030/$/compact/TEST?deleteOld=true
# FIXME: test env variable JVM_ARGS


# The SPARQL query that pulls the endpoint paths (query / update / store)
# out of the Fuseki server config TTL for a given fuseki:Service name.
_SERVICE_QUERY = """\
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX fuseki: <http://jena.apache.org/fuseki#>
SELECT ?query ?update ?store
WHERE {
    [] rdf:type fuseki:Service ;
        fuseki:name %r ;
        fuseki:endpoint [ fuseki:operation fuseki:query   ; fuseki:name ?query  ] ;
        fuseki:endpoint [ fuseki:operation fuseki:update  ; fuseki:name ?update ] ;
        fuseki:endpoint [ fuseki:operation fuseki:gsp-rw  ; fuseki:name ?store  ]
}"""


class FusekiClient( GenericClient ):

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__( self, location, repository, config_file,
                  username = None, password = None, echo = True ):
        # Discover the query/update/store endpoint paths declared for the
        # given repository in the Fuseki server config TTL.  The same .ttl
        # file is consumed by Fuseki itself when started with --config.
        g = rdflib.Graph()
        try:
            g.parse( config_file )
        except Exception as e:
            stop_error( f"Cannot parse Fuseki config file {config_file}: {e}" )

        rows = list( g.query( _SERVICE_QUERY % repository ) )
        if not rows:
            stop_error(
                f"No fuseki:Service with name '{repository}' found in {config_file} "
                "(check the [data] / [server] section against the Fuseki config TTL)"
            )
        if len( rows ) > 1:
            print_warn(
                f"Multiple fuseki:Service entries match name '{repository}' in "
                f"{config_file} — using the first."
            )
        row = rows[0]

        super().__init__(
            f"{location}/{repository}/{row.query}",
            f"{location}/{repository}/{row.update}",
            f"{location}/{repository}/{row.store}",
        )
        self.repository = repository
        self.location   = location
        # Basic-auth tuple, threaded into every HTTP call below.  None means
        # "no credentials" — requests then omits the Authorization header.
        self.auth = ( username, password ) if username is not None else None

        # Verify reachability — /$/ping is anonymous on default Fuseki.
        print_task( "contacting server" )
        try:
            http_call(
                { 'method': 'GET', 'url': location + "/$/ping" },
                [ 200 ], echo = echo,
            )
        except Exception:
            stop_error( f"Cannot contact Fuseki at {location}" )

        # If credentials were supplied, verify them against an admin endpoint
        # that *requires* auth — surface the configuration error here rather
        # than at the first update.
        if self.auth is not None:
            try:
                http_call(
                    { 'method': 'GET',
                      'url':    location + "/$/server",
                      'auth':   self.auth },
                    [ 200 ], echo = echo,
                )
            except Exception:
                stop_error( f"Authentication to Fuseki failed at {location} (user={username})" )

        if echo:
            report( "endpoint query",  self.endpoint_query )
            report( "endpoint update", self.endpoint_update )
            report( "endpoint store",  self.endpoint_store )

    # ------------------------------------------------------------------ #
    # Repository lifecycle
    # ------------------------------------------------------------------ #

    def list_repository( self ):
        """Return the list of known repositories.

        Trivial implementation: FusekiClient is bound to a single named
        dataset at construction time (the config TTL had a fuseki:Service
        for it), so we just return that one name.  kgsteward's only
        consumer (the ``repo in server.list_repository()`` check in main())
        is satisfied by this.
        """
        return [ self.repository ]

    def rewrite_repository( self, server_config_filename ):
        """Wipe all data in the configured dataset via SPARQL DROP ALL.

        *server_config_filename* is ignored — provided for cross-backend
        signature parity (GraphDB et al. recreate the repository from a
        config file; Fuseki has nothing equivalent because the dataset
        was declared in the config TTL the server started with).
        """
        self.sparql_update( "DROP ALL" )

    def free_access( self ):
        print_warn( "Not yet implemented: FusekiClient.free_access()" )

    def fuseki_compress_tdb2( self ):
        http_call(
            { 'method': 'POST',
              'url':    f"{self.location}/$/compact/{self.repository}?deleteOld=true",
              'auth':   self.auth },
            [ 200 ],
        )

    # ------------------------------------------------------------------ #
    # SPARQL
    # ------------------------------------------------------------------ #

    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True, timeout = None ):
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        data = { 'query': sparql }
        if timeout is not None:
            # Inherited from GraphDB; Fuseki may behave differently but the
            # extra accepted codes are harmless.
            for code in ( 500, 503 ):
                if code not in status_code_ok:
                    status_code_ok.append( code )
            data["timeout"] = timeout
        r = http_call(
            { 'method':  'POST',  # POST allows for big query strings
              'url':     self.endpoint_query,
              'headers': { 'Accept':       'application/json',
                           'Content-Type': 'application/x-www-form-urlencoded' },
              'data':    data,
              'auth':    self.auth },
            status_code_ok,
        )
        if timeout is not None and r.status_code in ( 500, 503 ):
            time.sleep( 1 )
            print_warn( "query timed out (or unknown server error)" )
            return None
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        tok = self._sparql_update_started( sparql )   # log query BEFORE the POST
        # ``data=`` (form body) — previously ``params=`` was used, which puts
        # the update in the query string and made some Fuseki versions reject
        # the request with HTTP 400 for "no update statement".
        r = http_call(
            { 'method':  'POST',
              'url':     self.endpoint_update,
              'headers': { 'Content-Type': 'application/x-www-form-urlencoded' },
              'data':    { 'update': sparql },
              'auth':    self.auth },
            status_code_ok,
            echo,
        )
        self._sparql_update_finished( tok, getattr( r, "status_code", None ) )
        return r

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        return {
            rec["g"]["value"]
            for rec in r.json()["results"]["bindings"]
            if "g" in rec
        }

    def drop_context( self, context, echo = True ):
        # Graph Store Protocol DELETE — faster than DROP GRAPH for large graphs.
        # echo is ignored here (the DELETE is one request, no payload to print).
        http_call(
            { 'method': 'DELETE',
              'url':    self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
              'auth':   self.auth },
            [ 204, 404 ],   # 204: deleted, 404: graph did not exist (idempotent)
        )
