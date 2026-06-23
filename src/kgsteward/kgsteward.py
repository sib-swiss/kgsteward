"""Main kgsteward module."""

import argparse
import os
import sys
import re
import hashlib
import requests  # https://docs.python-requests.org/en/master/user/quickstart/
import subprocess
import urllib

from   dumper    import dump # get ready to help debugging
from   termcolor import colored

from .common     import *
from .special    import *
from .yamlconfig import parse_yaml_conf
from .graphdb    import GraphDBClient
from .fuseki     import FusekiClient
from .rdf4j      import RFD4JClient
from .qlever     import QleverClient
# from .oxigraph   import OxigraphClient  # in preparation
# 
from importlib.metadata import version
__version__ = version("kgsteward")

# from .virtuoso   import VirtuosoClient  # in preparation
from .fileserver import LocalFileServer



name2context = {} # global helper dict
context2name = {} # same

# ---------------------------------------------------------#
# Command-line options
# ---------------------------------------------------------- #

def get_user_input():
    """Generate argparse CLI and return user input."""

    parser = argparse.ArgumentParser(
        description = "A command line tool to manage the content of a RDF store, as specified in a YAML configuration file. "
                      "Documentations, including supported YAML syntax and the source are available from https://github.com/sib-swiss/kgsteward."
    )
    parser.add_argument(
        'yamlfile',
        nargs = 1,
        help  = "Mandatory configuration file in YAML format. "
                "Supported syntax: https://github.com/sib-swiss/kgsteward/blob/main/doc/yaml/kgsteward.schema.md"
    )
    parser.add_argument(
        '-F',
        action = 'store_true',
        help   = "Force rebuild the core of the RDF database. "
                 "Sames as -I -D combined options."
    )
    parser.add_argument(
        '-I',
        action = 'store_true',
        help   = "Create the repository or force rewrite the repository, i.e. erase all existing RDF data."
    )
    parser.add_argument(
        '-D',
        action = 'store_true',
        help   = 'Force reload all RDF data'
    )
    parser.add_argument(
        '-d',
        help = "Force reload RDF data from the supplied comma-separated list "
               "of graph name (no space in the list). It might be combined "
               "with option -C.",
    )
    parser.add_argument(
        '-C',
        action = 'store_true',
        help   = "Load missing/incomplete/outdated dataset to complete the repository."
    )
    parser.add_argument(
        '-U',
        action = 'store_true',
        help   = 'Force update internal checksum without updating the data. '
    )
    parser.add_argument(
        '-V',
        action = 'store_true',
        help   = "Validate the repository content and the SPARQL queries, by running all queries." 
                 "Test the query results, if tests are defined in the YAML config. "
                 "It might be executed with timeout using option -t."
    )
    parser.add_argument(
        '-Q',
        action = 'store_true',
        help   = "Run all SPARQL queries. It might be combined with --timeout."
    )
    parser.add_argument(
        '--dump_dir',
        metavar = 'DIR',
        help   = "Output directory for dumps. Required whenever any --dump_* flag is given; "
                 "must already exist. Each unit is written as DIR/<name>.tsv."
    )
    parser.add_argument(
        '--dump_all_dataset',
        action = 'store_true',
        help   = "Dump the contents of ALL datasets, one sorted TSV per dataset, into --dump_dir. "
                 "Sorting is enforced irrespective of triple order so dumps from different servers "
                 "can be compared with diff. Useful for debugging, not meant to retrieve data; "
                 "possibly slow and memory hungry. Mutually exclusive with --dump_dataset."
    )
    parser.add_argument(
        '--dump_dataset',
        metavar = 'NAMES',
        help   = "As --dump_all_dataset, but limited to a comma-separated list of dataset names "
                 "(e.g. --dump_dataset SLR_test,RHEA_MNet). Unknown names are an error. "
                 "Mutually exclusive with --dump_all_dataset."
    )
    parser.add_argument(
        '--dump_all_select',
        action = 'store_true',
        help   = "Run ALL configured SPARQL SELECT queries and dump each result as a sorted TSV "
                 "into --dump_dir. Same sorting/comparison semantics as --dump_all_dataset. "
                 "Mutually exclusive with --dump_select."
    )
    parser.add_argument(
        '--dump_select',
        metavar = 'NAMES',
        help   = "As --dump_all_select, but limited to a comma-separated list of query names "
                 "(the query-file basenames, e.g. --dump_select all_triples_stable). "
                 "Unknown names are an error. Mutually exclusive with --dump_all_select."
    )
    parser.add_argument(
        '-v',
        action = 'store_true',
        help    = "Verbose mode: print out SPARQL queries being executed. "
                  "Super useful for debugging SPARQL update (after string replacement)."
    )
    parser.add_argument(
        '--version',
        action = 'version',
        version = f'%(prog)s {__version__}'
    )
    parser.add_argument(
        '-t', '--timeout',
        type = int,
        help   = "Timeout delay in seconds. There is no timeout by default. " 
    )
    parser.add_argument(
        '--force_unfreeze',
        action = 'store_true',
        help = "Ignore all frozen states."
    )
    parser.add_argument(
        '--fuseki_compress_tbd2',
        action = 'store_true',
        help = "Compress fuseki TDB2 indexes, otherwise do nothing. This is executed at first. "
               "Beware of the advantage and disadvantage of TDB vs TDB2 indexes in fuseki."
    )
    parser.add_argument(
        '--graphdb_upload_queries',
        action = 'store_true',
        help = "Rewrite and upload queries in the GraphDB menu. "
               "The queries are global to a GraphDB instance, i.e. they are not attached to a specific repository. "
    )
    parser.add_argument(
        '--graphdb_upload_prefixes', '--rdf4j_upload_prefixes',
        action = 'store_true',
        help = "Rewrite and reload all prefix definitions. "
               "The prefixes are global to a GraphDB/RDF4J instance, i.e. they are not attached to a specific repository. "
    )
    parser.add_argument(
        '--graphdb_free_access',
        action = 'store_true',
        help = "Allow read-only, public free-access to a repository in GraphDB. "
    )
    parser.add_argument(
        '--graphdb_compact_indexes',
        action = 'store_true',
        help = "Compact GraphDB indexes after data upload/insert/delete. It may take a while, but improves query performance. "
    )
    parser.add_argument(
        '--qlever_upload_quad_and_dump_checkpoints',
        action = 'store_true',
        help = "(qlever only) One-shot bootstrap: (i) wipe the qleverdir and restore the "
               "user's Qleverfile, (ii) build the index with `qlever index` from the "
               "configured INPUT_FILES (typically a big .nq.gz dump), (iii) start the "
               "server, (iv) verify that the named graphs in the loaded index match the "
               "YAML datasets, (v) dump every named graph as an .nt.gz + sidecar checkpoint.  "
               "After this, kgsteward's per-dataset checkpoint architecture is fully "
               "bootstrapped from the bulk dump and normal -C/-d operations work as usual."
    )
    parser.add_argument(
        '--qlever_complete',
        action = 'store_true',
        help = "(qlever only) At the end of the session, assemble the COMPLETE index from "
               "all on-disk checkpoints and build the text index if TEXT_INDEX is set in the "
               "Qleverfile.  Incremental runs (-C/-d) only rebuild the dependency closure of "
               "the datasets they touch, so the served index may be partial; --qlever_complete "
               "is the only run that guarantees a complete, queryable, text-indexed server. "
               "Without it the text index is absent (the main triple index works fine for "
               "everything except `?x ql:contains-word ...` queries)."
    )
    parser.add_argument(
        '--sparql_update_stats',
        metavar = 'FILE',
        help   = "Dump per-update timings to a TSV at session end (one row per "
                 "sparql_update call, with wall-clock and server-side timings, "
                 "size, sha1, error if any).  Useful for diagnosing slow updates "
                 "and for benchmark comparison between backends (run with each "
                 "backend, then join on sha1_8 to compare per-update timings)."
    )
    parser.add_argument(
        '--sib_swiss_editor',
        help = "Document and save all queries and prefix declarations in a single Turtle file, ready to be retrived by the sib-swiss editor (https://github.com/sib-swiss/sparql-editor). "
               "Note that the <SIB_SWISS_EDITOR> file is not uploaded directly to the store. "
    )
    parser.add_argument(
        '--dependency_graph',
        help = "Write an interactive dependency graph of datasets (and their 'parent' relationships) to an HTML file. "
               "The argument is the output filename (e.g. 'graph.html'). "
               "Uses Vis.js Network (loaded from CDN) — open the result in any browser. "
               "Triple counts are retrieved from the live triplestore and shown on each node."
    )
    args = parser.parse_args()

    # Further processing of command line arguments
    if args.F :
        args.I = True
        args.D = True

    return args

