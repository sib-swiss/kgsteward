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

    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True, timeout = None ):
        if echo :
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept' : 'application/json', 
            'Content-Type': 'application/x-www-form-urlencoded' 
        }
        params = { 'query' : sparql }
        if timeout is not None :
            params["timeout"] = timeout
            status_code_ok.append( 503 )
            status_code_ok.append( 500 ) # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause 
                                         # FIXME: verify if rdf4j behave the same
        r = http_call(
            {
                'method'  : 'POST',  # allows for big query string
                'url'     : self.endpoint_query,
                'headers' : { **self.headers, **headers },
                'params'  : params,
            },
            status_code_ok
        )
        if timeout is not None:
            if r.status_code == 503 :
                time.sleep( 1 )
                print_warn( "query timed out" )
                return None
            elif r.status_code == 500 : 
                time.sleep( 1 )
                print_warn( "unknown error, maybe timeout" )
                return None
        return r

    def sparql_update( self, sparql,status_code_ok = [ 204 ], echo = True ):
        if echo :
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'headers' : self.headers,
                'params'  : { 'update': sparql },
            }, 
            status_code_ok,
            echo
        )

    def load_from_file( 
        self,
        file,
        context, 
        headers = {},
        echo = True 
    ):
        super().load_from_file( file, context, { **self.headers, **headers }, echo )
    
    def list_context( self, echo = True ) :
        r = http_call({
            'method'  : 'GET',
            'url'     : self.server_url + "/repositories/" + self.repository + "/contexts",
            'headers' : { **self.headers, 'Accept': 'application/json' },
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["contextID"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        self.sparql_update( f"DROP GRAPH <{context}>", echo = echo )

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


