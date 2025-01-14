"""Main kgsteward module."""

import argparse
import os
import sys
import re
import hashlib
import glob
import requests  # https://docs.python-requests.org/en/master/user/quickstart/
import rdflib
import getpass
from   dumper    import dump # get ready to help debugging
from   termcolor import colored
from   rdflib    import *

from .common     import *
from .yamlconfig import parse_yaml_conf
from .graphdb    import GraphDBClient
from .fuseki     import FusekiClient
from .rdf4j      import RFD4JClient     # in preparation
# from .oxigraph   import OxigraphClient  # in preparation
# from .virtuoso   import VirtuosoClient  # in preparation
from .fileserver import LocalFileServer

name2context = {} # global helper dict
context2name = {} # same

# ---------------------------------------------------------#
# The RDF source dataset configuration
#
# Nota Bene: some resources are splitted into several files
# because there exists a limit of 200 MB per file in GraphDB
# ---------------------------------------------------------#

# ---------------------------------------------------------#
# Command-line options
# ---------------------------------------------------------- #

def get_user_input():
    """Generate argparse CLI and return user input."""

    parser = argparse.ArgumentParser(
        description = "A command line tool to manage the content of RDF store. "
            "This script rely on a YAML config file (version 2). "
            "Source code and documentation are available from https://github.com/sib-swiss/kgsteward"
    )
    parser.add_argument(
        'yamlfile',
        nargs = 1,
        help  = "Mandatory configuration file in YAML format"
    )
    parser.add_argument(
        '-F',
        action = 'store_true',
        help   = "Force rebuild the core of the RDF database. "
                 "Implies -I -D -L options."
    )
    parser.add_argument(
        '-I',
        action = 'store_true',
        help   = "Create the repository or force recreate the repository, "
                 "i.e. erase everything"
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
        help   = "Load missing/incomplete dataset to complete the repository."
    )
    parser.add_argument(
        '-L',
        action = 'store_true',
        help   = "Provide public free-access to the repository, which is "
            "strictly read-only."
    )
    parser.add_argument(
        '-U',
        action = 'store_true',
        help   = 'Force update internal checksum without updating the data.'
    )
    parser.add_argument(
        '-V',
        action = 'store_true',
        help   = 'Validate the repository content.'
    )
    parser.add_argument(
        '-P',
        action = 'store_true',
        help   = "Reset all prefixes"
    )
    parser.add_argument(
        '-Q',
        action = 'store_true',
        help   = "Clean, test and reload all SPARQL queries. This is a GraphDB "
                 "specific option. Note that the queries are global to a web "
                 "site, i.e. they are not attached to a specific repository. "
                 "It may fail on SPARQL syntax error!"
    )
    parser.add_argument(
        '-r',
        help   = "Save prefix and queries into supplied dir"
    )
    parser.add_argument(
        '-x',
        help   = "Dump all query results in TSV format to dir <X>"
    )
    parser.add_argument(
        '-y',
        help   = "Dump all contexts in nt formatton dir <Y>" 
    )

    args = parser.parse_args()

    # Further processing of command line arguments
    if args.F :
        args.I = True
        args.D = True
        args.L = True

    return args

def get_target( config, name ):
    """ An inefficient helper function """
    for rec in config["dataset"] :
        if rec["name"] == name :
            return rec
    raise RuntimeError( "Target name not found: " + name )

# Compute checksums of dataset record
#
def get_sha256( config, name ) :
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
            if re.search( r"https?:", path ) : # do not run HEAD on ftp server FIXME: implement something better
               info = get_head_info( path ) # as a side effect: verify is the server is responding
               sha256.update( info.encode('utf-8') )
    if "stamp" in target :
        for link in target["stamp"] :
            path = replace_env_var( link )
            sha256.update( path.encode('utf-8') )
            if( path.startswith( "http" )):
                info = get_head_info( path ) # as a side effect: verify is the server is responding
                sha256.update( info.encode('utf-8') )
            else:  # assume local file
                filenames = sorted( glob.glob( replace_env_var( path )))
                for filename in filenames :
                    with open( replace_env_var( filename ), "rb") as f :
                        for chunk in iter( lambda: f.read(4096), b"") :
                            sha256.update( chunk )
    if "file" in target :
        for path in target["file"] :
            for dir, filename in expand_path( path, config["kgsteward_yaml_directory"], fatal = False ):
                with open( replace_env_var( dir + "/" + filename ), "rb") as f :
                    for chunk in iter( lambda: f.read(4096), b"") :
                        sha256.update( chunk )
    if "zenodo" in target :
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
        for filename in target["update"] :
            # sha256.update( filename.encode('utf-8'))
            with open( replace_env_var( filename )) as f:
                sparql = f.read()
            sha256.update( sparql.encode('utf-8'))
    return sha256.hexdigest()

