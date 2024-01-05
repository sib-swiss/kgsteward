"""Main kgsteward module."""

# https://confluence.csiro.au/public/VOCAB/vocabulary-services/publishing-vocabularies/best-practice-in-formalizing-a-skos-vocabulary

# https://rdf4j.org/documentation/reference/rest-api/

# About relationship of dcat:Dataset and void:Dataset
# https://lists.w3.org/Archives/Public/public-lod/2017Mar/0014.html

# https://www.w3.org/TR/dwbp/

# https://wimmics.github.io/voidmatic/

# Very useful list of recommendations including vocabulary suggestion and SPARQL example
# https://www.w3.org/TR/hcls-dataset/
# https://eudat.eu/sites/default/files/MichelDumontier.pdf
# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4991880/

# --------------------------------------------------------- #
# Some REST services are not documented in the help pages
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
# --------------------------------------------------------- #

import argparse
import os
import sys
import re
import hashlib
import glob
import yaml
import requests         # https://docs.python-requests.org/en/master/user/quickstart/
import getpass
from   dumper    import dump # just in case to debug

from .graphdb    import GraphDBclient
from .fuseki     import FusekiClient
from .fileserver import LocalFileServer 
from .common     import *

# ---------------------------------------------------------#
# The RDF source graphs configuration
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
        description = "Manage a GraphDB repository using HTTP requests. "
            "This script rely on three environment variables (GRAPHDB_URL, "
            "GRAPHDB_USERNAME, GRAPHDB_PASSWORD) and a YAML config file."
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
        help   = "Load missing/incomplete graphs to complete the repository."
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
        '-Q',
        action = 'store_true',
        help   = "Clean, test and reload all SPARQL queries. This is a GraphDB "
                 "specific option. Note that the queries are global to a web "
                 "site, i.e. they are not attached to a specific repository. "
                 "It may fail on SPARQL syntax error!"
    )
    args = parser.parse_args()

    # Further processing of command line arguments
    if args.F :
        args.I = True
        args.D = True
        args.L = True

    return args


RE_CATCH_ENV_VAR = re.compile( "\\$\\{([^\\}]+)\\}" )
RE_CATCH_FILENAME = re.compile( "([^\\/]+)\\$" )

def replace_env_var( txt ) :
    """ A helper sub with no magic """
    m = RE_CATCH_ENV_VAR.match( txt )
    if m:
        val = os.getenv( m.group( 1 ) )
        if val:
            txt = RE_CATCH_ENV_VAR.sub( val, txt )
            return replace_env_var( txt ) # recursion
        else:
            sys.exit(f"Environment variable not set: {m.group(1)}")
    else:
        return txt

def parse_yaml_config( filename ) :
    """ Recursive parser of config file(s)"""
    print_break()
    print( "# Parse yaml file: " + filename )
    with open( filename, 'r') as f:
        config = yaml.load( f, Loader = yaml.Loader )
    for key in list( config ) :
        if key not in [ "endpoint", "username", "password", "repository_id", "setup_base_IRI", "graphdb_config", "graphs", "queries", "validations" ] :
            print( "Ignored config key in file (" + filename + "): " + key )
            del config[key]
    graphs = list()
    for item in config["graphs"] :
        if( "source" in item ) :
            c = parse_yaml_config( replace_env_var( item["source"] )) # recursion
            for key in list( c ) :
                if key not in [ "graphs" ] :
                    print( "Ignored config key from file (" + filename + "): " + key )
            for graph in c["graphs"] :
                if graph["dataset"] in config["graphs"] :
                    raise RuntimeError( "Duplicated dataset name: " + item["dataset"] )
                graphs.append( graph )
        else:
            if not "dataset" in item :
                raise RuntimeError( "Dataset name is mandatory: " + str( item ))
            graphs.append( item )
    config["graphs"] = graphs
    return config

def get_target( config, name ) :
    """ A stupid helper function """
    for rec in config["graphs"] :
        if rec["dataset"] == name :
            return rec
    raise RuntimeError( "Target dataset not found: " + name )

