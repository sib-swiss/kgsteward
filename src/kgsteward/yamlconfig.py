#https://stackoverflow.com/questions/58703926/how-do-i-generate-yaml-containing-local-tags-with-ruamel-yaml$
from dumper    import dump
from enum      import Enum
from typing    import Optional, Union
from pprintpp import pformat
from pydantic import BaseModel, Field, ValidationError
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str
from .common import *

description = {
    "server_url" : """
    URL of the server. The SPARL endpoint is different and server specific.
""" ,
}

# class SingleFileName( Field ):
#     title = "A file name",
#     description = "A single file name, possibly using written using environment variable ${...} "

# class MultipleFileName( Field ):
#     title = "File name with wildcards",
#     description = "A single file name, possibly containing with wildcards '*'"

#MultipleFileName = Field(
#    None,
#    description = "A single file name, possibly containing with wildcards '*'"
#)
##    title = "File name with wildcards",

class GraphConf ( BaseModel ):
    dataset  : str
    parent   : Optional[ Union[ str, list[ str ]]] = None
    context  : Optional[ str ]        = None
    system   : Optional[ list[ str ]] = None
    file     : Optional[ list[ str ]] = None
    url      : Optional[ list[ str ]] = None
    stamp    : Optional[ list[ str ]] = None # SingleFileName()
    replace  : Optional[ list[ dict [ str, str ]]] = None
    update   : Optional[ list[ str ]] = None # MultipleFileName()
    zenodo   : Optional[ list[ int ]] = None

class ServerEnum( str, Enum ):
    graphdb = 'graphdb'
    fuseki   = 'fuseki'
    virtuoso = 'virtuoso'

class KGStewardConf( BaseModel ):
    server_brand      : str = ServerEnum.graphdb
    server_url        : str = Field( 
        "http://localhost:7200",
        title = "Server URL",
        description = description["server_url"],
        alias = "endpoint_url"
    )
    server_config     : Optional[ str ] = None # SingleFileName()
    endpoint          : Optional[ str ] = Field(
        None,
        title       = "Server URL",
        description = "endpoint is deprecated, use server_url",
    )
    repository_id     : str = None
    context_base_IRI  : str = "http://example.org/context/"
    dataset_graph_IRI : str = Field( None, title="Deprecated, replaced by 'context_base_IRI'" )
    setup_graph_IRI   : str = Field( None, title="Deprecated, replaced by 'context_base_IRI'" )
    
    username          : str = None
    password          : str = None
    file_serve_port   : Optional[ int ]  = 8000
    use_file_server   : Optional[ bool ] = False 
    graphs            : list[ Union[ GraphConf, dict [ str, str ]]] 
    prefixes          : list[str]  = None
    queries           : list[str]  = None # MultipleFileName()
    validations       : list[str]  = None # MultipleFileName()

def parse_yaml_conf( path : str ):
    file = open( path )
    try:
        config = parse_yaml_raw_as( KGStewardConf, file.read()).model_dump()
    except ValidationError as e:
        stop_error( "YAML syntax error in file " + path + ":\n" + pformat( e.errors() ))
    for key in list( config ):
        if not config[key]:
            del config[key]
            continue
    # if key not in [ "server_url", "endpoint", "username", "password", "repository_id", 
    #                     "setup_base_IRI", "context_base_IRI", "server_config", "graphdb_config", 
    #                     "use_file_server", "file_server_port", "graphs", "queries", "validations", 
    #                     "prefixes" ] :
    #     print_warn( "Ignored config key in YAML: " + key ) # FIXME: the above parser remove ignored key
    #     del config[key]
    if "endpoint" in config and "server_url" not in config :
        config[ "server_url" ] = config[ "endpoint" ]
        del config[ "endpoint" ]
        print_warn( '"endpoint" is deprecated, use "server_url" instead' )
    if "setup_base_IRI" in config and "context_base_IRI" not in config :
        config[ "context_base_IRI" ] = config[ "setup_base_IRI" ]
        del config[ "setup_base_IRI" ]
        print_warn( '"setup_base_IRI" is deprecated, use "context_base_IRI" instead' )
    if "dataset_base_IRI" in config and "context_base_IRI"  not in config :
        config[ "context_base_IRI" ] = config[ "dataset_base_IRI" ]
        del config[ "dataset_base_IRI" ]
        print_warn( '"dataset_base_IRI" is deprecated, use "context_base_IRI" instead' )
    if "graphdb_config" in config and "server_config" not in config :
        config[ "server_config" ] = config[ "graphdb_config" ]
        del config[ "graphdb_config" ]
        print_warn( '"graphdb_config" is deprecated, use "server_config" instead' )
    graphs = list()
    for item in config["graphs"] :
        if "source" in item:
            try:
                file = open( replace_env_var( item["source"] ))
                conf = parse_yaml_raw_as( KGStewardConf, file.read()).model_dump()
            except ValidationError as e:
                dump( e.errors() )
                stop_error( "YAML syntax error in file " + path + ":\n" + pformat( e.errors() ))
            graphs.extend( conf["graphs"] )
        else:
            graphs.append( item )
    config["graphs"] = graphs
    # verify structure, complete context
    graphs = list()
    seen   = []    
    for item in config["graphs"] :
        if item["dataset"] in seen:
            stop_error( "Duplicated dataset name: " +  item["dataset"] )
        if isinstance( item["parent"] , str ):
            if not item["parent"] == "*":
                stop_error( 'Only "*" is valid to designate all parents: ' + item["parent"] )
            item["parent"] = seen
        elif isinstance( item["parent"] , list ):
            for parent in item["parent"]:
                if not parent in seen:
                    print( seen )
                    stop_error( "Parent not previously defined: " + parent )
        if item["context"] is None:
            item["context"] = config["context_base_IRI"] + item["dataset"]
        seen.append( item["dataset"] )
        newitem = {}
        for key in list( item ):
            if not item[key]:
                del item[key]
        graphs.append( item )
    config["graphs"] = graphs
    return config 

# c1 = parse_yaml_conf( "/Users/mpagni/gitlab.com/ReconXKG/reconxkg.yaml" )
# print( c1 )

# main_model_schema = KGStewardConf.model_json_schema()  # (1)!
# print(json.dumps(main_model_schema, indent=2))  # (2)!

# for graph in c1.graphs:
#     print(graph.dataset)

#c2 = parse_yaml_conf( "/Users/mpagni/gitlab.sib.swiss/sinergiawolfender/common/data/config/jlw.yaml" )
#print( c2 )
