# --------------------------------------------------------- #
# Some REST services were not documented in the help pages
# of GraphDB. The syntax of these services can be deduced
# from the JS code of the graphdb-workbench at GitHub
#
#    https://github.com/Ontotext-AD/graphdb-workbench
#
# in directory /src/js/angular/rest, or better in
#
# https://rdf4j.org/documentation/reference/rest-api/
#
# If one mess up with user/password, GraphDB may end up in
# a state where connection become impossible. The only
# way out is to erase the graphdb.home directory
# (Mac in ~/Library/Application\ Support/GraphDB)
# and restart GraphDB. All data will be lost!
#
# Given the frequent updates of GraphDB, some of the 
# above comments might already be deprecated.
# --------------------------------------------------------- #

import time

from dumper import dump
from .common import *
import urllib.parse

from .generic import GenericClient

class GraphDBClient( GenericClient ):

    def __init__( self, graphdb_url, username, password, repository_id ):
        super().__init__(  
            graphdb_url + "/repositories/" + repository_id, 
            graphdb_url + "/repositories/" + repository_id + "/statements",
            graphdb_url + "/repositories/" + repository_id + "/rdf-graphs/service"
        )
        self.graphdb_url          = graphdb_url
        self.username             = username
        self.password             = password
        self.repository_id        = repository_id
        self.headers              = {} # to be updated below
        print_break()
        print_task( "contacting server" )
        if self.username is not None :
            r = http_call({
                'method'  : 'POST',
                'url'     : self.graphdb_url + "/rest/login/" + self.username,
                'headers' : {
                    "X-GraphDB-Repository" : self.repository_id,
                    "X-GraphDB-Password"   : self.password
                }
            })
            if 'Authorization' in r.headers:
                self.headers = { 'Authorization': r.headers[ 'Authorization' ] }
            else:
                raise RuntimeError(
                    f"Authentication to GraphDB server failed: {self.graphdb_url}"
                )

    def rewrite_repository( self, graphdb_config_filename ) :
        http_call({
            'method' : 'DELETE',
            'url'    : self.graphdb_url + '/rest/repositories/' + self.repository_id,
            'headers' : self.headers
        })
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + '/rest/repositories',
            'headers' : self.headers,
            'files'   : { 'config' : open( graphdb_config_filename , 'rb' )}
        }, [ 201 ] )
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + '/rest/autocomplete/enabled',
            'headers' : { **self.headers, "X-GraphDB-Repository": self.repository_id },
            'params'  : { 'enabled' : 'true' }
        })
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/rest/security",
            'headers' : { **self.headers, "X-GraphDB-Repository": self.repository_id },
            'json'    : "true"
        })

    def free_access( self ) :
        http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/rest/class-hierarchy?doReload=true&graphURI=",
            'headers' : { **self.headers, "X-GraphDB-Repository": self.repository_id },
        })
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/rest/security/free-access",
            'headers' : self.headers,
            "json"    : {
                "enabled" : "true",
                "authorities" : [ "READ_REPO_" + self.repository_id ],
                "appSettings" : {
                    "DEFAULT_INFERENCE"        : "true",
                    "DEFAULT_VIS_GRAPH_SCHEMA" : "true",
                    "DEFAULT_SAMEAS"           : "true",
                    "IGNORE_SHARED_QUERIES"    : "false",
                    "EXECUTE_COUNT"            : "true"
                }
            }
        })

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

    def load_from_file_using_riot( self, file, context, echo = True ):
        super().load_from_file_using_riot( file, context, headers = { **self.headers }, echo = echo )

    def sparql_query_to_tsv(
        self, 
        sparql, 
        headers = { 'Accept': 'text/tab-separated-values', 'Content-Type': 'application/x-www-form-urlencoded' }, 
        status_code_ok = [ 200 ], 
        echo = True
    ):
        return super().sparql_query( sparql, { **self.headers, **headers }, status_code_ok, echo )
    
    def dump_context(
        self,
        context,
        headers = { 'Accept': 'text/plain' }, 
        status_code_ok = [ 200 ], 
        echo = True
    ):
        return super().dump_context( context, { **self.headers, **headers }, status_code_ok, echo )
     
    def get_contexts( self, echo = True ) :
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/contexts",
            'headers' : { **self.headers, 'Accept': 'application/json' },
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["contextID"]["value"] )
        return contexts

    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        request_args['url'] = self.graphdb_url + str( request_args['url'] )
        if 'headers' in request_args :
            request_args['headers']['Authorization' ] = self.authorization
        else :
            request_args['headers'] = { 'Authorization' : self.authorization }
        return http_call( request_args, status_code_ok, echo )

    def validate_sparql_query( self, sparql, echo = False ) :
        r = http_call({
            'method'  : 'POST',
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
        r = http_call({
            'method'  : 'DELETE',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/namespaces",
            'headers' : self.headers,
        }, [204], echo )

    def set_prefix( self, short, long, echo = True ):
        r = http_call({
            'method'  : 'PUT',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/namespaces/" + short,
            'headers' : self.headers.copy().update({ 'Accept', 'text/plain' }),
            'data'    : long
        }, [204], echo )