def get_sha256( config, name ) :
    sha256 = hashlib.sha256()
    target = get_target( config, name )
    context = "<" + config["setup_base_IRI"] + target["dataset"] + ">"
    if "url" in target :
        for urlx in target["url"] :
            path = "<" + replace_env_var( urlx ) + ">"
            sha256.update( path.encode('utf-8') )
    if "file" in target :
        for filename in target["file"] :
            with open( replace_env_var( filename ), "rb") as f :
                for chunk in iter(lambda: f.read(4096), b"") :
                    sha256.update(chunk)
    if "zenodo" in target :
        for id in target["zenodo"]:
            r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
            if not r.status_code == 200 :
                raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
            info = r.json()
            for record in info["files"] :
                sha256.update( record["checksum"].encode('utf-8'))
    if "update" in target :
        for filename in target["update"] :
            with open( replace_env_var( filename )) as f: sparql = f.read()
            sha256.update( sparql.encode('utf-8'))
    return sha256.hexdigest()

def update_config( gdb, config ) :
    """ Add information about the currrent repository status """
    print_break()
    name2dataset = {}
    for dataset in config["graphs"] :
        name = dataset["dataset"]
        name2dataset[name]    = dataset
        dataset["count"]      = ""
        dataset["date"]       = ""
        dataset["sha256_old"] = ""
        dataset["status"]     = "EMPTY"
    r = gdb.sparql_query( """
PREFIX void: <http://rdfs.org/ns/void#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX ex:   <http://example.org/>
SELECT ?g ?x ( REPLACE( STR( ?y ), "\\\\..+", "" ) AS ?t ) ?sha256
WHERE{{
    ?g a void:Dataset   ;
        void:triples  ?x      ;
        dct:modified  ?y      ;
        ex:has_sha256 ?sha256 ;
}}
""" )
    re_catch_name = re.compile( config['setup_base_IRI'] + "(\\w+)" )
    for rec in r.json()["results"]["bindings"] :
        name = re_catch_name.search( rec["g"]["value"] ).group( 1 )
        if not name in name2dataset :
            continue
        dataset = name2dataset[name]
        dataset["count"]      = rec["x"]["value"]
        dataset["date"]       = rec["t"]["value"]
        dataset["sha256_old"] = str( rec["sha256"]["value"] )
        dataset["sha256_new"] = get_sha256( config, name )
        if dataset["sha256_old"] == dataset["sha256_new"] :
            dataset["status"] = "ok"
        else :
            dataset["status"] = "UPDATE"
    buf = set()
    for dataset in config["graphs"] :
        if dataset["status"] != "ok" :
            buf.add( dataset["dataset"] )
            continue
        if "parent" in dataset :
            if dataset["parent"] == "*" and buf :
                if any( name2dataset[name]["status"] != "ok" for name in buf ) :
                    dataset["status"] = "PROPAGATE"
                    buf.add( dataset["dataset"])
            else:
                for parent in dataset["parent"].split( "," ) :
                    if name2dataset[name]["status"] != "ok" :
                        dataset["status"] = "PROPAGATE"
                        buf.add( dataset["dataset"] )
                        break
    return config

def update_dataset_info( gdb, config, name ) :
    print_break()
    context = "<" + config["setup_base_IRI"] + name + ">"
    sha256 = get_sha256( config, name )
    gdb.sparql_update( f"""DELETE
WHERE{{
    GRAPH {context} {{
        {context} ?p ?o
    }}
}}""" )
    gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
