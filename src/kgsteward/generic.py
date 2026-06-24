# This is a very minimalistic/generic SPARQL client
# that might work on a real triplestore (maybe?)

import subprocess
import urllib

# How to dump a context from the command line:
# curl -G --data-urlencode "graph=http://example.org/context/ReconX_schema" http://localhost:7200/repositories/ReconXKG2/rdf-graphs/service

from dumper  import dump
from .common import *

class GenericClient():

    def __init__( self, endpoint_query, endpoint_update, endpoint_store ):
        self.endpoint_query  = endpoint_query
        self.endpoint_update = endpoint_update
        self.endpoint_store  = endpoint_store
        self.cookies         = None
        self.headers         = None

    def list_repository( self ):
        """ Return a list of existing repository """
        raise Exception( "Abstract method called: list_repository()" )

    def rewrite_repository( self, arg ):
        """ Create an empty repository or empty an existing one """
        raise Exception( "Abstract method called: rewrite_repository()" )
    
    def get_endpoint_query( self ):
        return self.endpoint_query

    def get_endpoint_update( self ):
        return self.endpoint_update
    
    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True, timeout = None ): 
        """ Run a sparql query and return the response with the data in JSON format. """
        raise Exception( "Abstract method called: sparql_query()" )
     
    def sparql_update( self, sparql, status_code_ok = [ 204 ], echo = True ):
        """ Run a sparql update, returns nothing """
        raise Exception( "Abstract method called: sparql_update()" )
    
    def list_context( self, echo = True ):
        """ Run the actual list of contexts """
        raise Exception( "Abstract method called: list_context()" )

    def drop_context( self, context ):
        """ Drop a context """
        raise Exception( "Abstract method called: drop_context()" )
    
    def dump_context( self, context, echo = True ):
        r = self.sparql_query( f"""
SELECT ?s ?p ?o 
WHERE{{ 
    GRAPH <{context}> {{ 
        ?s ?p ?o 
    }}
}}"""
)
        return sparql_result_to_table( r )

    def validate_sparql_query( self, sparql, echo = False, timeout = None ):
        """ verify that at least the query returns at least one row of data, or timeout """
        r = self.sparql_query( sparql, echo = False, timeout = timeout )
        if r is None:
            if timeout is not None:
                time.sleep( 1 ) # print_warn( "Query timed out" ) already printed
            else:
                 print( colored( sparql, "green" ))
                 stop_error( "Unknown error!" ) # 
        elif r.status_code == 200 :
            h, v = sparql_result_to_table( r )
            if len( v ) == 0 :
                print_warn( "empty result" )
            else :
                report( "#row", str( len( v )))
        else :
            print( colored( sparql, "green" ))
            stop_error( "Unexpected status code: " + str( r.status_code ))

    def load_from_file( self, file, context, headers = {}, echo = True ):
        """ use graph store protocol """
        if echo:
            report( 'load file', file )
        with any_open( file, 'rb' ) as f: # NB any_open takes care of decompression
            http_call(
                {
                    'method'  : 'POST',
                    'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
                    'headers' : {
                        **headers,
                        'Content-Type' : guess_mime_type( file )
                    },
                    'cookies' : self.cookies,
                    'data'    : f
                },
                [ 200, 201, 204 ], # fuseki 200, GraphDB 204
                echo
            )
 
    def _flush_buf( self, context, data, headers = {}, echo = True ):
        args = {
            'method'  : 'POST',
            'url'     : self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context ),
            'headers' : {
                **headers,
                'Content-Type' : 'text/plain', # FIXME: verify encoding as UTF-8
            },
            'data'    : data
        }
        if hasattr( self, "cookies" ):
            args['cookies'] = self.cookies
        http_call( args, [ 200, 201, 204 ], # fuseki 200, GraphDB 204
            echo
    )
        
    def load_from_file_using_riot( self, file, context, headers = {}, echo = True ):
        """ use graph store protocol and riot """
        if echo:
            report( 'load file', file )
        cmd = [ 'riot', file ]
        print( colored( " ".join( cmd ), "cyan" ))
        p = subprocess.Popen( cmd, stdout = subprocess.PIPE, text=True ) # riot returns nt format by default
        buf = []
        size = 0
        count = 0
        for line in p.stdout:
            count += 1
            l = len( line )
            if size + l > 1e8 : # aka 100 mega
                report( "triples so far", str( count ))
                self._flush_buf( context, "".join( buf ), headers )
                buf  = [ line ] # rewrite
                size = l        # rewrite
            else:
                buf.append( line )
                size += l
        if size > 0 :
            report( "triples so far", str( count ))
            self._flush_buf( context, "".join( buf ), headers )

    # ------------------------------------------------------------------ #
    # Polymorphic workflow hooks
    #
    # kgsteward.py drives every backend through the same workflow and calls
    # these hooks unconditionally.  The defaults here suit a live, mutable
    # HTTP triplestore (graphdb/fuseki/rdf4j); static-index backends such as
    # qlever override them.  Keeping the brand-specific behaviour on the
    # server object avoids `config["server"]["brand"] == ...` branches in the
    # main workflow.
    # ------------------------------------------------------------------ #

    @property
    def supports_sparql_load( self ):
        """True iff the backend can ingest data via SPARQL ``LOAD`` / graph store.

        False for static-index backends (qlever), which stage files into an
        offline index build instead.
        """
        return True

    def load_url( self, path, context, echo = True ):
        """Load a remote graph and record its ``void:dataDump`` provenance."""
        self.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = echo )
        self.sparql_update(
            "PREFIX void: <http://rdfs.org/ns/void#>\n"
            f"INSERT DATA {{ GRAPH <{context}> {{ <{context}> void:dataDump <{path}> }} }}",
            echo = echo,
        )

    def update_set_offline( self, names, config, name2context, sha_of ):
        """Determine the -C update set without querying the server, or None.

        Returns None for live backends: kgsteward then falls back to the
        online status query (``update_config``).  qlever overrides this to use
        on-disk checkpoints when its server is stopped.
        """
        return None

    def plan_index_scope( self, update_names, config, name2context, echo = True ):
        """Restrict an incremental index rebuild to a dependency closure.

        No-op for live backends (they apply each update directly); qlever uses
        it to scope the rebuilt index and validate required parents.
        """
        pass

    def warn_if_unindexed( self, name, context ):
        """Warn that a skipped dataset will be absent from the served data.

        No-op for live backends, where skipped datasets simply stay in place.
        """
        pass

    def queue_persist( self, context, sha256 = None ):
        """Queue a dataset to be persisted at the next ``flush_pending``.

        No-op for live backends: their SPARQL writes are already durable.
        qlever queues a checkpoint-dump + index rebuild.
        """
        pass

    def flush_pending( self, echo = True ):
        """Apply anything queued by ``queue_persist`` / staged loads.

        No-op for live backends; qlever rebuilds the index and dumps
        checkpoints for the staged datasets.
        """
        pass

    def finalize( self, complete, echo = True ):
        """End-of-session finalisation hook.

        No-op for live backends; qlever assembles the complete index (and the
        text index) when *complete* is set (``--qlever_complete``).
        """
        pass

    def ensure_running( self, echo = True ):
        """Ensure the server is serving queries at the end of the session.

        No-op for live backends (always up); qlever starts its server if an
        index exists but the server is stopped.
        """
        pass

    def can_restamp( self, context ):
        """True iff -U can re-stamp metadata for *context* without reloading.

        Always True for live backends (the data is in the repository); qlever
        requires a checkpoint, otherwise the metadata would be lost at the next
        rebuild.
        """
        return True

    def refine_status( self, config, echo = False ):
        """Report-only refinement of each dataset's ``status`` field.

        No-op for live backends: what the server serves IS the managed content,
        so the status derived from the server query (see ``update_config``) is
        already authoritative.

        Backends that stage content separately from what they serve override
        this.  qlever is the first such backend (its on-disk ``.nt.gz``
        checkpoints are the source of truth, and a checkpoint can be current yet
        absent from the complete production index until ``--qlever_complete``
        assembles it).  The same hook would let another brand surface a READY
        state should it grow checkpoint-dumping later.
        """
        pass
