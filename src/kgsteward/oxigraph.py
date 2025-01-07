from dumper import dump
import re
from .common import *
from .generic import GenericClient

class OxigraphClient( GenericClient ):

    def __init__( self, oxigraph_url ):
        self.oxigraph_url = oxigraph_url
        super().__init__(  
            oxigraph_url + "/query", 
            oxigraph_url + "/update",
            oxigraph_url + "/data"
        )

    def ping( self ):
        super().ping()
        #r = http_call({
        #    'method'  : 'GET',
        #           'url'     : self.oxigraph_url + "/#/"
        #       },[ 200 ] )
        #ignore = super().ping()
        #print( "OK" )

    def rewrite_repository( self, server_config_filename ) :
        self.sparql_update( "DROP ALL")

    def free_access( self ) :
        print_warn( "Not yet implemented: FusekiClient.free_access()" );

    def sparql_query( 
        self, sparql, 
        headers = { 
            'Content-Type' : 'application/x-www-form-urlencoded', 
            'Accept'       : 'application/json'
        }, 
        status_code_ok = [ 200 ], 
        echo = True 
    ):
        return super().sparql_query( 
            sparql, 
            headers = headers, 
            status_code_ok = status_code_ok, 
            echo = echo
        )
    
    # on success fuseki return 200, not 204 !!!
    def sparql_update( 
        self, 
        sparql,
        headers = { 'Content-Type' : 'application/x-www-form-urlencoded' },
        status_code_ok = [ 204 ], 
        echo = True
    ):
        super().sparql_update( 
            sparql, 
            headers = headers,
            status_code_ok = status_code_ok, 
            echo = echo 
        )

    def sparql_query_to_tsv( self, sparql, status_code_ok = [200], echo=True) :
        return self.sparql_query(
            sparql,
            accept='text/tab-separated-values',
            status_code_ok=status_code_ok,
            echo=echo,
        )
        
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

    def load_from_url( self, url, context, tmpdir = "/tmp", echo = True ):
        if re.search( r"\.ttl$", url ):
            self.sparql_update( f"LOAD SILENT <{url}> INTO GRAPH <{context}>", echo = echo )
        elif re.search( r"\.(gz|bz2|xz)$", url  ):
            filename = tmpdir + "/" + url.split('/')[-1]
            if echo:
                report( 'write file', filename )
            download_file( url, filename )
            self.load_from_file( filename, context, echo = echo )
        else:
            stop_error( "Cannot handle this type of link with Fuseki: " + url )