PREFIX dct:  <http://purl.org/dc/terms/>
PREFIX ex:   <http://example.org/>
;
INSERT {{
    GRAPH {context} {{
        {context} a void:Dataset ;
            void:triples               ?c   ;
            void:distinctSubjects      ?cs  ;
            void:properties            ?cp  ;
            void:distinctObjects       ?co  ;
            dct:modified               ?now ;
            ex:has_sha256              "{sha256}" .
    }}
}}
USING {context}
WHERE {{
    SELECT
        ( COUNT( * ) AS ?c )
        ( COUNT( DISTINCT( ?s )) AS ?cs )
        ( COUNT( DISTINCT( ?p )) AS ?cp )
        ( COUNT( DISTINCT( ?o )) AS ?co )
        ( NOW() AS ?now )
    WHERE {{
        ?s ?p ?o
    }}
}}
""")

def main():
    """Main function of the kgsteward workflow."""

    args = get_user_input()


    # --------------------------------------------------------- #
    # Load YAML config and complete it
    # --------------------------------------------------------- #

    config = parse_yaml_config( replace_env_var( args.yamlfile[0] ))
    print()
    if not "endpoint" in config :
        config["endpoint"] = input( "Enter endpoint : " )
    if not "username" in config :
        config["username"] = input( "Enter username : " )
    if not "password" in config :
        config["password"] = getpass.getpass( prompt = "Enter password : " )

    # --------------------------------------------------------- #
    # Test if GraphDB is running and set it in write mode
    # --------------------------------------------------------- #

    gdb = GraphDBclient( 
        # FusekiClient(
        replace_env_var( config["endpoint"] ),
        replace_env_var( config["username"] ),
        replace_env_var( config["password"] ),
        replace_env_var( config["repository_id"] )
    )

    # --------------------------------------------------------- #
    # Create a new empty repository
    # turn autocomplete ON
    # turn free-access ON if required
    # --------------------------------------------------------- #

    if args.I :
        gdb.rewrite_repository( replace_env_var( config['graphdb_config'] ))

    # --------------------------------------------------------- #
    # Establish the list of contexts/graphs to update
    # --------------------------------------------------------- #

    rdf_graph_all = set()
    rdf_graph_to_update = set()
    for target in config["graphs"] :
        rdf_graph_all.add( target["dataset"] )

    if args.D :
        rdf_graph_to_update = rdf_graph_all
    elif args.d :
        for name in args.d.split( "," ) :
            if name in rdf_graph_all :
                rdf_graph_to_update.add( name )
            else :
                raise RuntimeError( "Invalid dataset name: " + name )
    elif args.C :
        config = update_config( gdb, config ) # takes a while
        for name in rdf_graph_all :
            target = get_target( config, name )
            if target["status"] in { "EMPTY", "UPDATE", "PROPAGATE" } :
                rdf_graph_to_update.add( name )

    # --------------------------------------------------------- #
    # Drop previous data, upload new data in their respective
    # graphs, update void stats.
    # --------------------------------------------------------- #

    for target in config["graphs"] :

        name = target["dataset"]
        if not name in rdf_graph_to_update :
            continue

        print_break()
        graph_IRI = config["setup_base_IRI"] + name
        gdb.sparql_update( f"DROP GRAPH <{graph_IRI}>", [ 204, 404 ] )
        context = "<" + config["setup_base_IRI"] + name + ">"

        if "url" in target :
            for urlx in target["url"] :
                print_break()
                path = "<" + replace_env_var( urlx ) + ">"
                gdb.sparql_update( f"LOAD {path} INTO GRAPH {context}" )
                gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH {context} {{
        {context} void:dataDump {path}
    }}
}}""" )

        if "file" in target :
            use_file_server = True
            if use_file_server :
                fs = LocalFileServer()
                for filename in target["file"] :
                    print_break()
                    dir, file = os.path.split( replace_env_var( filename ) )
                    fs.expose( dir )
                    path = "http://localhost:8000/" + file
                    gdb.sparql_update( f"LOAD <{path}> INTO GRAPH {context}" )
                    path = "file://" + replace_env_var( filename )
                    gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH {context} {{
        {context} void:dataDump <{path}>
    }}
}}""" )
                fs.terminate()
            else:
                for filename in target["file"] :
                    print_break()
                    path = "file://" + replace_env_var( filename )
                    gdb.sparql_update( f"LOAD <{path}> INTO GRAPH {context}" )
                    gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH {context} {{
        {context} void:dataDump <{path}>
    }}
}}""" )
        if "zenodo" in target :
            for id in target["zenodo"]:
                r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
                if not r.status_code == 200 :
                    raise RuntimeError( 'GET failed: ' + "https://zenodo.org/api/records/" + str( id ))
                info = r.json()
                for record in info["files"] :
                    print_break()
                    path = "<https://zenodo.org/records/" + str( id ) + "/files/" + record["key"] + ">"
                    gdb.sparql_update( f"LOAD {path} INTO GRAPH {context}" )
                    gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
