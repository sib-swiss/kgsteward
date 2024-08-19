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

class GraphDBClient():

    def __init__( self, graphdb_url, username, password, repository_id ):
        self.graphdb_url          = graphdb_url
        self.username             = username
        self.password             = password
        self.repository_id        = repository_id
        self.authorization        = '' # to be set below
        print_break()
        print_task( "contacting server" ) 
        r = http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/rest/login/" + self.username,
            'headers' : {
                "X-GraphDB-Repository" : self.repository_id,
                "X-GraphDB-Password"   : self.password
            }
        })
        if 'Authorization' in r.headers:
            self.authorization = r.headers[ 'Authorization' ]
        else:
            raise RuntimeError(
                f"Authentication to GraphDB server failed: {self.graphdb_url}"
            )

    def rewrite_repository( self, graphdb_config_filename ) :
        http_call({
            'method' : 'DELETE',
            'url'    : self.graphdb_url + '/rest/repositories/' + self.repository_id,
            'headers' : { 'Authorization' : self.authorization }
        })
        http_call({
            'method'  : 'POST',
            'url'     :  self.graphdb_url + '/rest/repositories',
            'headers' : { 'Authorization' : self.authorization },
            'files'   : { 'config' : open( graphdb_config_filename , 'rb' )}
        }, [ 201 ] )
        http_call({
            'method'  : 'POST',
            'url'     :  self.graphdb_url + '/rest/autocomplete/enabled',
            'headers' : {
                "X-GraphDB-Repository" : self.repository_id,
                'Authorization'        : self.authorization
            },
            'params'  : { 'enabled' : 'true' }
        })
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/rest/security",
            'headers' : {
                "X-GraphDB-Repository": self.repository_id,
                "Authorization":        self.authorization,
            },
            'json'    : "true"
        })

    def free_access( self ) :
        http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/rest/class-hierarchy?doReload=true&graphURI=",
            'headers' : {
                "X-GraphDB-Repository" : self.repository_id,
                "Authorization"        : self.authorization,
             },
        })
        http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/rest/security/free-access",
            'headers' : { "Authorization" : self.authorization },
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

    def sparql_query( self, sparql, accept='application/json', status_code_ok = [ 200 ], echo = True ) :
        if echo :
            print_strip( sparql, "green" )
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id,
            'headers' : {
                'Accept'        : accept,
                'Authorization' : self.authorization
            },
            'params'  : { 'query': sparql }
        }, status_code_ok, echo )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 204 ], echo = True ) :
        if echo :
            print_strip( sparql, "green")
        r = http_call({
            'method'  : 'POST',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/statements",
            'headers' : {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization' : self.authorization
            },
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
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/contexts",
            'headers' : {
                'Accept'        : 'application/json',
                'Authorization' : self.authorization
            }
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( "<" + rec["contextID"]["value"] + ">" )
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
            'headers' : {
                'Authorization' : self.authorization
            }
        }, [204], echo )

    def set_prefix( self, short, long, echo = True ):
        r = http_call({
            'method'  : 'PUT',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/namespaces/" + short,
            'headers' : {
                'Accept'        : "text/plain",
                'Authorization' : self.authorization
            },
            'data'    : long
        }, [204], echo )


