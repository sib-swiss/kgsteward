# --------------------------------------------------------- #
# An RDF4J driver
# --------------------------------------------------------- #

from dumper import dump
from .common import *

from .generic import GenericClient

class RFD4JClient( GenericClient ):

    def __init__( self, server_url, username, password, repository ):
        super().__init__(  
            server_url + "/repositories/" + repository,
            server_url + "/repositories/" + repository + "/statements",
            server_url + "/repositories/" + repository + "/rdf-graphs/service"
        )
        self.server_url    = server_url
        self.username      = username
        self.password      = password
        self.repository    = repository
        self.headers       = {} # to be updated below
        print_break()
        print_task( "Contacting server" )
        try:
            http_call({
                'method' : 'GET',
                'url'    : self.server_url
            }, [ 200 ])
        except:
            stop_error( "Cannot contact server at location: " + self.server_url )
#        try:
#            http_call({
#                'url'    : self.endpoint_query
#                'method' : 'GET',
#        except:
#            }, [ 200 ])
#            stop_error( "Server is running, but repository does not exist: " + self.repository )

    def rewrite_repository( self, rdf4j_config_filename ):
        # FIXME: this does not work!
        try: # attempt to erase the repo and its content
            # curl -X DELETE http://localhost:8080/rdf4j-server/repositories/TEST
            http_call({ # slower alternative self.sparql_update( "DROP SILENT ALL" )
                'method' : 'DELETE',
                'url'    : self.server_url + '/repositories/' + self.repository,
                'headers' : self.headers
            }, [ 204, 404 ] ) # 204: cleared; 404 unknown
        except: # case repo does not exist yet 
            pass
        # "curl -H 'content-type: text/turtle' --upload-file common/data/config/JLW_Native_Lucene.config.ttl http://localhost:8080/rdf4j-server/repositories/JLW_Native_Lucene"
        http_call({
            'method'  : 'PUT',
            'url'     : self.server_url + '/repositories/' + self.repository,
            'headers' : { **self.headers, "content-type": "text/turtle" },
            'data'    : open( rdf4j_config_filename , 'rb' )
        }, [ 204, 409 ] ) # 204: created; 409 repository already exists (and don't care)

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
            'url'     : self.server_url + "/repositories/" + self.repository + "/contexts",
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
            'url'     : self.server_url + "/repositories/" + self.repository,
            'headers' : {
                'Accept'        : 'text/tab-separated-values'
                # 'Authorization' : self.authorization
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
            'url'     : self.server_url + "/repositories/" + self.repository + "/namespaces",
            'headers' : self.headers,
        }, [204], echo )

    def set_prefix( self, short, long, echo = True ):
        return
        r = http_call({
            'method'  : 'PUT',
            'url'     : self.server_url + "/repositories/" + self.repository + "/namespaces/" + short,
            'headers' : self.headers.copy().update({ 'Accept', 'text/plain' }),
            'data'    : long
        }, [204], echo )


