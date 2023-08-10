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

import yaml
import requests # https://docs.python-requests.org/en/master/user/quickstart/
from dumper import dump
from SPARQLWrapper import SPARQLWrapper2
from array import *

from .graphdb import GraphDBclient

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

def replace_env_var(txt):
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


def main():
    """Main function of the kgsteward workflow."""
    args = get_user_input()

    # ---------------------------------------------------------#
    # Read environment variables
    # FIXME: remove SINERGIA
    # ---------------------------------------------------------#
    GRAPHDB_URL = os.getenv("GRAPHDB_URL")
    if not GRAPHDB_URL:
        sys.exit("Environment variable GRAPHDB_URL is not set!")
    GRAPHDB_USERNAME = os.getenv("GRAPHDB_USERNAME")
    if not GRAPHDB_USERNAME:
        sys.exit("Environment variable GRAPHDB_USERNAME is not set!")
    GRAPHDB_PASSWORD = os.getenv("GRAPHDB_PASSWORD")
    if not GRAPHDB_PASSWORD:
        sys.exit("Environment variable GRAPHDB_PASSWORD is not set!")


    # --------------------------------------------------------- #
    # Load YAML config
    # --------------------------------------------------------- #


    with open( args.yamlfile[0], 'r') as f:
        config = yaml.load( f, Loader=yaml.Loader )

    REPOSITORY_ID = config['repository_id']

    rdf_graph_all = set()
    for target in config["graphs"] :
        rdf_graph_all.add( target["dataset"] )

    # --------------------------------------------------------- #
    # Test if GraphDB is running and set it in write mode
    # --------------------------------------------------------- #

    gdb = GraphDBclient( GRAPHDB_URL, GRAPHDB_USERNAME, GRAPHDB_PASSWORD, REPOSITORY_ID )

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

    rdf_graph_ok = set()
    re_catch_name = re.compile( config['setup_base_IRI'] + "(\\w+)" )

    if args.D :
        rdf_graph_ok = rdf_graph_all
    elif args.d :
        for name in args.d.split( "," ) :
            if name in rdf_graph_all :
                rdf_graph_ok.add( name )
            else :
                sys.exit( "Invalid name: " + name )
    if args.C :
        if not rdf_graph_ok :
            rdf_graph_ok = rdf_graph_all.copy()
        r = gdb.sparql_query( """PREFIX void: <http://rdfs.org/ns/void#>
    SELECT ?g ?x
    WHERE{
        ?g a void:Dataset ; void:triples ?x
    }""" )
        for info in r.json()["results"]["bindings"] :
            nam = re_catch_name.search( info["g"]["value"] ).group( 1 )
            if nam in rdf_graph_ok :
                rdf_graph_ok.remove( nam )

    buf = set()
    for target in config["graphs"] :
        if target["dataset"] in rdf_graph_ok :
            buf.add( target["dataset"] )
        if "parent" in target :
            if target["parent"] == "*" and buf :
                rdf_graph_ok.add( target["dataset"] )
                buf.add( target["dataset"] )
            else:
                for name in target["parent"].split( "," ) :
                    if name in buf :
                        rdf_graph_ok.add( target["dataset"] )
                        buf.add( target["dataset"] )

    # --------------------------------------------------------- #
    # Compute checksum of a target graph/context
    # --------------------------------------------------------- #

    def get_sha256( target ) :
        sha256 = hashlib.sha256()
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
                info = r.json()
                for record in info["files"] :
                    sha256.update( record["checksum"].encode('utf-8'))
        if "update" in target :
            for filename in target["update"] :
                with open( replace_env_var( filename )) as f: sparql = f.read()
                sha256.update( sparql.encode('utf-8') )
        return sha256.hexdigest()

    def update_dataset_info( target ) :
        context = "<" + config["setup_base_IRI"] + target["dataset"] + ">"
        sha256 = get_sha256( target )
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

    # --------------------------------------------------------- #
    # Drop target graphs
    # --------------------------------------------------------- #

    for target in config["graphs"] :
        if target["dataset"] in rdf_graph_ok :
            graph_IRI = config["setup_base_IRI"] + target["dataset"]
            gdb.sparql_update( f"DROP GRAPH <{graph_IRI}>", [ 204, 404 ] )

    # --------------------------------------------------------- #
    # Upload data in their respective graphs, update void stats
    # --------------------------------------------------------- #

    for target in config["graphs"] :
        if not target["dataset"] in rdf_graph_ok :
            continue
        context = "<" + config["setup_base_IRI"] + target["dataset"] + ">"

        if "url" in target :
            for urlx in target["url"] :
                path = "<" + replace_env_var( urlx ) + ">"
                gdb.sparql_update( f"LOAD {path} INTO GRAPH {context}" )
                gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
    INSERT DATA {{
        GRAPH {context} {{
            {context} void:dataDump {path}
        }}
    }}""" )

        if "file" in target :
            for filename in target["file"] :
                path = "<file://" + replace_env_var( filename ) + ">"
                gdb.sparql_update( f"LOAD {path} INTO GRAPH {context}" )
                gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
    INSERT DATA {{
        GRAPH {context} {{
            {context} void:dataDump {path}
        }}
    }}""" )

        if "zenodo" in target :
            for id in target["zenodo"]:
                r = requests.request( 'GET', "https://zenodo.org/api/records/" + str( id ))
                info = r.json()
                for record in info["files"] :
                    path = "<https://zenodo.org/record/" + str( id ) + "/files/" + record["key"] + ">"
                    gdb.sparql_update( f"LOAD {path} INTO GRAPH {context}" )
                    gdb.sparql_update( f"""PREFIX void: <http://rdfs.org/ns/void#>
    INSERT DATA {{
        GRAPH {context} {{
            {context} void:dataDump {path}
        }}
    }}""" )

        if "update" in target :
            for filename in target["update"] :
                with open( replace_env_var( filename )) as f: sparql = f.read()
                gdb.sparql_update( sparql )

        update_dataset_info( target )

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
        for filename in config["validations"] :
            print( '----------------------------------------------------------')
            print( filename )
            with open( replace_env_var( filename )) as f: sparql = f.read()
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
        for filename in config["queries"] :
            with open( replace_env_var( filename )) as f: sparql = f.read()
            name = re.sub( '(.*\/|)([^\/]+)\.\w+$', r'\2', filename )
            print( "TEST:   " + name)
            gdb.validate_sparql_query( sparql, echo=False)
            print( "LOAD:   " + name)
            gdb.graphdb_call({
                'url'    : '/rest/sparql/saved-queries',
                'method'  : 'POST',
                'headers' : { 'Content-Type': 'application/json' },
                'json'    : { 'name': name, 'body': sparql, "shared": "true" }
            }, [ 201 ] )

    # --------------------------------------------------------- #
    # Turn free access ON
    # --------------------------------------------------------- #

    if args.L :
        gdb.free_access()

    # --------------------------------------------------------- #
    # Print current DB status
    # --------------------------------------------------------- #

    r = gdb.sparql_query( """
    PREFIX void: <http://rdfs.org/ns/void#>
    PREFIX dct:  <http://purl.org/dc/terms/>
    PREFIX ex:   <http://example.org/>
    SELECT ?g ?x ( REPLACE( STR( ?y ), "\\\\..+", "" ) AS ?t ) ?sha256
    WHERE{{
        ?g a void:Dataset ; void:triples ?x
        OPTIONAL{{ ?g dct:modified ?y }}
        OPTIONAL{{ ?g ex:has_sha256 ?sha256 }}
    }}
    """ ) # FIXME: remove OPTIONAL sooner or later
    re_catch_name = re.compile( config['setup_base_IRI'] + "(\\w+)" )
    count  = {}
    date   = {}
    sha256 = {}
    for info in r.json()["results"]["bindings"] :
        nam = re_catch_name.search( info["g"]["value"] ).group( 1 )
        count[nam] = info["x"]["value"]
        if "t" in info :
            date[nam] = info["t"]["value"]
        else :
            date[nam] = ""
        if "sha256" in info :
            sha256[nam] = str( info["sha256"]["value"] )
        else :
            sha256[nam] = ""

    print( '----------------------------------------------------------')
    print( '       graph/context        #triple    last modified  ')
    print( '----------------------------------------------------------')
    for target in config["graphs"] :
        sha256current = get_sha256( target )
        if target["dataset"] in count :
            status = "update available" if sha256current != sha256[target["dataset"]] else ''
            print('{:>20} : {:>12}    {} {}'.format( target["dataset"], count[target["dataset"]], date[target["dataset"]], status ))
            del count[target["dataset"]]
        else :
            print( '{:>20} : {:>12}'.format( target["dataset"], "na" ))
    for name in sorted( count ) :
        print( '{:>20} : {:>12}'.format( name, "???" ))
    print( '----------------------------------------------------------')


if __name__ == "__main__":
    main()