def update_config( server, config ) :
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
""" )
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
                item["sha256_new"] = get_sha256( config, name )
                if item["sha256_old"] == item["sha256_new"]:
                    item["status"] = "ok"
                elif not item["status"] == "FROZEN":
                    item["status"] = "UPDATE"
        except Exception as e: # test before and remove this typ/excep block 
            stop_error( "Failed parsing server response: " + str( e ))
    for item in config["dataset"] :
        if item["status"] == "ok" and "parent" in item :
            for parent in item["parent"] :
                if name2item[parent]["status"] == "UPDATE" :
                    item["status"] = "PROPAGATE"
    return config

def update_dataset_info( server, config, name ) :
    print_break()
    context = name2context[ name ]
    sha256 = get_sha256( config, name )
    server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX ex:   <http://example.org/>

INSERT {{
    GRAPH <{context}> {{
        <{context}> a void:Dataset ;
            void:triples               ?c   ;
            #void:distinctSubjects      ?cs  ;
            #void:properties            ?cp  ;
            #void:distinctObjects       ?co  ;
            dct:modified               ?now ;
            ex:has_sha256              "{sha256}" .
    }}
}}
WHERE {{
    GRAPH <{context}> {{
        SELECT
            ( COUNT( * ) AS ?c )
            #( COUNT( DISTINCT( ?s )) AS ?cs )
            #( COUNT( DISTINCT( ?p )) AS ?cp )
            #( COUNT( DISTINCT( ?o )) AS ?co )
            ( NOW() AS ?now )
        WHERE {{
            ?s ?p ?o
        }}
    }}
}}
""")

def main():
    """Main function of the kgsteward workflow."""

    args = get_user_input()

    # --------------------------------------------------------- #
    # Load YAML config and complete it
    # --------------------------------------------------------- #

    print_break()
    print_task( "read YAML config" );
    config = parse_yaml_conf( replace_env_var( args.yamlfile[0] ))
    for item in config["dataset"]:
        name2context[ item["name"] ] = item["context"]
        context2name[ item["context"] ] = item["name"]

    # if not "location" in config :
    #    config["location"] = input( "Enter location : " )
    #if "username" in config and not "password" in config :
    #    config["password"] = getpass.getpass( prompt = "Enter password : " )

    # --------------------------------------------------------- #
    # Initalise connection with the right triplestore
    # --------------------------------------------------------- #

    if "username" in config["server"]:
        username = replace_env_var( config["server"]["username"] )
        password = replace_env_var( config["server"]["password"] )
    else:
        username = None
        password = None

    if config["server"]["type"] == "graphdb":
        server = GraphDBClient(
            replace_env_var( config["server"]["location"] ),
            username,
            password,
            replace_env_var( config["server"]["repository"] )
        )
    elif config["server"]["type"] == "rdf4j":
        server = RFD4JClient(
            replace_env_var( config["server"]["location"] ),
            username,
            password,
            replace_env_var( config["server"]["repository"] )
        )
    elif config["server"]["type"] == "fuseki":
        server = FusekiClient(
            replace_env_var( config["server"]["location"] ),
            username,
            password,
            replace_env_var( config["server"]["repository"] )
        )
