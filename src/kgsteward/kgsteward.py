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
# from .oxigraph   import OxigraphClient  # in preparation
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
        help   = "Validate the repository content, by running SPARQL queries that supposed to return the problems. "
                 "It might be combined with --timeout."
    )
    parser.add_argument(
        '-Q',
        action = 'store_true',
        help   = "Run all SPARQL queries. It might be combined with --timeout."
    )
    parser.add_argument(
        '-x',
        help   = "Dump all query results in TSV format to dir <X>. "
                 "Sorting of results is enforced, irrespective of the SPARQL queries. "
                 "The results are amended to facilitate the comparison of different server output, e.g. using diff. "
                 "Using this service is useful for debugging, but not meant to retrieve data. " 
                 "It is possibly slow and memory hungry." 
    )
    parser.add_argument(
        '-y',
        help   = "Dump all context data in TSV format to dir <Y>. "                 
                 "Sorting of results is enforced, irrespective of the SPARQL queries. "
                 "The results are amended to facilitate the comparison of different server output, e.g. using diff. "
                 "Using this service is useful for debugging, but not meant to retrieve data. " 
                 "It is possibly slow and memory hungry." 
    )
    parser.add_argument(
        '-v',
        action = 'store_true',
        help    = "Verbose mode: print out SPARQL queries being executed. "
                  "Super useful for debugging SPARQL update (after string replacement)."
    )
    parser.add_argument(
        '--timeout',
        type = int,
        help   = "Timeout delay in seconds. There is no timeout by default. "
                 "Values lower than 15 are not recommended with GraphDB." 
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
        '--sib_swiss_editor',
        help = "Document and save all queries and prefix declarations in a single Turtle file, ready to be retrived by the sib-swiss editor (https://github.com/sib-swiss/sparql-editor). "
               "Note that the <SIB_SWISS_EDITOR> file is not uploaded directly to the store. "
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
    context = name2context[ name ] # get_context( config, name )
    os.environ["TARGET_GRAPH_CONTEXT"] = context
    os.environ["kgsteward_dataset_name"]    = name
    os.environ["kgsteward_dataset_context"] = context
    sha256 = hashlib.sha256()
    if "system" in target :
        for cmd in target["system"] :
            sha256.update( cmd.encode( 'utf-8' ))
    if "url" in target :
        for url in target["url"] :
            path = replace_env_var( url )
            sha256.update( path.encode('utf-8') )
            if re.search( r"https?:", path ) :
               info = get_head_info( path, echo = echo ) # as a side effect: verify is the server is responding
               sha256.update( info.encode('utf-8'))
            elif re.search( r"ftp:", path ) : # do not run HEAD on ftp server FIXME: implement something better
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
    if "file" in target :
        for path in target["file"] :
            for dir, filename in expand_path( path, config["kgsteward_yaml_directory"], fatal = False ):
                with open( replace_env_var( dir + "/" + filename ), "rb") as f :
                    for chunk in iter( lambda: f.read(4096), b"") :
                        sha256.update( chunk )
    if "zenodo" in target : # FIXME: remove this!
        for id in target["zenodo"]:
            r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
            if not r.status_code == 200 :
                raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
            info = r.json()
            for record in info["files"] :
                sha256.update( record["checksum"].encode('utf-8'))
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
    return sha256.hexdigest()

def update_config( server, config, echo = True ) :
    """ Compute current status information about the records in repository.
        Take dependency into account."""
    print_break()
    print_task( "Retrieve current status" )
    name2item = {}
    for item in config["dataset"] :
        name = item["name"]
        name2item[name]    = item
        item["count"]      = ""
        item["date"]       = ""
        item["sha256_old"] = ""
        item["status"]     = "FROZEN" if item["frozen"] else "EMPTY"
    r = server.sparql_query( """
PREFIX void: <http://rdfs.org/ns/void#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX ex:   <http://example.org/>
SELECT ?context ?x ( REPLACE( STR( ?y ), "\\\\..+", "" ) AS ?t ) ?sha256
WHERE{
    ?context a void:Dataset   ;
             void:triples  ?x      ;
             dct:modified  ?y      ;
             ex:has_sha256 ?sha256 .
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
                item["count"]      = rec["x"]["value"]
                item["date"]       = rec["t"]["value"]
                item["sha256_old"] = str( rec["sha256"]["value"] )
                item["sha256_new"] = get_sha256( config, name, echo = echo )
                if item["sha256_old"] == item["sha256_new"]:
                    item["status"] = "ok"
                elif not item["status"] == "FROZEN":
                    item["status"] = "UPDATE"
        except Exception as e: # test before and remove this typ/excep block 
            stop_error( "Failed parsing server response: " + str( e ))
    for item in config["dataset"] :
        if item["status"] == "ok" and "parent" in item :
            for parent in item["parent"] :
                if name2item[parent]["status"] in { "EMPTY", "UPDATE", "PROPAGATE" }:
                    item["status"] = "PROPAGATE"
    return config

def update_dataset_info( server, config, name, echo = True ) :
    print_break()
    context = name2context[ name ]
    sha256 = get_sha256( config, name, echo = echo )
    server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX ex:   <http://example.org/>

INSERT {{
    GRAPH <{context}> {{
        <{context}> a void:Dataset ;
            void:triples               ?c   ;
            dct:modified               ?now ;
            ex:has_sha256              "{sha256}" .
    }}
}}
WHERE {{
    GRAPH <{context}> {{
        SELECT
            ( COUNT( * ) AS ?c )
            ( NOW() AS ?now )
        WHERE {{
            ?s ?p ?o
        }}
    }}
}}
""", echo = echo )

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
                replace_env_var( config["server"]["server_config"] ),
                echo = args.v
            )
        except Exception as e:
            stop_error( "Failed to connect to Fuseki server: " + str( e ))
    else:
        stop_error( "Unknown server brand: " + config["server"]["brand"] )

    for key in config["server"].keys():
        os.environ[ "kgsteward_server_" + str( key )] = str( config["server"][key] )
    os.environ[ "kgsteward_server_endpoint_query"]  = server.get_endpoint_query()
    os.environ[ "kgsteward_server_endpoint_update"] = server.get_endpoint_update()

    # --------------------------------------------------------- #
    # Create a new empty repository or rewrite an existing one
    # --------------------------------------------------------- #

    # FIXME: check if the repository exists 
    repo = replace_env_var( config["server"]["repository"] )
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
    # Establish the list of contexts to update
    # --------------------------------------------------------- #

    rdf_graph_all       = set()
    rdf_graph_to_update = set()

    for target in config["dataset"] :
        rdf_graph_all.add( target["name"] )

    if args.D :
        rdf_graph_to_update = rdf_graph_all
    elif args.d : # status not checked here
        for name in args.d.split( "," ) :
            if name in rdf_graph_all :
                rdf_graph_to_update.add( name )
            else :
                raise stop_error( "Invalid name: " + name )
    elif args.C :
        config = update_config( server, config, echo = args.v ) # may takes a while
        for name in rdf_graph_all :
            target = get_target( config, name )
            if target["status"] in { "EMPTY", "UPDATE", "PROPAGATE" } :
                rdf_graph_to_update.add( name )

    # --------------------------------------------------------- #
    # Drop previous data, upload new data in their respective
    # dataset
    # --------------------------------------------------------- #
    
    is_running_in_a_container = False # initial guess
    
    for target in config["dataset"] :

        name = target["name"]
        if not name in rdf_graph_to_update :
            continue

        print_break()
        print_task( "Update dataset record: " + name )
        context = name2context[ name ]
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
                    server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>", echo = args.v )
                    server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <{path}>
    }}
}}""", echo = args.v )
        if "file" in target :
            if config["file_loader"]["method"] == "http_server":
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
    # Force update dataset info
    # --------------------------------------------------------- #

    if args.U :
        for target in config["dataset"] :
            update_dataset_info( target )

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
            if "test" not in record:
                continue
            for path in record["file"]: 
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    # print_break()
                    report( 'query file', filename )        
                    with open( filename ) as f: sparql = f.read()
                    if args.v:
                        print_strip( sparql, color = "green" )
                    r = server.sparql_query( sparql, echo = args.v, timeout=args.timeout )
                    header, rows = sparql_result_to_table( r )
                    if args.timeout is not None and r is None: # likely timeout
                        # report( "Result", "Unknown" )
                        test_to = test_to + 1
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
        sys.exit( test_ko == 0 )

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

    if args.sib_swiss_editor:
        print_break()
        print_task( "Prepare queries for SIB-swiss editor" )     
        counter = 0 # to keep track of the original input order 
        prefix = {} # to create a non-redundant list
        catch_key_value_ttl = re.compile( r"@prefix\s+(\S*):\s+<([^>]+)>", re.IGNORECASE )
        catch_key_value_rq  = re.compile( r"PREFIX\s+(\S*):\s+<([^>]+)>",  re.IGNORECASE )
        g = Graph()
        SPARQLQUERY   = Namespace( server.get_endpoint_query() + "/.well-known/sparql-examples/" )
        prefixes_iri  = URIRef(    server.get_endpoint_query() + "/.well-known/prefixes" )
        PREFIX        = Namespace( server.get_endpoint_query() + "/.well-known/prefix/" )
        RDF           = Namespace( "http://www.w3.org/1999/02/22-rdf-syntax-ns#" )
        RDFS          = Namespace( "http://www.w3.org/2000/01/rdf-schema#" )
        SCHEMA        = Namespace( "https://schema.org/" )
        SH            = Namespace( "http://www.w3.org/ns/shacl#" )
        SPEX          = Namespace( "https://purl.expasy.org/sparql-examples/ontology#" )
        XSD           = Namespace( "http://www.w3.org/2001/XMLSchema#" )
        OWL           = Namespace( "http://www.w3.org/2002/07/owl#" )
        g.bind( "rdf",    RDF )
        g.bind( "rdfs",   RDFS )
        g.bind( "rdfs",   RDFS )
        g.bind( "schema", SCHEMA )
        g.bind( "sh",     SH )
        g.bind( "spex",   SPEX )
        g.bind( "xsd",    XSD )
        g.bind( "owl",    OWL )
        g.bind( "sparql_query_" + config["server"]["repository"], SPARQLQUERY )
        g.bind( "prefix_" + config["server"]["repository"],    PREFIX )
        if "queries" in config:
            for record in config["queries"] :
                for filename in record["file"]:
                    report( "read", filename )
                    report( "parse file", filename )
                    counter = counter + 1
                    comment = []
                    select  = [] # i.e. the SPARQL query itself
                    name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                    with open( filename ) as file:
                        for line in file:
                            if re.match( "^#", line ):
                                comment.append( re.sub( r"^#\s*", "", line.rstrip() ))
                            else:
                                select.append( line.rstrip().replace( "\t", "    "))
                                match = catch_key_value_rq.search( line )
                                if match:
                                    prefix[match.group( 1 )] = match.group( 2 )
                    # server.validate_sparql_query( "\n".join( select ), echo=args.v, timeout=args.timeout )
                    iri = SPARQLQUERY[ "query_" + config["server"]["repository"] + str( counter ).rjust( 4, '0' )]
                    g.add(( iri, RDF.type, SH.SPARQLExecutable ))
                    g.add(( iri, RDF.type, SH.SPARQLSelectExecutable ))
                    # g.add(( iri, RDFS.label,    Literal( "<b>" + name.replace( "_", " ") + "</b><br>")))
                    g.add(( iri, RDFS.comment,  Literal( "<b>" + name.replace( "_", " ") + "</b><br>") + "\n".join( comment )))
                    g.add(( iri, SH.prefixes,   prefixes_iri ))
                    g.add(( iri, SH.select,     Literal( "\n".join( select ))))
                    # g.add(( iri, SCHEMA.target, URIRef( server.get_endpoint_query()))) not portable
        if "prefixes" in config:
            for filename in config["prefixes"] :
                report( "parse file", filename )
                file = open( replace_env_var( filename ))
                for line in file:
                    match = catch_key_value_ttl.search( line )
                    if match:
                        prefix[ match.group( 1 ) ] = match.group( 2 )
        for key in prefix:
            g.add(( prefixes_iri,  SH.declare,   PREFIX[ key ]))
            g.add(( PREFIX[ key ], SH.prefix,    Literal( key )))
            g.add(( PREFIX[ key ], SH.namespace, Literal( prefix[key], datatype=XSD.anyURI )))
        g.serialize(
            format="turtle",
            destination = args.sib_swiss_editor
        )
        sys.exit( 0 )
        
    if args.x:
        print_break()
        print_task( "Serialize query results" )     
        if "queries" not in config:
            stop_error( "There are no 'queries' key in config! ")
        print_break()
        print_task( "Dump all query results in TSV format" )
        if not os.path.isdir( args.x ):
            stop_error( "Not a directory: " + args.x )
        for record in config["queries"] :
            for path in record["file"]:
                for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                    filename = dir + "/" + fn
                    print_break()
                    report( "read file", filename )
                    name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                    with open( filename ) as file:
                        sparql = file.read()
                    r = server.sparql_query( sparql, echo = args.v, timeout = args.timeout )
                    if r is not None: # no timeout, i.e. the data are here
                        header, rows = sparql_result_to_table( r )
                        out_path =  args.x + "/" + name + ".tsv"
                        report( "write file", out_path )
                        with open( out_path, "w", encoding="utf-8" ) as f:
                            f.write( "\t".join( header ) + "\n" )
                            for row in sorted( rows ):
                                f.write( "\t".join( map( str, row )) + "\n" )

    if args.y:
        print_break()
        print_task( "Dump all contexts in TSV format" )
        if not os.path.isdir( args.y ):
            stop_error( "Not a directory: " + args.y )
        for item in config["dataset"]:
            print_break()
            header, rows = server.dump_context( item["context"], echo = args.v )
            out_path =  args.y + "/" +  item["name"] + ".tsv"
            report( "write file", out_path )
            with open( out_path, "w", encoding="utf-8"  ) as f:
                for row in sorted( rows ):
                    f.write( "\t".join( map( str, row )) + "\n" )

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

    # --------------------------------------------------------- #
    # Print final repository status
    # FIXME: implement target_graph_context rewrite
    # --------------------------------------------------------- #

    config = update_config( server, config, echo = args.v )

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

    #  save_json_schema(  "doc/kgsteward.schema.json" )

# --------------------------------------------------------- #
# Main
# --------------------------------------------------------- #

if __name__ == "__main__":
    main()
