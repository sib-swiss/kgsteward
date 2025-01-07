from dumper import dump
import re
from .common import *
from .generic import GenericClient

# FIXME: implement curl -XPOST http://localhost:3030/$/compact/TEST?deleteOld=true
# FIXME: test env variable JVM_ARGS
class FusekiClient( GenericClient ):

    def __init__( self, fuseki_url, username, password, repository_id ):
        self.fuseki_url = fuseki_url
        self.repository_id = repository_id
        super().__init__(  
            fuseki_url + "/" + repository_id + "/query", 
            fuseki_url + "/" + repository_id + "/update",
            fuseki_url + "/" + repository_id + "/store"
        )
        print_task( "contacting server" )
        try:
            r = http_call({
                'method'  : 'GET',
                'url'     : self.fuseki_url + "/$/ping"
            },[ 200 ] )
        except:
            stop_error( "Cannot contact fuseki at location: " + self.fuseki_url ) 
        if username is not None :
            try:
                r = http_call({
                    'method'  : 'GET',
                    'url'     : self.fuseki_url + "/$/server",
                    'auth'    : ( username, password )
                },[ 200 ] ) # returns 401 if authentification fail
                self.cookies = requests.utils.dict_from_cookiejar( r.cookies )
            except:
                stop_error( "Authentication to fuseki server failed: + self.graphdb_url" )

    def rewrite_repository( self, server_config_filename ) :
        self.sparql_update( "DROP ALL")

    def free_access( self ) :
        print_warn( "Not yet implemented: FusekiClient.free_access()" );

#    def sparql_query( self, sparql, accept='application/json', status_code_ok = [ 200 ], echo = True ) :
#        if echo :
#            print( sparql, flush=True )
#        r = http_call({
#            'method'  : 'GET',
#            'url'     : "http://localhost:3030/#/dataset/first_step/query",
#            'params'  : { 'query': sparql },
#        }, status_code_ok, echo )
#        return r
    
    def sparql_query( 
        self, 
        sparql, 
        headers = { 'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' }, 
        status_code_ok = [ 200 ], 
        echo = True 
    ):
        return super().sparql_query( sparql, { **self.headers, **headers }, status_code_ok, echo )

    def sparql_update( 
        self, 
        sparql, 
        headers = { 'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [ 200 ],  # on success fuseki return 200, not 204 !!!
        echo = True
    ):
        return super().sparql_update( sparql, { **self.headers, **headers }, status_code_ok, echo )

    def sparql_query_to_tsv(
        self, 
        sparql, 
        headers = { 'Accept': 'text/tab-separated-values', 'Content-Type': 'application/x-www-form-urlencoded' }, 
        status_code_ok = [ 200 ], 
        echo = True
    ):
        return super().sparql_query( sparql, { **self.headers, **headers }, status_code_ok, echo )
        
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
