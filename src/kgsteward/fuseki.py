from dumper import dump
import re
import rdflib
import urllib

from .common import *
from .generic import GenericClient

# FIXME: implement curl -XPOST http://localhost:3030/$/compact/TEST?deleteOld=true
# FIXME: test env variable JVM_ARGS

class FusekiClient( GenericClient ):

    def __init__( self, location, repository, config_file, username = None, password = None  ):
        g = rdflib.Graph()
        try:
            g.parse( config_file )
        except:
            stop_error( "Cannot parse file: " + config_file )
        query = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX fuseki: <http://jena.apache.org/fuseki#>
SELECT ?query ?update ?store
WHERE{
    [] rdf:type fuseki:Service ;
    fuseki:name '""" + repository + """' ;
    fuseki:endpoint [ 
        fuseki:operation fuseki:query ;
        fuseki:name ?query
    ] ;
    fuseki:endpoint [
        fuseki:operation fuseki:update ;
        fuseki:name ?update
    ] ;
    fuseki:endpoint [ 
        fuseki:operation fuseki:gsp-rw ; 
        fuseki:name ?store
    ]
}"""
        qres = g.query( query )
        for row in qres:
            dump( row )
            super().__init__(  
                location + "/" + repository + "/" + row.query, 
                location + "/" + repository + "/" + row.update,
                location + "/" + repository + "/" + row.store
            )
        self.repository = repository 
        self.location = location
        print_task( "contacting server" )
        try:
            r = http_call({
                'method'  : 'GET',
                'url'     : location + "/$/ping"
            },[ 200 ] )
        except:
            stop_error( "Cannot contact fuseki at location: " + location ) 
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
        print( self.endpoint_query )
        print( self.endpoint_update )
        print( self.endpoint_store )

    def rewrite_repository( self, server_config_filename ) :
        self.sparql_update( "DROP ALL")
# FIXME: this is n'importe quoi!
#        http_call({
#            'method'  : 'DELETE',
#            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
#            # 'headers' : { **self.headers, **headers }
#        }, [ 204, 404 ] ) # 204: deletion succeful, 404: graph did not exist

    def free_access( self ) :
        print_warn( "Not yet implemented: FusekiClient.free_access()" );

    def drop_context( self, context ): # FIXME: might be faster than DROP GRAPH <context>
        http_call({
            'method'  : 'DELETE',
            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
            # 'headers' : { **self.headers, **headers }
        }, [ 204, 404 ] ) # 204: deletion succeful, 404: graph did not exist

    def sparql_query( self, 
        sparql,
        headers = { 
            'Accept' : 'application/json', 
            'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [ 200 ],
        echo = True,
        timeout = None, 
    ):
        if echo :
            print( colored( sparql.replace( "\t", "    " ), "green" ), flush = True )
        if timeout is not None:
            headers["timeout"] = str( timeout )
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

    def sparql_update( 
        self, 
        sparql, 
        headers = { 'Content-Type': 'application/x-www-form-urlencoded' },
        status_code_ok = [ 200 ],  # on success fuseki return 200, not 204 !!!
        echo = True
    ):
        return super().sparql_update( sparql, { **self.headers, **headers }, status_code_ok, echo )
        
    def fuseki_compress_tdb2( self ):
        r = http_call({
            'method'  : 'POST',
            'url'     : self.location + "/$/compact/" + self.repository + "?deleteOld=true"
        }, [ 200 ] )

    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        print_warn( "Not yet implemented: FusekiClient.graphdb_call()" )

#    def validate_sparql_query( self, sparql, echo = False ):
#        print_warn( "Not yet implemented: FusekiClient.validate_sparql_query ()" )
#        r = http_call({
#            'method'  : 'GET',
#            'url'     : self.graphdb_url + "/repositories/" + self.repository_id,
#                'Accept'        : 'text/tab-separated-values',
#            'headers' : {
#                'Authorization' : self.authorization
#            },
#            'params'  : {
#                'query'   : sparql,
#                "timeout" : 5       # 5 seems to solve a HTTP "problem" observed with a timout of 1 s ?!?
#                "infer"   : True,
#            }
#        }, [ 503, 500, 400, 200 ], echo )
#        if r.status_code == 503 :
#            time.sleep( 1 )
#            print( "\t" + "query timed out" )
#        elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
#            print( "\t" + "unknown error, maybe timeout" )
#            time.sleep( 1 )
#        elif r.status_code == 400 :
#            raise RuntimeError( "Suspected SPARQL syntax error:\n" + sparql )
#        else : #  r.status_code == 200 :
#            n = r.text.count( "\n" )
#            if n == 0 :
#                print( "\t" + "!!! empty results !!!" )
#            else :
#                print( "\t" + str( n ) + " lines returned" )

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