def get_target( config, name ):
    """ An inefficient helper function """
    for rec in config["dataset"] :
        if rec["name"] == name :
            return rec
    raise RuntimeError( "Target name not found: " + name )

def get_sha256( config, name, echo = True ) :
    """ Compute checksums of dataset record"""
    target = get_target( config, name )
    context = name2context[ name ]
    os.environ["TARGET_GRAPH_CONTEXT"] = context
    os.environ["kgsteward_dataset_name"]    = name
    os.environ["kgsteward_dataset_context"] = context
    sha256 = hashlib.sha256()
    #   sha256.update( target["count"].encode( 'utf-8' ))
    #   sha256.update( target["date"].encode( 'utf-8' ))
    #   sha256.update( target["sha256"].encode( 'utf-8' ))
    if "context" in target:
        sha256.update( target["context"].encode( 'utf-8' ))
    if "parent" in target:
        for parent_name in target["parent"]:
            sha256.update( parent_name.encode( 'utf-8' )) # parent sha256 might be out of sync, it is simpler not to check it
    # skip frozen status, as it is not a property of the dataset content generation
    if "system" in target :
        for cmd in target["system"] :
            sha256.update( cmd.encode( 'utf-8' ))
    if "file" in target :
        for path in target["file"] :
            for dir, filename in expand_path( path, config["kgsteward_yaml_directory"], fatal = False ):
                with open( replace_env_var( dir + "/" + filename ), "rb") as f :
                    for chunk in iter( lambda: f.read(4096), b"") :
                        sha256.update( chunk )
    if "url" in target :
        for url in target["url"] :
            path = replace_env_var( url )
            sha256.update( path.encode('utf-8') )
            if re.search( r"https?:", path ) :
               info = get_head_info( path, echo = echo ) # as a side effect: verify is the server is responding
               sha256.update( info.encode('utf-8'))
            elif re.search( r"ftp:", path ):# do not run HEAD on ftp server FIXME: implement something better
                continue
            else:
                stop_error( "It does not look like an URL: " + path )
    if "stamp" in target :
        for link in target["stamp"] :
            path = replace_env_var( link )
            sha256.update( path.encode('utf-8') )
            if( path.startswith( "http" )):
                info = get_head_info( path, echo = echo  ) # as a side effect: verify is the server is responding
                sha256.update( info.encode('utf-8') )
            else:  # assume local file
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"], fatal = False ):
                    filename = dir + "/" + fn
                    with open( replace_env_var( filename ), "rb") as f :
                        for chunk in iter( lambda: f.read(4096), b"") :
                            sha256.update( chunk )
    if "replace" in target:
        for key in sorted( target["replace"].keys()):
            sha256.update( key.encode( 'utf-8' ))
            sha256.update( target["replace"][key].encode( 'utf-8' ))
    if "update" in target :
        for path in target["update"] :
            for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                filename = dir + "/" + fn
                with open( filename ) as f:
                    sparql = f.read()
                sha256.update( sparql.encode('utf-8'))
    if "zenodo" in target : # FIXME: remove this!
        for id in target["zenodo"]:
            r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
            if not r.status_code == 200 :
                raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
            info = r.json()
            for record in info["files"] :
                sha256.update( record["checksum"].encode('utf-8'))
    if  "special" in target:
        for key in target["special"]:
            sha256.update( key.encode( 'utf-8' ))
    return sha256.hexdigest()

