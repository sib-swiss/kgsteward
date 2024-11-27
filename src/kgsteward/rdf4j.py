# --------------------------------------------------------- #
# An RDF4J driver
# --------------------------------------------------------- #

from dumper import dump
from .common import *

from .generic import GenericClient

class RFD4JClient( GenericClient ):

    def __init__( self, server_url, username, password, repository_id ):
        super().__init__(  
            server_url + "/repositories/" + repository_id,
            server_url + "/repositories/" + repository_id + "/statements",
            server_url + "/repositories/" + repository_id + "/rdf-graphs/service"
        )
        self.server_url          = server_url
        self.username            = username
        self.password            = password
        self.repository_id       = repository_id
        self.headers             = {} # to be updated below
        print_break()
        print_task( "Contacting server" )
        try:
            http_call({
                'method' : 'GET',
                'url'    : self.server_url
            }, [ 200 ])
        except:
            stop_error( "Cannot contact server at url: " + self.server_url )

    def rewrite_repository( self, rdf4j_config_filename ):
        # "curl -H 'content-type: text/turtle' --upload-file common/data/config/JLW_Native_Lucene.config.ttl http://localhost:8080/rdf4j-server/repositories/JLW_Native_Lucene"
        http_call({
            'method' : 'DELETE',
            'url'    : self.server_url + '/repositories/' + self.repository_id,
#            'headers' : self.headers
        }, [ 204, 405 ] )
        http_call({
            'method'  : 'PUT',
            'url'     : self.server_url + '/repositories/' + self.repository_id,
            'headers' : { **self.headers, "content-type": "text/turtle" },
            'files'   : { 'config' : open( rdf4j_config_filename , 'rb' )}
        }, [ 204, 409 ] ) # 204: crated; 409 repository already exists (and don't care)
        # self.sparql_update( "DROP SILENT ALL" )

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
        status_code_ok = [ 204 ],
        echo = True
    ):
        return super().sparql_update( sparql, { **self.headers, **headers }, status_code_ok, echo )

    def load_from_file( 
        self,
        file,
        context, 
        headers = {},
        echo = True 
    ):
        super().load_from_file( file, context, { **self.headers, **headers }, echo )

    def sparql_query_to_tsv(
        self, 
        sparql, 
        headers = { 'Accept': 'text/tab-separated-values', 'Content-Type': 'application/x-www-form-urlencoded' }, 
        status_code_ok = [ 200 ], 
        echo = True
    ):
        return super().sparql_query( sparql, { **self.headers, **headers }, status_code_ok, echo )
    
    def get_contexts( self, echo = True ) :
        r = http_call({
            'method'  : 'GET',
            'url'     : self.server_url + "/repositories/" + self.repository_id + "/contexts",
            'headers' : { **self.headers, 'Accept': 'application/json' },
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["contextID"]["value"] )
        return contexts

    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        request_args['url'] = self.server_url + str( request_args['url'] )
        if 'headers' in request_args :
            request_args['headers']['Authorization' ] = self.authorization
        else :
            request_args['headers'] = { 'Authorization' : self.authorization }
        return http_call( request_args, status_code_ok, echo )

    def validate_sparql_query( self, sparql, echo = False ) :
        r = http_call({
            'method'  : 'POST',
            'url'     : self.server_url + "/repositories/" + self.repository_id,
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
            report( "status", "query timed out" )
        elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
            time.sleep( 1 )
            report( "status", "unknown error, maybe timeout" )
        elif r.status_code == 400 :
            raise RuntimeError( "Suspected SPARQL syntax error:\n" + sparql )
        else : #  r.status_code == 200 :
            n = r.text.count( "\n" )
            if n == 0 :
                report( "status" + "!!! empty results !!!" )
            else :
                report( "status", str( n ) + " lines returned" )

    def rewrite_prefixes( self, echo = True ):
        return
        r = http_call({
            'method'  : 'DELETE',
            'url'     : self.server_url + "/repositories/" + self.repository_id + "/namespaces",
            'headers' : self.headers,
        }, [204], echo )

    def set_prefix( self, short, long, echo = True ):
        return
        r = http_call({
            'method'  : 'PUT',
            'url'     : self.server_url + "/repositories/" + self.repository_id + "/namespaces/" + short,
            'headers' : self.headers.copy().update({ 'Accept', 'text/plain' }),
            'data'    : long
        }, [204], echo )


