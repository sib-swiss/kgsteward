from dumper import dump
import re
import rdflib
import urllib

from .common import *
from .generic import GenericClient

class QleverClient( GenericClient ):

    def __init__( self, location, access_token = None, echo = True  ):
        super().__init__( location, None, None )
        self.access_token = access_token
        try:
            r = http_call({
                'method'  : 'GET', # not supported by qlever, but return 404
                'url'     : location
                }, [ 404 ], echo = echo ) 
        except:
            stop_error( "Cannot contact qlever at location: " + location ) 

    def list_repository( self ):
        return [ "repository" ] # also hardcoded in yamlconfig.py

    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True, timeout = None ):
        if echo :
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept' : 'application/json', 
            'Content-Type': 'application/x-www-form-urlencoded' 
        }
        params = { 'query' : sparql }
        if timeout is not None:
            if not 503 in status_code_ok: # returned by "normal" GraphDB timeout
                status_code_ok.append( 503 ) 
            if not 500 in status_code_ok: # returned by "service" GraphDB timeout
                status_code_ok.append( 500 )
            params["timeout"] = timeout
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_query,
                'headers' : headers,
                'data'    : params,
            },
            status_code_ok,
        )
        if timeout is not None:
            if r.status_code == 503 :
                time.sleep( 1 )
                print_warn( "query timed out" )
                return None
            elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
                time.sleep( 1 )
                print_warn( "status", "unknown error, possibly timeout" )
                return None
        return r
    
    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.sparql_update() is not available" )
        # the code below works with INSERT WHERE clause, but not with LOAD INTO ;-()
        if self.access_token is None:
            raise Exception( "Missing access token: QleverConf.sparql_update()" )
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept' : 'application/qlever-results+json', 
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Bearer ' + self.access_token
        }
        params = { 'update' : sparql }
        r = http_call(
            {
                'method'  : 'POST',  # allows for big query string
                'url'     : self.endpoint_update,
                'headers' : headers,
                'data'    : params,
                # 'cookies' : self.cookies
            },
            status_code_ok,
        )
        return r
        # raise Exception( "Not yet implemented: QleverConf.sparql_update()" )

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.drop_context() is not available" )
        # the code below is nevertheless working
        self.sparql_update( f"DROP GRAPH <{context}>", echo = echo )