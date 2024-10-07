# This is a very minimalistic/generic SPARQL client
# that might work on a real triplestore (maybe?)

from dumper  import dump
from .common import *

class GenericClient():

    def __init__( self, endpoint_query, endpoint_update, endpoint_store, echo = True ) :
        self.endpoint_query  = endpoint_query
        self.endpoint_update = endpoint_update
        self.endpoint_store  = endpoint_store

    def ping( self, echo = True ):
        """ test if the server is responding """
        sparql = "SELECT ?hello WHERE{ BIND( 'Hello' AS ?hello )}"
        if echo :
            print( sparql, flush = True )
        r = self.sparql_query( sparql, echo = echo )

    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True ) :
        if echo :
            print( colored( sparql, "green" ), flush = True )
        r = http_call(
            {
                'method'  : 'POST', 
                'url'     : self.endpoint_query,
                'headers' : { 'Accept' : 'application/json' },
                'params'  : { 'query' : sparql }
            },
            status_code_ok,
            echo = echo
        )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200, 204 ], echo = True ):
        if echo :
            print( colored( sparql, "green" ), flush=True )
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'headers' : { 'Content-Type': 'application/x-www-form-urlencoded' },
                'params'  : { 'update': sparql }
            }, 
            status_code_ok, 
            echo = echo
        )

    def sparql_query_to_tsv( self, sparql, status_code_ok=[200], echo=True ) :
        return self.sparql_query(
            sparql,
            accept='text/tab-separated-values',
            status_code_ok=status_code_ok,
            echo=echo,
        )

    def get_contexts( self, echo = True ) :
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {} }", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["g"]["value"] )
        return contexts

    def load_from_file( self, file, context, echo = True ):
        """ use graph store protocol """
        if echo:
            report( 'load file', file )
        with any_open( file, 'rb') as f:
            http_call(
                {
                    'method'  : 'POST',
                    'url'     : self.endpoint_store + "?graph=" + context,
                    'headers' : {
                        'Content-Type' : guess_mime_type( file )
                    },
                    'data'    : f
                },
                [ 200, 201 ] # fuseki 200, GraphDB 201
            )
        
