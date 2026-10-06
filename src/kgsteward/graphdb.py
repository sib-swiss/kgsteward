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

AUTOCOMPLETE_NS = "http://www.ontotext.com/plugins/autocomplete#"

class GraphDBClient( GenericClient ):

    def __init__( self, graphdb_url, username, password, repository_id, echo = True ):
        # This constructor works even if the repo does not exist yet
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
            r = http_call(
                {
                    'method'  : 'POST',
                    'url'     : self.graphdb_url + "/rest/login/" + self.username,
                    'headers' : {
                        "X-GraphDB-Repository" : self.repository_id,
                        "X-GraphDB-Password"   : self.password
                    }
                },
                echo = echo 
            )
            if 'Authorization' in r.headers:
                self.headers = { 'Authorization': r.headers[ 'Authorization' ] }
            else:
                raise RuntimeError(
                    f"Authentication to GraphDB server failed: {self.graphdb_url}"
                )
    def list_repository( self ):
        r = http_call({
            'method' : 'get',
            'url'    : self.graphdb_url + '/rest/repositories',
            'headers' : self.headers
        })
        repos = []
        for rec in r.json(): repos.append( rec["id"] )
        return repos

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
        # http_call({
        #     'method'  : 'GET',
        #     'url'     : self.graphdb_url + "/rest/class-hierarchy?doReload=true&graphURI=",
        #     'headers' : { **self.headers, "X-GraphDB-Repository": self.repository_id },
        # })
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

    def compact_indexes( self ) :
        self.sparql_update( "INSERT DATA { [] <http://www.ontotext.com/compactIndexes> [] . }")
        
    # --------------------------------------------------------- #
    # Autocomplete (Lucene suggester) plugin.
    #
    # The plugin is driven by "magic" predicates: the triples below are
    # commands, nothing is stored. Properties verified against GraphDB
    # free 10.x/11.x, on which the code depends:
    #
    # * addLabelConfig/removeLabelConfig read their SUBJECT (the label
    #   predicate), the object being a language filter ("" = any).
    #   enabled/indexIRIs read only their OBJECT, the subject is ignored.
    # * reIndex fails with "Autocomplete is not enabled." while the plugin
    #   is off, hence it is switched on first. A repository left disabled
    #   with a huge index on disk is exactly what has to be cleaned here.
    # * reIndex must NOT share an INSERT DATA with the configuration it
    #   depends upon: issued together, the rebuild runs against the former
    #   configuration, with neither error nor warning.
    # * reIndex returns in seconds while the rebuild may run for hours,
    #   hence completion is polled on the status predicate.
    # * status is BUILDING, READY, NONE (plugin off) or CANCELED (sticky:
    #   an interrupted build never turns READY by itself). Waiting for
    #   READY alone would hang forever on the last two.
    # * the on/off state is NOT readable as "?s auto:enabled ?o", a pattern
    #   which silently returns rdf:type. REST is used instead.
    # --------------------------------------------------------- #

    def autocomplete_enabled( self, echo = True ):
        """Return True when the autocomplete plugin is switched on."""
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/rest/autocomplete/enabled",
            'headers' : { **self.headers, "X-GraphDB-Repository": self.repository_id },
        }, [ 200 ], echo )
        return r.text.strip().lower() == "true"

    def autocomplete_status( self, echo = True ):
        """Return the plugin status, or None when the server answers nothing,
        which it may do while a large build is running."""
        r = self.sparql_query(
            f"SELECT ?o WHERE {{ ?s <{AUTOCOMPLETE_NS}status> ?o }}",
            echo = echo
        )
        rows = r.json()["results"]["bindings"]
        return rows[0]["o"]["value"] if rows else None

    def _autocomplete_command( self, triple, echo = True ):
        self.sparql_update( "INSERT DATA { " + triple + " . }", echo = echo )

    def reset_autocomplete( self, timeout = 3600, echo = True ):
        """Empty the autocomplete index and reclaim the disk space it occupies.

        Nothing in the normal kgsteward lifecycle ever reclaims that index,
        which may grow to outweigh everything else in the data directory.
        Switching the plugin off does not help: it only flips a flag, the
        Lucene segments stay. Rebuilding an empty index does reclaim them.

        The whole operation goes over HTTP, so a GraphDB that is not reachable
        on the filesystem can be cleaned too. The on/off state of the plugin is
        preserved; the list of indexed label predicates cannot be, as emptying
        it is the very mechanism that releases the segments."""
        was_enabled = self.autocomplete_enabled( echo = echo )
        report( "plugin state", "enabled" if was_enabled else "disabled" )
        self._autocomplete_command( f'[] <{AUTOCOMPLETE_NS}enabled> true', echo = echo )
        # Stop a build in progress, which would otherwise delay everything
        # below by hours. The request itself may time out while waiting behind
        # a large build, hence the retries.
        for n in range( 3 ):
            try:
                self._autocomplete_command( f'[] <{AUTOCOMPLETE_NS}interruptIndexing> ""', echo = echo )
                break
            except Exception:
                print_warn( f"interrupt request failed ({ n + 1 }/3), a running build may be holding the server" )
                time.sleep( 30 )
        else:
            print_warn( "no build could be interrupted, carrying on nevertheless" )
        r = self.sparql_query(
            f"SELECT DISTINCT ?p WHERE {{ ?p <{AUTOCOMPLETE_NS}labelConfig> ?lang }}",
            echo = echo
        )
        for rec in r.json()["results"]["bindings"]:
            predicate = rec["p"]["value"]
            report( "unconfigure", predicate )
            self._autocomplete_command( f'<{predicate}> <{AUTOCOMPLETE_NS}removeLabelConfig> ""', echo = echo )
        self._autocomplete_command( f'[] <{AUTOCOMPLETE_NS}indexIRIs> false', echo = echo )
        # Sent on its own: batched with the configuration above, the rebuild
        # would silently run against the previous one.
        report( "rebuild", "empty index, asynchronously" )
        self._autocomplete_command( f'[] <{AUTOCOMPLETE_NS}reIndex> ""', echo = echo )
        start, previous = time.time(), None
        time.sleep( 5 ) # let the build start, lest the status still be the former READY
        while True:
            status = self.autocomplete_status( echo = False )
            if status != previous:
                report( "status", status if status else "(no answer from server)" )
                previous = status
            if status in ( "READY", "NONE", "CANCELED", "ERROR" ):
                break
            if time.time() - start > timeout:
                print_warn( f"autocomplete still '{ status }' after { timeout }s, no longer waiting" )
                break
            time.sleep( 10 )
        if not was_enabled:
            self._autocomplete_command( f'[] <{AUTOCOMPLETE_NS}enabled> false', echo = echo )
            report( "plugin state", "switched off again" )

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
            status_code_ok.append( 500 ) # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
        r = http_call(
            {
                'method'  : 'POST',  # allows for big query string
                'url'     : self.endpoint_query,
                'headers' : { **self.headers, **headers },
                'params'  : params,
            },
            status_code_ok,
            echo
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
    
    def sparql_update( self, sparql, status_code_ok = [ 204 ], echo = True ):
        if echo :
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        tok = self._sparql_update_started( sparql )   # log query BEFORE the POST
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'headers' : self.headers,
                'data'    : { 'update': sparql }, # POST body, per SPARQL 1.1 Protocol (not the URL query string)
            },
            status_code_ok,
            echo
        )
        self._sparql_update_finished( tok, getattr( r, "status_code", None ) )
        return r

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
       
    def list_context( self, echo = True ) :
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id + "/contexts",
            'headers' : { **self.headers, 'Accept': 'application/json' }
        }, [ 200 ], echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["contextID"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        self.sparql_update( f"DROP GRAPH <{context}>", echo = echo )

    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        request_args['url'] = self.graphdb_url + str( request_args['url'] )
        if 'headers' in request_args :
            request_args['headers'] ={ **self.headers, **request_args['headers'] }
        else :
            request_args['headers'] = self.headers
        return http_call( request_args, status_code_ok, echo )

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
            'headers' : { **self.headers, 'Accept': 'text/plain' },
            'data'    : long
        }, [204], echo )