#    elif config["server"]["type"] == "oxigraph":
#        server = OxigraphClient(
#            replace_env_var( config["server"]["location"] )
#        )
    else:
        stop_error( "Unknown server type: " + config["server"]["type"] )

    for key in config["server"].keys():
        os.environ[ "kgsteward_server_" + str( key )] = str( config["server"][key] )
    os.environ[ "kgsteward_server_endpoint_query"]  = server.get_endpoint_query()
    os.environ[ "kgsteward_server_endpoint_update"] = server.get_endpoint_update()

    # --------------------------------------------------------- #
    # Create a new empty repository or rewrite an existing one
    # --------------------------------------------------------- #

    if args.I :
        if "server_config" in config["server"]:
            config_file = update_path( config["server"]["server_config"], config["kgsteward_yaml_directory"] )
            server.rewrite_repository( config_file )
        else:
             server.rewrite_repository()

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
        config = update_config( server, config ) # may takes a while
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
        os.environ["TARGET_GRAPH_CONTEXT"] = context
        os.environ["kgsteward_dataset_name"]    = name
        os.environ["kgsteward_dataset_context"] = context
        replace = {}

        server.sparql_update( f"DROP SILENT GRAPH <{context}>" )

        if "system" in target :
            for cmd in target["system"] :
                cmd2 = replace_env_var( cmd )
                print( colored( cmd2, "cyan" ))
                exit_code = os.system( cmd2 )
                if not exit_code == 0 :
                    raise stop_error( 'System cmd failed: ' + cmd2 )

        if "url" in target :
            for urlx in target["url"] :
                path = replace_env_var( urlx )
                server.sparql_update( f"LOAD SILENT <{path}> INTO GRAPH <{context}>" )
                server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <{path}>
    }}
}}""" )
        if "file" in target :
            if config["server"]["file_loader"]["type"] == "http_server":
                fs = LocalFileServer( port = config["server"]["file_loader"][ "port" ] )
                for path in target["file"] :
                    for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                        if not os.path.isfile( dir + "/" + fn ):
                            stop_error( "File not found: " + dir + "/" + fn )
                        fs.expose( dir ) # cache already exposed directory
                        if not is_running_in_a_container: 
                            try:
                                path = "http://localhost:" + str( config["server"]["file_loader"][ "port" ] ) + "/" + fn
                                server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>" )
                            except Exception as e:
                                msg = str( e )
                                if msg == "HTTP request failed!":
                                    is_running_in_a_container = True 
                                    print_warn( "Maybe the server is running in a container => let's try again!" )
                                else:
                                    stop_error( msg)
                        if is_running_in_a_container:
                            # see https://stackoverflow.com/questions/68021524/access-localhost-from-docker-container
                            path = "http://host.docker.internal:" + str( config["server"][ "file_server_port" ] ) + "/" + fn
                            server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>" )
                        filename = dir + "/" + fn
                        server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <file://{filename}>
    }}
}}""" )
                fs.terminate()
            else: # config["server"]["file_loader"]["type"] != "http_server"
                for path in target["file"] :
                    for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                        filename = dir + "/" + fn
                        if config["server"]["file_loader"]["type"] == "sparql_load":
                            server.sparql_update( f"LOAD <file://{filename}> INTO GRAPH <{context}>" )
                        elif config["server"]["file_loader"]["type"] == "chunked_store_file":
                            server.load_from_file_using_riot( filename, context )
                        else:
                            raise SystemError( "Unexpected file loader type: " + config["server"]["file_loader"]["type"] )
                        server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <file://{filename}>
    }}
}}""" )

        if "zenodo" in target :
            for id in target["zenodo"]:
                r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
                if not r.status_code == 200 :
                    raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
                info = r.json()
                for record in info["files"]:
                    path = "https://zenodo.org/records/" + str( id ) + "/files/" + record["key"]
                    server.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>" )
                    server.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH <{context}> {{
        <{context}> void:dataDump <{path}>
    }}
}}""" )

        if "replace" in target:
            for key in target["replace"]:
                replace[key] = replace_env_var( target["replace"][key] )

        if "update" in target :
            for filename in target["update"]:
                with open( replace_env_var( filename )) as f:
                    sparql = f.read()
                # if replace is not None:
                for key in sorted( replace.keys()):
                    sparql = sparql.replace( key, replace[ key ])
                server.sparql_update( sparql )

        update_dataset_info( server, config, name )

    # --------------------------------------------------------- #
    # Force update namespace declarations
    # --------------------------------------------------------- #

    if args.P and "prefixes" in config:
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

    if args.V :
        print_break()
        print_task( "Run assert queries to validate repository content " )
        exit_code = 0
        for path in config["validations"] :
            for dir, fn in expand_path( path, config["kgsteward_yaml_directory"] ):
                filename = dir + "/" + fn
                report( 'query file', filename )
                # print( '----------------------------------------------------------')
                with open( filename ) as f: sparql = f.read()
                r = server.sparql_query_to_tsv( sparql, echo = False )
                if r.text.count( "\n" ) == 1 :
                    report( "Result", "Pass ;-)" )
                else:
                    print( colored( sparql, "green" ))
                    print( colored( re.sub( "\n+$","", re.sub( "^[^\n]+\n", "",r.text )), "red" ))
                    report( "Result", "Failed ;-(" )
                    exit_code = 1
        print( '----------------------------------------------------------')
        sys.exit( exit_code )

    # --------------------------------------------------------- #
    # Refresh all GraphDB preloaded queries
    # --------------------------------------------------------- #

    if args.Q:
        r = server.graphdb_call({ 'url' : '/rest/sparql/saved-queries', 'method' : 'GET' })
        for item in r.json() :
            print( f"DELETE: {item['name']}" ) # GraphDB builtin queries cannot be deleted
            server.graphdb_call({
                'url'    : '/rest/sparql/saved-queries',
                'method' : 'DELETE',
                'params' : { 'name': item['name']}
            })
        for path in config["queries"] :
            filenames = sorted( glob.glob( replace_env_var( path )))
            for filename in filenames :
                with open( filename ) as f: sparql = f.read()
                name = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                print( "TEST:   " + name)
                server.validate_sparql_query( sparql, echo=False)
                print( "LOAD:   " + name)
                server.graphdb_call({
                    'url'    : '/rest/sparql/saved-queries',
                    'method'  : 'POST',
                    'headers' : {
                        'Content-Type': 'application/json',
                        'Accept-Encoding': 'identity'
                    },
                    'json'    : { 'name': name, 'body': sparql, "shared": "true" }
                }, [ 201 ] )

    if args.r:
        if not os.path.isdir( args.r ):
            stop_error( "Not a directory: " + args.r )
        counter = 0
        prefix = {}
        catch_key_value_ttl = re.compile( r"@prefix\s+(\S*):\s+<([^>]+)>", re.IGNORECASE )
        catch_key_value_rq  = re.compile( r"PREFIX\s+(\S*):\s+<([^>]+)>",  re.IGNORECASE )
        for path in config["queries"] :
            filenames = sorted( glob.glob( replace_env_var( path )))
            for filename in filenames :
                report( "parse file", filename )
                counter = counter + 1
                comment = []
                select  = []
                name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                with open( filename ) as file:
                    for line in file:
                        if re.match( "^#", line ):
                            comment.append( re.sub( r"^#\s*", "", line.rstrip() ))
                        else:
                            select.append( line.rstrip() )
                            match = catch_key_value_rq.search( line )
                            if match:
                                prefix[match.group( 1 )] = match.group( 2 )
                server.validate_sparql_query( "\n".join( select ), echo=False)
                EX     = Namespace( server.get_endpoint_query() + "/.well-known/sparql-examples/" )
                RDF    = Namespace( "http://www.w3.org/1999/02/22-rdf-syntax-ns#" )
                RDFS   = Namespace( "http://www.w3.org/2000/01/rdf-schema#" )
                SCHEMA = Namespace( "https://schema.org/" )
                SH     = Namespace( "http://www.w3.org/ns/shacl#" )
                SPEX   = Namespace( "https://purl.expasy.org/sparql-examples/ontology#" )
                g = Graph()
                g.bind( "ex",     EX )
                g.bind( "rdfs",   RDFS )
                g.bind( "schema", SCHEMA )
                g.bind( "sh",     SH )
                g.bind( "spex",   SPEX )
                iri = EX["query_" + str( counter )]
                g.add(( iri, RDF.type, SH.SPARQLExecutable ))
                g.add(( iri, RDF.type, SH.SPARQLSelectExecutable ))
                g.add(( iri, RDFS.comment,  Literal( "\n".join( comment ))))
                g.add(( iri, SH.prefixes,   URIRef("http://example.org/prefixes/sparql_examples_prefixes")))
                g.add(( iri, SH.select,     Literal( "\n".join( select ))))
                g.add(( iri, SCHEMA.target, URIRef( server.get_endpoint_query())))
                g.serialize(
                    format="turtle",
                    destination = args.r + "/query" + str( counter ).rjust( 4, "0" ) + ".ttl"
                )
        if "prefixes" in config:
            for filename in config["prefixes"] :
                report( "parse file", filename )
                file = open( replace_env_var( filename ))
                for line in file:
                    match = catch_key_value_ttl.search( line )
                if match:
                    prefix[match.group( 1 )] = match.group( 2 )
        SH     = Namespace( "http://www.w3.org/ns/shacl#" )
        XSD    = Namespace( "http://www.w3.org/2001/XMLSchema#" )
        RDF    = Namespace( "http://www.w3.org/1999/02/22-rdf-syntax-ns#" )
        RDFS   = Namespace( "http://www.w3.org/2000/01/rdf-schema#" )
        OWL    = Namespace( "http://www.w3.org/2002/07/owl#" )
        g = Graph()
        g.bind( "sh",   SH )
        g.bind( "rdf",  RDF )
        g.bind( "rdfs", RDFS )
        g.bind( "owl",  OWL )
        g.add(( URIRef('http://example.org/prefixes/sparql_examples_prefixes' ), RDF.type,     OWL.ontology ))
        g.add(( URIRef('http://example.org/prefixes/sparql_examples_prefixes' ), RDFS.comment, Literal( "toto" )))
        g.add(( URIRef('http://example.org/prefixes/sparql_examples_prefixes' ), OWL.imports,  URIRef( 'http://www.w3.org/ns/shacl#' )))
        for key in prefix:
            g.add(( URIRef('http://example.org/prefixes/sparql_examples_prefixes' ), SH.declare, URIRef( 'http://example.org/prefixes/prefix_' + key )))
            g.add(( URIRef( 'http://example.org/prefixes/prefix_' + key ), SH.prefix,    Literal( key )))
            g.add(( URIRef( 'http://example.org/prefixes/prefix_' + key ), SH.namespace, Literal( prefix[key], datatype=XSD.anyURI )))
        g.serialize(
            format="turtle",
            destination = args.r + "/prefixes.ttl"
        )
        sys.exit( 0 )
        

    if args.x:
        print_break()
        print_task( "Dump all query results in TSV format" )
        if not os.path.isdir( args.x ):
            stop_error( "Not a directory: " + args.x )
        for path in config["queries"] :
            filenames = sorted( glob.glob( replace_env_var( path )))
            for filename in filenames :
                report( "read file", filename )
                name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
                with open( filename ) as file:
                    sparql = file.read()
                r = server.sparql_query_to_tsv( sparql, echo = True )
                s = r.text.splitlines( keepends = True )
                out_path =  args.x + "/" + name + ".tsv"
                report( "write file", out_path )
                with open( out_path, "w" ) as file:
                    file.write( "".join( s[ :1 ] ))
                    file.write( "".join( sorted( s[ 1: ])))
        sys.exit( 0 )

    if args.y:
        print_break()
        print_task( "Dump all contexts in nt format" )
        if not os.path.isdir( args.y ):
            stop_error( "Not a directory: " + args.y )
        for item in config["dataset"] :
            out_path =  args.y + "/" +  item["name"] + ".nt"
            with open( out_path, "w" ) as file:
                r = server.dump_context( item["context"] )
                file.write( r.text )
        sys.exit( 0 )

    # --------------------------------------------------------- #
    # Turn free access ON
    # --------------------------------------------------------- #

    if args.L :
        server.free_access()

    # --------------------------------------------------------- #
    # Print final repository status
    # FIXME: implement target_graph_context rewrite
    # --------------------------------------------------------- #

    config = update_config( server, config )

    contexts = server.get_contexts()
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
