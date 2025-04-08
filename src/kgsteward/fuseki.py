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
        self.location   = location
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
                'method'  : 'POST',  # allows for big query string
                'url'     : self.endpoint_query,
                'headers' : headers,
                'params'  : params,
                'cookies' : self.cookies
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
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'headers' : { 'Content-Type': 'application/x-www-form-urlencoded' }, 
                'cookies' : self.cookies,
                'params'  : { 'update': sparql },
            }, 
            status_code_ok,
            echo
        )

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ): # FIXME: might be faster than DROP GRAPH <context>, echo is ignored
        http_call({
            'method'  : 'DELETE',
            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
            # 'headers' : { **self.headers, **headers }
            'cookies' : self.cookies,
        }, [ 204, 404 ] ) # 204: deletion succeful, 404: graph did not exist

#    def dump_context( self, context, status_code_ok = [ 200 ], echo = True ):
#        return http_call({
#            'method'  : 'GET',
#            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
#            'cookies' : self.cookies,
##            'headers' : { 'Accept': 'text/plain' },
#        }, status_code_ok, echo )

    def fuseki_compress_tdb2( self ):
        r = http_call({
            'method'  : 'POST',
            'url'     : self.location + "/$/compact/" + self.repository + "?deleteOld=true",
            'cookies' : self.cookies,
        }, [ 200 ] )

    def load_from_url( self, url, context, tmpdir = "/tmp", echo = True ): # FIXME: this code is never called
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
