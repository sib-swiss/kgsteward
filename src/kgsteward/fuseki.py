import time

from dumper import dump
from .common import *

class FusekiClient():

    def __init__( self, fuseki_url, username, password, repository_id ):
        self.fuseki_url           = fuseki_url
        self.username             = username
        self.password             = password
        self.repository_id        = repository_id
        print_break()
        print_task( "contacting server" ) 
        r = http_call({
            'method'  : 'GET',
            'url'     : self.fuseki_url + "/#/"
        },[ 200 ] )        

    def rewrite_repository( self, graphdb_config_filename ) :
        print_warn( "Not yet implemented: FusekiClient.rewrite_repository()" )

    def free_access( self ) :
        print_warn( "Not yet implemented: FusekiClient.free_access()" );

    def sparql_query( self, sparql, accept='application/json', status_code_ok = [ 200 ], echo = True ) :
        if echo :
            print( sparql, flush=True )
        r = http_call({
            'method'  : 'GET',
            'url'     : self.fuseki_url + "/" + self.repository_id + "/sparql",
            'params'  : { 'query': sparql }
        }, status_code_ok, echo )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 204 ], echo = True ) :
        if echo :
            print( sparql, flush=True )
        r = http_call({
            'method'  : 'POST',
            'url'     : self.fuseki_url + "/" + self.repository_id + "/update",
            'params'  : { 'update': sparql }
        }, status_code_ok, echo )

    def sparql_query_to_tsv( self, sparql, status_code_ok=[200], echo=True) :
        return self.sparql_query(
            sparql,
            accept='text/tab-separated-values',
            status_code_ok=status_code_ok,
            echo=echo,
        )

    def get_contexts( self, echo = True ) :
        return set() # FIXME: remove
        r = http_call({
            'method'  : 'GET',
            'url'     : self.fuseki_url + "/#/dataset/" + self.repository_id + "/get",
            'headers' : {
                'Accept'        : 'application/json',
                # 'Authorization' : self.authorization
            }
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( "<" + rec["contextID"]["value"] + ">" )
        return contexts
        
    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        print_warn( "Not yet implemented: FusekiClient.graphdb_call()" )

    def validate_sparql_query( self, sparql, echo = False ):
        print_warn( "Not yet implemented: FusekiClient.validate_sparql_query ()" )
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id,
            'headers' : {
                'Accept'        : 'text/tab-separated-values',
                'Authorization' : self.authorization
            },
            'params'  : {
                'query'   : sparql,
                "infer"   : True,
                "timeout" : 5       # 5 seems to solve a HTTP "problem" observed with a timout of 1 s ?!?
            }
        }, [ 503, 500, 400, 200 ], echo )
        if r.status_code == 503 :
            time.sleep( 1 )
            print( "\t" + "query timed out" )
        elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
            time.sleep( 1 )
            print( "\t" + "unknown error, maybe timeout" )
        elif r.status_code == 400 :
            raise RuntimeError( "Suspected SPARQL syntax error:\n" + sparql )
        else : #  r.status_code == 200 :
            n = r.text.count( "\n" )
            if n == 0 :
                print( "\t" + "!!! empty results !!!" )
            else :
                print( "\t" + str( n ) + " lines returned" )