def update_config( server, config, name_to_update = set(), echo = True ) :
    """ Compute, or update current status information about the records in repository.
        Take dependency into account."""
    print_break()
    print_task( "Retrieve current status" )
    name2item = {}
    for item in config["dataset"]:
        name = item["name"]
        name2item[name]    = item
    r = server.sparql_query( """
PREFIX void:      <http://rdfs.org/ns/void#>
PREFIX dct:       <http://purl.org/dc/terms/>
PREFIX ex:        <http://example.org/>
PREFIX kgsteward: <https://purl.expasy.org/kgsteward/>

SELECT ?context ?x ( REPLACE( STR( ?y ), "\\\\..+", "" ) AS ?t ) ?sha256
WHERE{
    {
        ?context_1 a kgsteward:Dataset   ;
            kgsteward:triples  ?x_1     ;
            kgsteward:modified ?y_1      ;
            kgsteward:checksum ?sha256_1 .
        
    } UNION {
        ?context_2 a void:Dataset   ;
            void:triples                    ?x_2      ;
            dct:modified                    ?y_2      ;
            <http://example.org/has_sha256> ?sha256_2 .
    }
    BIND( COALESCE( ?context_1, ?context_2 ) AS ?context )
    BIND( COALESCE( ?x_1, ?x_2 ) AS ?x )
    BIND( COALESCE( ?y_1, ?y_2 ) AS ?y )
    BIND( COALESCE( ?sha256_1, ?sha256_2 ) AS ?sha256 )
}
""", echo = echo )
    if r is not None:
        try: 
            for rec in r.json()["results"]["bindings"] :
                if rec["context"]["value"] in context2name:
                    name = context2name[rec["context"]["value"]]
                    item = name2item[ name ]
                else:
                    continue
                item["count"]  = rec["x"]["value"]
                item["date"]   = rec["t"]["value"]
                item["sha256"] = str( rec["sha256"]["value"] )
        except Exception as e: # test before and remove this try/except block
            stop_error( "Failed parsing server response: " + str( e ))
    for item in config["dataset"]: # ordering respect dependency 
        sha256 = get_sha256( config, item["name"], echo = echo )
        # default status is "EMPTY" if the context is not found in the repository, 
        # otherwise "ok" if the checksum is the same, 
        # or "UPDATE" if the checksum is different,
        # or "FROZEN" if the record is frozen, 
        # or "PROPAGATE" if it is not frozen but has a parent record to update.
        # or "UNKNOWN" if is is not managed by kgsteward 
        if item["name"] in name_to_update:
            item["status"] = "UPDATE"
        elif item["sha256"] == sha256:
            item["status"] = "ok" # may be still changed below if it is a parent of an UPDATE record, but it is simpler to set it as "ok" first
        elif item["frozen"]:
            item["status"] = "FROZEN"        
        else:
            item["status"] = "UPDATE"
        if "parent" in item and not item["status"] == "FROZEN":
            for parent_name in item["parent"] :
                if name2item[parent_name]["status"] in { "EMPTY", "UPDATE", "PROPAGATE" }: # ignore FROZEN
                    item["status"] = "PROPAGATE"
    return config

def update_dataset_info( server, config, name, echo = True ) :
    """Re-stamp the kgsteward:Dataset metadata for *name*.

    Issued as a single DELETE-then-INSERT update so that calling this twice
    against the same context replaces the metadata cleanly instead of
    accumulating duplicate sets (the previous INSERT-only form left pept_cluster
    with 8 metadata triples = 2 stacked sets after two -C runs).
    """
    context = name2context[ name ]
    sha256 = get_sha256( config, name, echo = echo )
    server.sparql_update( f"""
PREFIX kgsteward: <https://purl.expasy.org/kgsteward/>

DELETE {{
    GRAPH <{context}> {{
        <{context}> a kgsteward:Dataset ;
            kgsteward:triples  ?old_c   ;
            kgsteward:modified ?old_t   ;
            kgsteward:checksum ?old_sha .
    }}
}}
INSERT {{
    GRAPH <{context}> {{
        <{context}> a kgsteward:Dataset ;
            kgsteward:triples   ?c   ;
            kgsteward:modified  ?now ;
            kgsteward:checksum  "{sha256}" .
    }}
}}
WHERE {{
    OPTIONAL {{
        GRAPH <{context}> {{
            <{context}> a kgsteward:Dataset ;
                kgsteward:triples  ?old_c   ;
                kgsteward:modified ?old_t   ;
                kgsteward:checksum ?old_sha .
        }}
    }}
    {{
        SELECT
            ( COUNT( * ) AS ?c )
            ( NOW() AS ?now )
        WHERE {{
            GRAPH <{context}> {{ ?s ?p ?o }}
        }}
    }}
}}
""", echo = echo )
    item = get_target( config, name )
    item["status"] = "ok"

