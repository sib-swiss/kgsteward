#https://stackoverflow.com/questions/58703926/how-do-i-generate-yaml-containing-local-tags-with-ruamel-yaml$
from dumper    import dump
from enum      import Enum
from json      import dumps
from typing    import List, Dict, Optional, Union
from pprintpp import pformat
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str
from .common import *

description = {
    "server_brand": """One of 'graphdb' or 'fuseki' ( 'graphdb' by default).""",
    "server_url" :   """URL of the server. The SPARL endpoint is different and server specific.""" ,
    "repository_id": """The name of the repository (graphdb) or dataset (fuseki) in the triplestore.""",
    "username":      """The name of a user with write-access rights in the triplestore.""",
    "password":      """The password of a user with write-access rights to the triplestore. 
It is recommended that the value of this variable is passed trough an environment variable. 
By this way the password is not stored explicitely in the config file.
Alternatively `?` can be used and the password will be asked interactively at run time.""",
    "context_base_IRI": """Base IRI to construct the graph context. 
    Default value: http://example.org/context/
""",
    "use_file_server": """Boolean, `False` by default. 
When set to `True`: local files will be exposed through a temporary HTTP server and loaded from it. 
Support for different RDF file types and their compressed version depend on the triplstore. 
The benefit is the that RDF data from `file`are processed with the same protocol as those supplied through `url`. 
Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. 
Beware that the used python-based server is potentially insecure
(see [here](https://docs.python.org/3/library/http.server.html) for details). 
This should however pose no real treat if used on a personal computer or on a server that is behind a firewall.
""",
    "file_server_port": "Optional integer, default to 8000.",
    "server_config":  """Filename with the triplestore configuration, possibly a turtle file. 
`graphdb_config` is a deprecated synonym. 
This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively, 
thus permitting to reproduce the repository configuration elsewhere. 
This file is used by the `-I` and `-F` options. 
Beware that the repository ID could be hard-coded in the config file and 
should be maintained in sync with `repository_id`.
""",
    "graphs": "Mandatory key to specify the overall knowledge graph content",
    "queries": """A list of paths to files with SPARQL queries to be add to the repository user interface.
Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint, 
with a short timeout.
The query result is not iteself checked. 
Wild card can be supplied in the path.
""",
    "validations": """A list of path(s) to SPARQL queries used to validate the repsository.
By convention, a valid result should be empty, no row is returned. 
Failed results should return rows permitting to diagnose the problems.
Wild card `*` can be supplied in the path.
""",
    "dataset": """Mandatory name of a graphs record.""",
    "context": """IRI for 'context' in RDF4J/GraphDB terminology, or IRI for 'named graph' in RDF/SPARQL terminology. 
If missing, contect IRI will be built by concataining `context_base_IRI` and `dataset`
""",
"system": """A list of system command. 
This is a simple convenience provided by kgsteward which is not meant to be a replacement 
for serious Make-like system as for example git/dvc.
""",
"file": """Optional list of files containing RDF data. 
Wild card "*" can be used.
The strategy used to load these files will depends on the `use_file_server` Boolean value. 
With GraphDB, if `use_file_server` is `false` there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. With `use_file_server` set to `true` these limitations are overcomed, but see the security warning described above. 
""",
"url": """Optional list of url from which to load RDF data""",
"zenodo": """Do not use!
Fetch turtle files from zenodo. 
This is a completely ad hoc command developped for ENPKG (), that will be suppressed sooner or later
""",
"update": """Optional list files containing SPARQL update commands. 
Wild card `*` can be supplied in the path.
""",
"source": """Path to another kgsteward YAML file from which the graphs list of record will be extracted 
and inserted in the current graphs list.
""",
    "parent": """A list of name to encode dependency between datasets. 
Updating the parent datset will provoke the update of its children.
""",
    "stamp": """Optional list of paths to files which last modification dates will used.
The file contents are ignored.
Wild card "*" can be used.
""",
    "replace": """Optional dictionary to perform string substitution in SPARQL queries from `update` list.
Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context.
"""
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
    dataset     : str = Field( 
        title = "Short name of a graphs reccord",
        description = description[ "dataset" ],
        pattern = r"[a-zA-Z]\w{0,31}"
    )
    parent   : Optional[ List[ str ]] = Field(
        None,
        title = "Parent(s) of a graphs record",
        description = description[ "parent" ]
    )
    context  : Optional[ str ]        = Field( 
        None,
        title = "Full IRI of a context/named graph",
        description = description[ "context" ]
    )
    system   : Optional[ List[ str ]] = Field( 
        None,
        title = "UNIX system command(s)",
        description = description[ "system" ]
    )
    file     : Optional[ list[ str ]] = Field( 
        None,
        title = "Load RDF from file(s)",
        description = description[ "file" ],
    )
    url      : Optional[ list[ str ]] = Field( 
        None,
        title = "Load RDF from URL(s)",
        description = description[ "url" ]
    )
    stamp    : Optional[ list[ str ]] = Field( 
        None,
        title = "Stamp file(s)",
        description = description[ "stamp" ]
    )
    replace  : Optional[ list[ dict [ str, str ]]] = Field( 
        None,
        title = "String subtitution in SPARQL update(s)",
        description = description[ "replace" ]
    )
    update   : Optional[ list[ str ]] = Field( 
        None,
        title = "SPARQL update file(s)",
        description = description[ "update" ]
    )
    zenodo   : Optional[ list[ int ]] = Field( 
        None,
        title = "Ignore me",
        description = description[ "zenodo" ]
    )

class ServerEnum( str, Enum ):
    graphdb  = 'graphdb'
    fuseki   = 'fuseki'
    # virtuoso = 'virtuoso'

class KGStewardConf( BaseModel ):
    # description  = "This is main description"
    model_config = ConfigDict( extra='allow' )
    server_brand      : str = Field( 
        ServerEnum.graphdb, 
        title = "Server brand",
        description = description["server_brand"]
    )
    server_url        : str = Field( 
        default = "http://localhost:7200",
        title       = "Server URL",
        description = description["server_url"],
    )
#    endpoint_url      : Optional[ str ] = Field( None, id = "deprecated and replaced by 'server_url'" )
#    server_config     : Optional[ str ] = None # SingleFileName()
#    endpoint          : Optional[ str ] = Field(
#        None,
#        title       = "Server URL",
#        description = "endpoint is deprecated, use server_url",
#    )
    repository_id     : str= Field(
        pattern = r"\w+",
        title = "Repository ID",
        description = description[ "repository_id" ]
    )
    context_base_IRI  : str = "http://example.org/context/"
    dataset_graph_IRI : str = Field( None, title="deprecated and replaced by 'context_base_IRI'" )
    setup_graph_IRI   : str = Field( None, title="deprecated and replaced by 'context_base_IRI'" )
    username          : Optional[ str ] = None
    password          : Optional[ str ] = None
    file_server_port  : Optional[ int ]  = 8000
    use_file_server   : Optional[ bool ] = False 
    graphs            : list[ Union[ GraphConf, dict [ str, str ]]] 
    prefixes          : list[str]  = None
    queries           : list[str]  = None # MultipleFileName()
    validations       : list[str]  = None # MultipleFileName()

def parse_yaml_conf( path : str ):
    file = open( path )
    try:
        config = parse_yaml_raw_as( KGStewardConf, file.read() ).model_dump( exclude_none = True )
    except ValidationError as e:
        stop_error( "YAML syntax error in file " + path + ":\n" + pformat( e.errors() ))
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

    if "username" in config and not "password" in config :
        config["password"] = getpass.getpass( prompt = "Enter password : " )

    graphs = list()
    for item in config["graphs"] :
        if "source" in item:
            try:
                file = open( replace_env_var( item["source"] ))
                conf = parse_yaml_raw_as( KGStewardConf, file.read()).model_dump( exclude_none = True )
            except ValidationError as e:
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
        if "parent" in item:
            if isinstance( item["parent"] , str ):
                if not item["parent"] == "*":
                    stop_error( 'Only "*" is valid to designate all parents: ' + item["parent"] )
                item["parent"] = seen.copy()
            elif isinstance( item["parent"] , list ):
                for parent in item["parent"]:
                    if not parent in seen:
                        stop_error( "Parent not previously defined: " + parent )
        seen.append( item["dataset"] )
        if "context" not in item:
            item["context"] = str( config["context_base_IRI"] ) + str( item["dataset"] )
        graphs.append( item )
    config["graphs"] = graphs
    # dump( config )
    # stop_error( "toto" )
    return config 

def save_json_schema( path ):
    schema = KGStewardConf.model_json_schema()
    schema["description"] = "This is main description"
    with open( path, "w" ) as f:
        f.write( dumps( schema, indent=2 ))

# c1 = parse_yaml_conf( "/Users/mpagni/gitlab.com/ReconXKG/reconxkg.yaml" )
# print( c1 )

# main_model_schema = KGStewardConf.model_json_schema()  # (1)!
# print(json.dumps(main_model_schema, indent=2))  # (2)!

# for graph in c1.graphs:
#     print(graph.dataset)

#c2 = parse_yaml_conf( "/Users/mpagni/gitlab.sib.swiss/sinergiawolfender/common/data/config/jlw.yaml" )
#print( c2 )
