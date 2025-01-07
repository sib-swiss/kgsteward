# This is a very minimalistic/generic SPARQL client
# that might work on a real triplestore (maybe?)

# How to dump a context from the command line:
# curl -G --data-urlencode "graph=http://example.org/context/ReconX_schema" http://localhost:7200/repositories/ReconXKG2/rdf-graphs/service
from dumper  import dump
from .common import *

class GenericClient():

    def __init__( self, endpoint_query, endpoint_update, endpoint_store ) :
        self.endpoint_query  = endpoint_query
        self.endpoint_update = endpoint_update
        self.endpoint_store  = endpoint_store   # FIXME: make it works
        self.headers         = {}
        self.cookies         = {}

    def get_endpoint_query( self ):
        return self.endpoint_query

    def get_endpoint_update( self ):
        return self.endpoint_update
   
#    def ping( self, echo = True ):
#        """ ping server """
#        sparql = "SELECT ?hello WHERE{ BIND( 'Hello' AS ?hello )}"
#        if echo :
#            print( sparql, flush = True )
#        self.sparql_query( sparql, echo = echo )
    
    def get_contexts( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def sparql_query( self, 
        sparql,
        headers = { 
            'Accept' : 'application/json', 
            'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [ 200 ], 
        echo = True ):
        if echo :
            print( colored( sparql, "green" ), flush = True )
        r = http_call(
            {
                'method'  : 'POST', 
                'url'     : self.endpoint_query,
                'headers' : headers,
                'params'  : { 'query' : sparql },
                'cookies' : self.cookies
            },
            status_code_ok,
        )
        return r

    def sparql_query_to_tsv( 
        self, 
        sparql, 
        headers = { 'Accept' :'text/tab-separated-values', 'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [200], 
        echo = True 
    ):
        return self.sparql_query( sparql, headers, status_code_ok, echo )
    
    def sparql_update( 
        self, 
        sparql,
        headers        = { 'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [ 204 ],
        echo           = True
    ):
        if echo :
            print( colored( sparql, "green" ), flush = True )
        http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'headers' : headers,
                'cookies' : self.cookies,
                'params'  : { 'update': sparql },
                'cookies' : self.cookies
            }, 
            status_code_ok,
            echo
        )

    def load_from_file( self, file, context, headers = {}, echo = True ):
        """ use graph store protocol """
        if echo:
            report( 'load file', file )
        with any_open( file, 'rb' ) as f: # NB any_open takes care of decompression
            http_call(
                {
                    'method'  : 'POST',
                    'url'     : self.endpoint_store + "?graph=" + context,
                    'headers' : {
                        **headers,
                        'Content-Type' : guess_mime_type( file )
                    },
                    'cookies' : self.cookies,
                    'data'    : f
                },
                [ 200, 201, 204 ], # fuseki 200, GraphDB 204
                echo
            )       