def main():
    """Main function of the kgsteward workflow."""

    # --------------------------------------------------------- #
    # Read command line options
    # --------------------------------------------------------- #

    args = get_user_input()

    # --------------------------------------------------------- #
    # Load YAML config and complete it
    # --------------------------------------------------------- #

    print_break()
    print_task( "read YAML config" )
    if not args.yamlfile[0]:
        stop_error( "No YAML file provided! Use -h for help." )
    config = parse_yaml_conf( replace_env_var( args.yamlfile[0] ))
    for item in config["dataset"]:
        name2context[ item["name"] ] = item["context"]
        context2name[ item["context"] ] = item["name"]

    # --------------------------------------------------------- #
    # Initalise connection with the right triplestore
    # --------------------------------------------------------- #

    if "username" in config["server"]:
        username = replace_env_var( config["server"]["username"] )
        password = replace_env_var( config["server"]["password"] )
    else:
        username = None
        password = None

    if config["server"]["brand"] == "graphdb":
        try:
            server = GraphDBClient(
                replace_env_var( config["server"]["location"] ),
                username,
                password,
                replace_env_var( config["server"]["repository"] ),
                echo = args.v
            )
        except Exception as e:
            print_warn( "Failed to connect to GraphDB server, or the repository does not exist yet (use -I to create it)!" ) 
            stop_error( str( e ))

    elif config["server"]["brand"] == "rdf4j":
        try:
            server = RFD4JClient(
                replace_env_var( config["server"]["location"] ),
                username,
                password,
                replace_env_var( config["server"]["repository"] ),
                echo = args.v
            )
        except Exception as e:
            stop_error( "Failed to connect to RDF4J server: " + str( e ))
    elif config["server"]["brand"] == "fuseki":
        try:
            server = FusekiClient(
                replace_env_var( config["server"]["location"] ),
                replace_env_var( config["server"]["repository"] ),
                # Resolve server_config relative to the YAML directory so
                # rdflib.Graph().parse() in FusekiClient doesn't try to
                # open a bare filename against the process CWD.
                update_path( config["server"]["server_config"], config["kgsteward_yaml_directory"] ),
                username = username,
                password = password,
                echo = args.v,
            )
        except Exception as e:
            stop_error( "Failed to connect to Fuseki server: " + str( e ))
    elif config["server"]["brand"] == "qlever":
        try:
            server = QleverClient(
                replace_env_var( config["server"]["qleverfile"] ),
                replace_env_var( config["server"]["qleverdir"] ),
                access_token = replace_env_var( config["server"]["access_token"] ) if config["server"].get( "access_token" ) else None,
                echo = args.v
            )
        except Exception as e:
            stop_error( "Failed to connect to Qlever server: " + str( e ))
    else:
        stop_error( "Unknown server brand: " + config["server"]["brand"] )

    for key in config["server"].keys():
        os.environ[ "kgsteward_server_" + str( key )] = str( config["server"][key] )
    os.environ[ "kgsteward_server_endpoint_query"]  = server.get_endpoint_query()
    os.environ[ "kgsteward_server_endpoint_update"] = server.get_endpoint_update()

    # --------------------------------------------------------- #
    # Create a new empty repository or rewrite an existing one
    # --------------------------------------------------------- #

    if "repository" in config["server"]:
        repo = replace_env_var( config["server"]["repository"] )
    else:
        repo = server.repository   # qlever: derived from Qleverfile NAME
    if not repo in server.list_repository():
        if not args.I:
            stop_error( "The repository does not exist, use -I to create it: " + repo )

    if args.I :
        if "server_config" in config["server"]:
            config_file = update_path( config["server"]["server_config"], config["kgsteward_yaml_directory"] )
            server.rewrite_repository( config_file )
        else:
             server.rewrite_repository()

    if args.fuseki_compress_tbd2: # FIXME: check that index type is really TDB2 (and not TDB)
        if config["server"]["brand"] == "fuseki":
            print_break()
            print_task( "Launch TDB2 compression in the. It may delay execution of next statements" )
            server.fuseki_compress_tdb2()
        else:
            print_warn( "Option --fuseki_compress_tbd2 not supported for server brand: " + config["server"]["brand"] )

    # --------------------------------------------------------- #
    # qlever-only: bootstrap from a bulk quad dump.
    # (i)   reset to the user's Qleverfile;
    # (ii)  qlever index --overwrite-existing  from INPUT_FILES;
    # (iii) qlever start;
    # (iv)  verify named graphs in loaded index vs YAML datasets;
    # (v)   dump every named graph as a .nt.gz + sidecar checkpoint.
    #
    # Placed AFTER -I (it does the equivalent reset anyway, so an
    # explicit -I is redundant but harmless), and BEFORE the
    # update-set determination so the freshly-created checkpoints
    # inform has_checkpoint() in -C stopped-server fallback mode.
    # --------------------------------------------------------- #

    if args.qlever_upload_quad_and_dump_checkpoints:
        if config["server"]["brand"] != "qlever":
            stop_error( "--qlever_upload_quad_and_dump_checkpoints is only valid for the qlever backend" )
        print_break()
        print_task( "Bootstrap qlever from quad dump and capture checkpoints" )
        dumped = server.upload_quad_and_dump_checkpoints( name2context, echo = args.v )
        report( "checkpoints created", len( dumped ) )

    if args.qlever_complete and config["server"]["brand"] != "qlever":
        stop_error( "--qlever_complete is only valid for the qlever backend" )
    # (No early action needed — --qlever_complete only triggers the one-shot
    # complete_index() call at the session end.)

    # --------------------------------------------------------- #
    # Establish the list of contexts to update
    # --------------------------------------------------------- #

    # Per-run memo for dataset checksums.  get_sha256 reads file contents and
    # issues HTTP HEADs, so it must not be recomputed once per call site;
    # compute each dataset's checksum at most once per run and reuse it.  This
    # does NOT change get_sha256 itself.
    _sha256_cache = {}
    def dataset_sha256( name ):
        if name not in _sha256_cache:
            _sha256_cache[ name ] = get_sha256( config, name, echo = args.v )
        return _sha256_cache[ name ]

    rdf_graph_all       = set()
    rdf_graph_to_update = set()

    for target in config["dataset"] :
        rdf_graph_all.add( target["name"] )

    if args.force_unfreeze:
        for name in rdf_graph_all :
            target = get_target( config, name )
            target["frozen"] = False

    if args.D :
        rdf_graph_to_update = rdf_graph_all
    elif args.d : # status not checked here
        rdf_graph_to_update.update( resolve_names( args.d, rdf_graph_all, "dataset" ))
    elif args.C :
        if config["server"]["brand"] == "qlever" and not server.is_running :
            # qlever server is stopped (e.g. after a crash). The SPARQL status query
            # would return all-EMPTY, which is meaningless. Use .nt.gz checkpoints as the
            # source of truth instead: datasets without a checkpoint need (re)processing.
            print_task( "qlever server stopped — using checkpoints to determine update set" )
            for name in rdf_graph_all :
                if not server.has_checkpoint( name2context[ name ], dataset_sha256( name ) ) :
                    rdf_graph_to_update.add( name )
        else :
            config = update_config( server, config, name_to_update = rdf_graph_to_update, echo = args.v ) # may takes a while
            for name in rdf_graph_all :
                target = get_target( config, name )
                if target["status"] in { "EMPTY", "UPDATE", "PROPAGATE" } :
                    rdf_graph_to_update.add( name )

    # --------------------------------------------------------- #
    # For qlever: restrict incremental index rebuilds to the dependency
    # closure of the datasets being processed (the update set plus all
    # their transitive parents).  Untouched, unrelated datasets keep their
    # checkpoints on disk but are left out of the rebuilt index -- so the
    # served index may be partial until a --qlever_complete run reassembles
    # everything.  This avoids re-reading every checkpoint on each rebuild.
    # --------------------------------------------------------- #
    if config["server"]["brand"] == "qlever" and rdf_graph_to_update :
        parents_of = { t["name"]: list( t.get( "parent", [] ) or [] ) for t in config["dataset"] }
        scope = set()
        stack = list( rdf_graph_to_update )
        while stack :
            n = stack.pop()
            if n in scope :
                continue
            scope.add( n )
            stack.extend( parents_of.get( n, [] ) )
        # A required parent that is NOT being processed this run must already
        # have a checkpoint, otherwise the scoped index would silently miss
        # data that the updates query.
        for n in scope :
            if n not in rdf_graph_to_update and not server.has_checkpoint( name2context[ n ] ) :
                stop_error(
                    "Dataset '" + n + "' is a required parent in the dependency scope but has "
                    "no checkpoint. Include it in the run (e.g. add it to -d) or build it first."
                )
        server.index_scope = { name2context[ n ] for n in scope }
        report( "qlever index scope (datasets)", ", ".join( sorted( scope ) ) )

    # --------------------------------------------------------- #
    # Drop previous data, upload new data in their respective
    # dataset
    # --------------------------------------------------------- #
    
    is_running_in_a_container = False # initial guess
    
    for target in config["dataset"] :

        name    = target["name"]
        context = name2context[ name ]

        if not name in rdf_graph_to_update :
            # Dataset is up-to-date — nothing to reprocess.
            # For qlever: checkpoints are auto-collected by _finalize_index via .nt.gz.json
            # sidecars, so no explicit staging is needed here.  Warn if a checkpoint is
            # missing for a dataset that would otherwise be silently dropped from the index.
            if config["server"]["brand"] == "qlever" :
                if not server.has_checkpoint( context ) and server.has_index :
                    print_warn( f"No checkpoint for skipped dataset '{name}'; it will be absent from the index." )
            continue

        print_break()
        print_task( "Update dataset record: " + name )
        # For qlever: do NOT delete the old checkpoint here.  It stays on disk as a
        # last-known-good fallback and is excluded from the next index rebuild because
        # this dataset's context will be present in pending_files (see
        # _collect_checkpoint_entries' exclude_iris parameter).  dump_checkpoint
        # atomically replaces the .nt.gz at the end of processing, so a crash anywhere
        # in between leaves the OLD checkpoint intact rather than losing both old and new.
        # drop_context is a no-op for qlever (see qlever.py docstring).
        server.drop_context( context, echo = args.v )

        os.environ["TARGET_GRAPH_CONTEXT"] = context
        os.environ["kgsteward_dataset_name"]    = name
        os.environ["kgsteward_dataset_context"] = context
        replace = {}

        if "system" in target :
            for cmd in target["system"] :
                cmd2 = replace_env_var( cmd )
                print( colored( cmd2, "cyan" ))
                exit_code = os.system( cmd2 )
                if not exit_code == 0 :
                    raise stop_error( 'System cmd failed: ' + cmd2 )

        if "url" in target :
            for u in target["url"] :
                path = replace_env_var( u )
                if config["url_loader"]["method"] == "curl_riot_store":
                    filename = config["url_loader"]["tmp_dir"] + "/" + path.split('/')[-1]
                    cmd = [ "curl", path, "-o", filename ]
                    print( colored( " ".join( cmd ), "cyan" ))
                    subprocess.run( cmd )
                    server.load_from_file_using_riot( filename, context, echo = args.v )
                else: # direct sparql_load
                    if config["server"]["brand"] == "qlever":
                        # qlever cannot defer LOAD — download immediately and stage for indexing
                        server.load_url_as_file( path, context, echo = args.v )
                    else:
                        server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = args.v )
                        server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <{path}>
    }}
}}""", echo = args.v )
        if "file" in target :
            if config["file_loader"]["method"] == "http_server":
                if config["server"]["brand"] == "qlever":
                    # qlever uses a static index and does not support SPARQL LOAD.
                    # Stage files directly into the deferred index build instead.
                    # void:dataDump is baked into the staged files by _stage_file — no
                    # explicit INSERT needed here.
                    for path in target["file"] :
                        for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                            filename = dir + "/" + fn
                            if not os.path.isfile( filename ):
                                stop_error( "File not found: " + filename )
                            server.load_from_file( filename, context, echo = args.v )
                else:
                    fs = LocalFileServer( port = config["file_loader"][ "port" ] )
                    for path in target["file"] :
                        for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                            if not os.path.isfile( dir + "/" + fn ):
                                stop_error( "File not found: " + dir + "/" + fn )
                            fs.expose( dir ) # cache already exposed directory
                            if not is_running_in_a_container:
                                try:
                                    path = "http://localhost:" + str( config["file_loader"][ "port" ] ) + "/" + fn
                                    server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = args.v )
                                except Exception as e:
                                    is_running_in_a_container = True # new guess
                                    print_warn( "Maybe the server is running in a container => let's try again!" )
                            if is_running_in_a_container:
                                # see https://stackoverflow.com/questions/68021524/access-localhost-from-docker-container
                                path = "http://host.docker.internal:" + str( config["file_loader"][ "port" ] ) + "/" + fn
                                server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = args.v )
                            filename = dir + "/" + fn
                            server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <file://{filename}>
    }}
}}""", echo = args.v )
                    fs.terminate()
            else: # config["file_loader"]["type"] != "http_server"
                for path in target["file"] :
                    for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                        filename = dir + "/" + fn
                        if config["file_loader"]["method"] == "sparql_load":
                            server.sparql_update( f"LOAD <file://{filename}> INTO GRAPH <{context}>", echo = args.v )
                        elif config["file_loader"]["method"] == "file_store":
                            server.load_from_file( filename, context, echo = args.v )
                        elif config["file_loader"]["method"] == "riot_chunk_store":
                            server.load_from_file_using_riot( filename, context, echo = args.v )
                        else:
                            raise SystemError( "Unexpected file loader method: " + config["file_loader"]["method"] )
                        server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <file://{filename}>
    }}
}}""", echo = args.v)
        if "zenodo" in target :
            for id in target["zenodo"]:
                r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
                if not r.status_code == 200 :
                    raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
                info = r.json()
                for record in info["files"]:
                    path = "https://zenodo.org/records/" + str( id ) + "/files/" + record["key"]
                    server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = args.v )
                    server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <{path}>
    }}
}}""", echo = args.v )

        if "replace" in target:
            for key in target["replace"]:
                replace[key] = replace_env_var( target["replace"][key] )

        if "update" in target :
            for path in target["update"] :
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    report( "read", filename )
                    with open( filename ) as f:
                        sparql = f.read()
                    for key in sorted( replace.keys()):
                        sparql = sparql.replace( key, replace[ key ])
                    for s in split_sparql_update( sparql): # split on ";" to execute one statement at a time
                        server.sparql_update( s, echo = args.v )
        if "special" in target:
            for key in target["special"]:
                if key == "sib_swiss_void":
                    for s in split_sparql_update( make_void_description( context )):
                        server.sparql_update( s, echo = args.v )
                if key == "sib_swiss_prefix":
                    if "prefixes" in config:
                        sparql = make_prefix_description( context, config["prefixes"] )
                        for s in sparql:
                            server.sparql_update( s, echo = args.v )
                    else:
                        print_warn( "Key not found in YAML config: prefixes" )
                if key == "sib_swiss_query":
                    filenames = []
                    if "queries" in config:
                        for record in config["queries"] :
                            for path in record["file"]:
                                #FIXME: filter on publish
                                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                                    filenames.append( dir + "/" + fn )
                            sparql = make_query_description( context, filenames )
                            for s in sparql:
                                server.sparql_update( s, echo = args.v )
                    else:
                        print_warn( "Key not found in YAML config: queries" )
    
        update_dataset_info( server, config, name, echo = args.v )
        # For qlever: immediately finalize the index and checkpoint this dataset,
        # mimicking the GraphDB driver's per-dataset persistence model.
        # mark_rebuild queues the rebuild+checkpoint sentinel; server_start triggers
        # _finalize_index (which auto-includes all existing checkpoints + the newly
        # staged files), applies the queued SPARQL updates, rebuilds the persistent
        # index, and dumps the checkpoint — all before moving to the next dataset.
        if config["server"]["brand"] == "qlever" :
            server.mark_rebuild( context, dataset_sha256( name ) )
            server.server_start( echo = args.v )

    # --------------------------------------------------------- #
    # For qlever: safety net — flush any staged data not yet finalized
    # (normally server_start is called per-dataset inside the loop above)
    # --------------------------------------------------------- #
    if config["server"]["brand"] == "qlever" and ( server.pending_files or server.pending_updates ) :
        server.server_start( echo = args.v )

    # --------------------------------------------------------- #
    # For qlever: assemble the complete index from all checkpoints
    # (plus the text index, if configured) when --qlever_complete is set.
    # --------------------------------------------------------- #
    if args.qlever_complete and config["server"]["brand"] == "qlever":
        print_break()
        print_task( "Assemble complete qlever index (all checkpoints + text index)" )
        server.complete_index( echo = args.v )

    # --------------------------------------------------------- #
    # Force update namespace declarations
    # --------------------------------------------------------- #

    if args.graphdb_upload_prefixes:
        if not config["server"]["brand"] == "graphdb":
            print_warn( "Option --graphdb_upload_prefixes not supported for server brand: " + config["server"]["brand"] )
        else:
            if "prefixes" in config:
                print_task( "rewrite prefixes" )
                server.rewrite_prefixes()
                catch_key_value = re.compile( r"@prefix\s+(\S*):\s+<([^>]+)>" )
                for filename in config["prefixes"] :
                    report( "parse file", filename )
                    file = open( replace_env_var( filename ))
                    for line in file:
                        match = catch_key_value.search( line )
                        if match:
                            server.set_prefix( match.group( 1 ), match.group( 2 ))
            

    # --------------------------------------------------------- #
    # Force update dataset info -- re-stamp the kgsteward:Dataset
    # metadata (triples count, modified, checksum) for every dataset
    # WITHOUT reloading the source data.  Useful when checkpoints exist
    # but their metadata is missing or stale (e.g. checkpoints produced
    # by a kgsteward version that had the metadata-loss bug, or after a
    # bulk adoption via --qlever_upload_quad_and_dump_checkpoints).
    #
    # For qlever, each refresh also queues a mark_rebuild sentinel so
    # the final server_start flushes all the INSERTs against the
    # running index AND dumps a fresh .nt.gz for every refreshed
    # context -- otherwise the in-memory metadata would be lost at the
    # next index rebuild.
    # --------------------------------------------------------- #

    if args.U :
        is_qlever = config["server"]["brand"] == "qlever"
        for target in config["dataset"] :
            name = target["name"]
            if is_qlever and not server.has_checkpoint( name2context[ name ] ):
                # Nothing to re-stamp -- the data isn't in any checkpoint, so
                # any metadata we insert would be wiped by the next rebuild.
                print_warn( f"-U: skipping '{name}' (no checkpoint on disk)" )
                continue
            print_break()
            print_task( "Refresh dataset info: " + name )
            update_dataset_info( server, config, name, echo = args.v )
            if is_qlever:
                server.mark_rebuild( name2context[ name ], dataset_sha256( name ) )
        if is_qlever and server.pending_updates:
            print_break()
            print_task( "Flush metadata updates and re-dump checkpoints" )
            server.server_start( echo = args.v )

    # --------------------------------------------------------- #
    # Run all validation tests
    # --------------------------------------------------------- #

    if args.V:
        print_break()
        print_task( "Run SPARQL queries to validate repository content." )
        if "queries" not in config:
            stop_error( "There are no 'queries' key in config! ")
        test_to = 0
        test_ok = 0
        test_ko = 0 
        for record in config["queries"] :
            for path in record["file"]: 
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    # print_break()
                    report( 'query file', filename )        
                    with open( filename ) as f: sparql = f.read()
                    if args.v:
                        print_strip( sparql, color = "green" )
                    r = server.sparql_query( sparql, echo = args.v, timeout=args.timeout )
                    if r is None:
                        if args.timeout is not None: # likely timeout
                            test_to = test_to + 1
                        else:
                            test_ko = test_ko + 1
                        continue
                    try:
                        header, rows = sparql_result_to_table( r )
                    except Exception as e :
                        print_warn( str( e ))
                        test_ko = test_ko + 1
                        continue
                    if "test" not in record:
                        continue
                    ok = True
                    if "min_row_count" in record["test"]:
                        if len( rows ) < record["test"]["min_row_count"] :
                            print_warn( "Expected at least " + str( record["test"]["min_row_count"] ) + " rows, but got " + str( len( rows )))
                            test_ko = test_ko + 1
                            ok = False
                        else: 
                            test_ok = test_ok + 1
                    if "max_row_count" in record["test"]:
                        if len( rows ) > record["test"]["max_row_count"] :
                            print_warn( "Expected at most " + str( record["test"]["max_row_count"] ) + " rows, but got " + str( len( rows )))
                            test_ko = test_ko + 1
                            ok = False
                        else: 
                            test_ok = test_ok + 1
                    if not ok:
                        if not args.v: print_strip( sparql, color = "green" )
                        print( colored( "\t".join( header ), "red" ))
                        for row in rows:
                            print( colored( "\t".join( map( str, row )), "red" ))
        report( "test timeout", test_to )
        report( "test passed",  test_ok )
        report( "test failed",  test_ko )
        sys.exit( 0 if test_ko == 0 else 1 )

    # --------------------------------------------------------- #
    # Refresh all GraphDB preloaded queries
    # --------------------------------------------------------- #

    if args.Q:
        print_break()
        print_task( "Run SPARQL queries to validate their syntax" )
        if "queries" not in config:
            stop_error( "There are no 'queries' key in config! ")
        for record in config["queries"] :
            for path in record["file"]: 
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    print_break()
                    with open( filename ) as f: sparql = f.read()
                    name = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                    sparql = "## " + name + " ##\n" + sparql # to ease debugging from logs
                    report( "validate", filename )
                    server.validate_sparql_query( sparql, echo = args.v, timeout=args.timeout )

    if args.graphdb_upload_queries:
        print_break()
        print_task( "GraphDB upload queries" )     
        if not config["server"]["brand"] == "graphdb":
            print_warn( "Option --graphdb_upload_queries not supported for server brand: " + config["server"]["brand"] )
        else:
            r = server.graphdb_call({ 'url' : '/rest/sparql/saved-queries', 'method' : 'GET' })
            for item in r.json() :
                print_break()
                report( "remove", item['name'] ) # GraphDB builtin queries cannot be deleted
                server.graphdb_call({
                    'url'    : '/rest/sparql/saved-queries',
                    'method' : 'DELETE',
                    'params' : { 'name': item['name']}
                })
            for record in config["queries"] :
                for path in record["file"]: 
                    for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                        filename = dir + "/" + fn
                        report( "read", filename )
                        print_break()
                        with open( filename ) as f: sparql = f.read()
                        name = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                        sparql = "## " + name + " ##\n" + sparql # to ease debugging from logs
