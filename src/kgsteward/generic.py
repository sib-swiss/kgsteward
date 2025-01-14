# This is a very minimalistic/generic SPARQL client
# that might work on a real triplestore (maybe?)

import subprocess
import urllib

# How to dump a context from the command line:
# curl -G --data-urlencode "graph=http://example.org/context/ReconX_schema" http://localhost:7200/repositories/ReconXKG2/rdf-graphs/service

from dumper  import dump
from .common import *

class GenericClient():

    def __init__( self, endpoint_query, endpoint_update, endpoint_store ) :
        self.endpoint_query  = endpoint_query
        self.endpoint_update = endpoint_update
        self.endpoint_store  = endpoint_store
        self.headers         = {}
        self.cookies         = {}

    def get_endpoint_query( self ):
        return self.endpoint_query

    def get_endpoint_update( self ):
        return self.endpoint_update
    
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
            print( colored( sparql.replace( "\t", "    " ), "green" ), flush = True )
        r = http_call(
            {
                'method'  : 'POST',  # allows for big query
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
            print( colored( sparql.replace( "\t", "    " ), "green" ), flush = True )
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
    
    def dump_context(
        self,
        context,
        headers = { 'Accept': 'text/plain' }, 
        status_code_ok = [ 200 ], 
        echo = True
    ):
        return http_call({
            'method'  : 'GET',
            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
            'headers' : { **self.headers, **headers }
        }, status_code_ok, echo )

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
 
    def _flush_buf( self, context, data, headers = {}, echo = True ):
        http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
                'headers' : {
                    **headers,
                    'Content-Type' : 'text/plain',
                },
                'cookies' : self.cookies,
                'data'    : data
            },
            [ 200, 201, 204 ], # fuseki 200, GraphDB 204
            echo
    )
        
    def load_from_file_using_riot( self, file, context, headers = {}, echo = True ):
        """ use graph store protocol and riot """
        if echo:
            report( 'load file', file )
        p = subprocess.Popen( [ 'riot', file ], stdout = subprocess.PIPE, text=True ) # riot returns nt format by default
        buf = []
        size = 0
        count = 0
        for line in p.stdout:
            count += 1
            l = len( line )
            if size + l > 1e8 : # aka 100 mega
                report( "triples so far", str( count ))
                self._flush_buf( context, "".join( buf ), headers )
                buf  = [ line ] # rewrite
                size = l        # rewrite
            else:
                buf.append( line )
                size += l
        if size > 0 :
            report( "triples so far", str( count ))
            self._flush_buf( context, "".join( buf ), headers )