INSERT DATA {{
    GRAPH {context} {{
        {context} void:dataDump {path}
    }}
}}""" )

        if "update" in target :
            for filename in target["update"] :
                print_break()
                with open( replace_env_var( filename )) as f: sparql = f.read()
                gdb.sparql_update( sparql )

        update_dataset_info( gdb, config, name )

    # --------------------------------------------------------- #
    # Force update dataset info
    # --------------------------------------------------------- #

    if args.U :
        for target in config["graphs"] :
            update_dataset_info( target )

    # --------------------------------------------------------- #
    # Run all validation tests
    # --------------------------------------------------------- #

    if args.V :
        for path in config["validations"] :
            filenames = glob.glob( replace_env_var( path ))
            for filename in filenames :
                print( '----------------------------------------------------------')
                print( filename )
                with open( filename ) as f: sparql = f.read()
                r = gdb.sparql_query_to_tsv( sparql, echo = False )
                if r.text.count( "\n" ) == 1 :
                    print( "---- Pass ;-) ----")
                else:
                    print( re.sub( "\n+$","", re.sub( "^[^\n]+\n", "",r.text )))
        print( '----------------------------------------------------------')
        sys.exit( 0 )

    # --------------------------------------------------------- #
    # Refresh all GraphDB preloaded queries
    # --------------------------------------------------------- #

    if args.Q:
        r = gdb.graphdb_call({ 'url' : '/rest/sparql/saved-queries', 'method' : 'GET' })
        for item in r.json() :
            print( f"DELETE: {item['name']}" ) # GraphDB builtin queries cannot be deleted
            gdb.graphdb_call({
                'url'    : '/rest/sparql/saved-queries',
                'method' : 'DELETE',
                'params' : { 'name': item['name']}
            })
        for path in config["queries"] :
            filenames = glob.glob( replace_env_var( path ))
            for filename in filenames :
                with open( filename ) as f: sparql = f.read()
                name = re.sub( '(.*\/|)([^\/]+)\.\w+$', r'\2', filename )
                print( "TEST:   " + name)
                gdb.validate_sparql_query( sparql, echo=False)
                print( "LOAD:   " + name)
                gdb.graphdb_call({
                    'url'    : '/rest/sparql/saved-queries',
                    'method'  : 'POST',
                    'headers' : {
                        'Content-Type': 'application/json',
                        'Accept-Encoding': 'identity'
                    },
                    'json'    : { 'name': name, 'body': sparql, "shared": "true" }
                }, [ 201 ] )

    # --------------------------------------------------------- #
    # Turn free access ON
    # --------------------------------------------------------- #

    if args.L :
        gdb.free_access()

    # --------------------------------------------------------- #
    # Print final repository status
    # --------------------------------------------------------- #

    config = update_config( gdb, config )
    r = gdb.get_context_list()
    context = set()
    re_catch_name = re.compile( config['setup_base_IRI'] + "(\\w+)" )
    for rec in r.json()["results"]["bindings"] :
        name = re_catch_name.search( rec["contextID"]["value"] ).group( 1 )
        context.add( name ) # FIXME

    print( '-------------------------------------------------------------------')
    print( '       graph/context        #triple     last modified       status')
    print( '-------------------------------------------------------------------')
    for dataset in config["graphs"] :
        print('{:>20} : {:>12}    {:>20} {}'.format( dataset["dataset"], dataset["count"], dataset["date"], dataset["status"] ))
        if dataset["dataset"] in context :
            context.remove( dataset["dataset"] )
    for name in context:
        print('{:>20} : {:>12}    {:>20} {}'.format( name, "", "", "UNKNOWN" ))
    print( '-------------------------------------------------------------------')

# --------------------------------------------------------- #
# Main
# --------------------------------------------------------- #

if __name__ == "__main__":
    main()