#                    report( "validate", filename )
#                    server.validate_sparql_query( sparql, echo = args.v, timeout=args.timeout )
#                    if not args.graphdb_upload_query:
#                        continue
                        report( "load", filename )
                        server.graphdb_call({
                            'url'    : '/rest/sparql/saved-queries',
                            'method'  : 'POST',
                            'headers' : {
                                'Content-Type': 'application/json', 
                                'Accept-Encoding': 'identity'
                            },
                            'json'    : { 'name': name, 'body': sparql, "shared": "true" }
                        }, [ 201 ] )

    # if args.sib_swiss_editor:
    #     print_break()
    #     print_task( "Prepare queries for SIB-swiss editor" )     
    #     counter = 0 # to keep track of the original input order 
    #     prefix = {} # to create a non-redundant list
    #     catch_key_value_ttl = re.compile( r"@prefix\s+(\S*):\s+<([^>]+)>", re.IGNORECASE )
    #     catch_key_value_rq  = re.compile( r"PREFIX\s+(\S*):\s+<([^>]+)>",  re.IGNORECASE )
    #     g = Graph()
    #     SPARQLQUERY   = Namespace( server.get_endpoint_query() + "/.well-known/sparql-examples/" )
    #     prefixes_iri  = URIRef(    server.get_endpoint_query() + "/.well-known/prefixes" )
    #     PREFIX        = Namespace( server.get_endpoint_query() + "/.well-known/prefix/" )
    #     RDF           = Namespace( "http://www.w3.org/1999/02/22-rdf-syntax-ns#" )
    #     RDFS          = Namespace( "http://www.w3.org/2000/01/rdf-schema#" )
    #     SCHEMA        = Namespace( "https://schema.org/" )
    #     SH            = Namespace( "http://www.w3.org/ns/shacl#" )
    #     SPEX          = Namespace( "https://purl.expasy.org/sparql-examples/ontology#" )
    #     XSD           = Namespace( "http://www.w3.org/2001/XMLSchema#" )
    #     OWL           = Namespace( "http://www.w3.org/2002/07/owl#" )
    #     g.bind( "rdf",    RDF )
    #     g.bind( "rdfs",   RDFS )
    #     g.bind( "rdfs",   RDFS )
    #     g.bind( "schema", SCHEMA )
    #     g.bind( "sh",     SH )
    #     g.bind( "spex",   SPEX )
    #     g.bind( "xsd",    XSD )
    #     g.bind( "owl",    OWL )
    #     g.bind( "sparql_query_" + config["server"]["repository"], SPARQLQUERY )
    #     g.bind( "prefix_" + config["server"]["repository"],    PREFIX )
    #     if "queries" in config:
    #         for record in config["queries"] :
    #             for filename in record["file"]:
    #                 report( "read", filename )
    #                 report( "parse file", filename )
    #                 counter = counter + 1
    #                 comment = []
    #                 select  = [] # i.e. the SPARQL query itself
    #                 name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
    #                 with open( filename ) as file:
    #                     for line in file:
    #                         if re.match( "^#", line ):
    #                             comment.append( re.sub( r"^#\s*", "", line.rstrip() ))
    #                         else:
    #                             select.append( line.rstrip().replace( "\t", "    "))
    #                             match = catch_key_value_rq.search( line )
    #                             if match:
    #                                 prefix[match.group( 1 )] = match.group( 2 )
    #                 # server.validate_sparql_query( "\n".join( select ), echo=args.v, timeout=args.timeout )
    #                 iri = SPARQLQUERY[ "query_" + config["server"]["repository"] + str( counter ).rjust( 4, '0' )]
    #                 g.add(( iri, RDF.type, SH.SPARQLExecutable ))
    #                 g.add(( iri, RDF.type, SH.SPARQLSelectExecutable ))
    #                 # g.add(( iri, RDFS.label,    Literal( "<b>" + name.replace( "_", " ") + "</b><br>")))
    #                 g.add(( iri, RDFS.comment,  Literal( "<b>" + name.replace( "_", " ") + "</b><br>") + "\n".join( comment )))
    #                 g.add(( iri, SH.prefixes,   prefixes_iri ))
    #                 g.add(( iri, SH.select,     Literal( "\n".join( select ))))
    #                 # g.add(( iri, SCHEMA.target, URIRef( server.get_endpoint_query()))) not portable
    #     if "prefixes" in config:
    #         for filename in config["prefixes"] :
    #             report( "parse file", filename )
    #             file = open( replace_env_var( filename ))
    #             for line in file:
    #                 match = catch_key_value_ttl.search( line )
    #                 if match:
    #                     prefix[ match.group( 1 ) ] = match.group( 2 )
    #     for key in prefix:
    #         g.add(( prefixes_iri,  SH.declare,   PREFIX[ key ]))
    #         g.add(( PREFIX[ key ], SH.prefix,    Literal( key )))
    #         g.add(( PREFIX[ key ], SH.namespace, Literal( prefix[key], datatype=XSD.anyURI )))
    #     g.serialize(
    #         format="turtle",
    #         destination = args.sib_swiss_editor
    #     )
    #     sys.exit( 0 )
        
    # --------------------------------------------------------- #
    # Dump dataset contents and/or SELECT query results as sorted
    # TSV into --dump_dir, for debugging and cross-server diffing.
    # --------------------------------------------------------- #

    if any([ args.dump_all_dataset, args.dump_dataset, args.dump_all_select, args.dump_select ]):
        if not args.dump_dir:
            stop_error( "--dump_dir is required for any --dump_* option" )
        if not os.path.isdir( args.dump_dir ):
            stop_error( "Not a directory: " + args.dump_dir )

    # Datasets (formerly -y)
    if args.dump_all_dataset or args.dump_dataset:
        if args.dump_all_dataset and args.dump_dataset:
            stop_error( "Use either --dump_all_dataset or --dump_dataset, not both" )
        by_name = { d["name"]: d for d in config["dataset"] }
        names   = list( by_name ) if args.dump_all_dataset else resolve_names( args.dump_dataset, by_name, "dataset" )
        print_break()
        print_task( "Dump dataset contents in TSV format" )
        for name in names:
            print_break()
            header, rows = server.dump_context( by_name[name]["context"], echo = args.v )
            write_sorted_tsv( args.dump_dir, name, header, rows )

    # SELECT queries (formerly -x)
    if args.dump_all_select or args.dump_select:
        if args.dump_all_select and args.dump_select:
            stop_error( "Use either --dump_all_select or --dump_select, not both" )
        if "queries" not in config:
            stop_error( "There are no 'queries' key in config!" )
        catalog = {} # query name (file basename) -> file path
        for record in config["queries"]:
            for path in record["file"]:
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    catalog[ re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename ) ] = filename
        names = list( catalog ) if args.dump_all_select else resolve_names( args.dump_select, catalog, "query" )
        print_break()
        print_task( "Dump SELECT query results in TSV format" )
        for name in names:
            print_break()
            report( "read file", catalog[name] )
            with open( catalog[name] ) as file:
                sparql = file.read()
            r = server.sparql_query( sparql, echo = args.v, timeout = args.timeout )
            if r is None: # timeout
                print_warn( "Timeout while executing query: " + catalog[name] )
                report( "write file", "skipped" )
                continue
            header, rows = sparql_result_to_table( r )
            write_sorted_tsv( args.dump_dir, name, header, rows )

    # --------------------------------------------------------- #
    # Turn free access ON
    # --------------------------------------------------------- #

    if args.graphdb_free_access :
        print_break()
        print_task( "Set GraphDB repository in free read-only mode" )     
        if not config["server"]["brand"] == "graphdb":
            print_warn( "Option --graphdb_upload_queries not supported for server brand: " + config["server"]["brand"] )
        else:
            server.free_access()

    if args.graphdb_compact_indexes:
        print_break()
        print_task( "Compact GraphDB indexes" )     
        if not config["server"]["brand"] == "graphdb":
            print_warn( "Option --graphdb_compact_indexes not supported for server brand: " + config["server"]["brand"] )
        else:
            server.compact_indexes()

    # --------------------------------------------------------- #
    # Print final repository status
    # FIXME: implement target_graph_context rewrite
    # --------------------------------------------------------- #

    config = update_config( server, config, echo = args.v )

    if args.dependency_graph:
        print_break()
        print_task( "Write dependency graph" )
        write_dependency_graph( config, args.dependency_graph )

    contexts = server.list_context()
    print_break()
    print_task( "Show current status" )
    print( colored("                            name        #triple        last modified    status", "blue" ))
    print( colored("================================        =======     =================== ======", "blue" ))
    for item in config["dataset"] :
        print( colored( '{:>32}   {:>12}    {:>20} {}'.format(
            item["name"],
            item["count"],
            item["date"],
            item["status"]
        ), "blue" ))
        context = item[ "context" ]
        if context in contexts :
            contexts.remove( context )
    for name in contexts:
        print( colored( '{:>32} : {:>12}    {:>20} {}'.format( name, "", "", "UNKNOWN" ), "blue" ))
    print_break()

    # Ensure the qlever server is running at the end of the session
    # (only if an index exists — avoids starting a server with no index)
    if config["server"]["brand"] == "qlever" and not server.is_running and server.has_index:
        print_break()
        print_task( "Start qlever server" )
        server.server_start( echo = args.v )

    # Dump per-call sparql_update timings to a TSV, if requested.  Useful for
    # diagnosing slow updates in a single backend and for benchmark comparison
    # across backends (run with each, then join on sha1_8 to compare timings).
    if args.sparql_update_stats and hasattr( server, "dump_sparql_update_stats" ):
        print_break()
        print_task( "Dump per-call sparql_update timing stats" )
        server.dump_sparql_update_stats( args.sparql_update_stats )

    #  save_json_schema(  "doc/kgsteward.schema.json" )

# --------------------------------------------------------- #
# Main
# --------------------------------------------------------- #

if __name__ == "__main__":
    main()
