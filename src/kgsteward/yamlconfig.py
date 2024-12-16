# https://stackoverflow.com/questions/58703926/how-do-i-generate-yaml-containing-local-tags-with-ruamel-yaml$
# https://app.soos.io/research/packages/Python/-/pydantic-yaml-parser/

import yaml
import yaml_include
from dumper        import dump
from enum          import Enum
from typing        import List, Dict, Optional, Union, Literal
from pprintpp      import pformat
from pydantic      import BaseModel, Field, ValidationError, ConfigDict
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str
import json
from .common       import *

description = {
    "schema": """
    Configuration file follows YAML syntax. 
    UNIX environmenent variables can be accessed anywhere in the YAML config through the `${<env-var>}` syntax. 
    The use of UNIX environment variables permits the portability of kgsteward config file, as local path are supplied through variables. 
    For security reason, kgsteward checks that every used variable exitsts and is not an empty string. 
    In addition, to the environment variables available at statup of kgsteward, a certain number of variables are defined at run-time:  
    `${}`, `${}` and `${}`.
    Especially useful is `${graphs.name}` that can be used in be used in `graphs.replace` clause to indicate the current "active" context/named graph.
""",
    "server_brand": """One of 'graphdb' or 'fuseki' ( 'graphdb' by default).""",
    "location" :   """URL of the server. The SPARL endpoint is different and server specific.""" ,
    "repository": """The name of the 'repository' (GraphDB naming) or 'dataset' (fuseki) in the triplestore.""",
    "username":      """The name of a user with write-access rights in the triplestore.""",
    "password":      """The password of a user with write-access rights to the triplestore. 
It is recommended that the value of this variable is passed trough an environment variable. 
By this way the password is not stored explicitely in the config file.
Alternatively `?` can be used and the password will be asked interactively at run time.""",
    "context_base_IRI": """Base IRI to construct the graph context. 
    Default value: http://example.org/context/
""",
    "file_server_port": """Integer, `0` by default, i.e. the file server is turned off. 
When set to a positive integer, say `8000`, local files will be exposed through a temporary 
HTTP server and loaded from it. Support for different RDF file types and their compressed 
version depend on the tripelstore. The benefit is the that RDF data from `file` are processed 
with the same protocol as those supplied remotely through `url`. Essentially for GraphDB, 
file-size limits are suppressed and compressed formats are supported. 
Beware that the used python-based server is potentially insecure
(see [here](https://docs.python.org/3/library/http.server.html) for details). 
This should however pose no real treat if used on a personal computer or on a server that is behind a firewall.
""",
    "server_config":  """Filename with the triplestore configuration, possibly a turtle file. 
`graphdb_config` is a deprecated synonym. 
This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively, 
thus permitting to reproduce the repository configuration elsewhere. 
This file is used by the `-I` and `-F` options. 
Beware that the repository ID could be hard-coded in the config file and 
should be maintained in sync with `repository`.
""",
    "graphs": "Mandatory key to specify the content of the knowledge graph in the triplestore",
    "queries": """A list of paths to files with SPARQL queries to be add to the repository user interface.
Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint, 
with a short timeout.
The query result is not iteself checked. 
Wildcard `*` can be used.
""",
    "validations": """A list of paths to files contining SPARQL queries used to validate the repsository.
Wildcard `*` can be used.
By convention, a valid result should be empty, i.e. no row is returned. 
Failed results should return rows permitting to diagnose the problems.
""",
    "name": """Mandatory name of a graphs record.""",
    "context": """IRI for 'context' in RDF4J/GraphDB terminology, or IRI for 'named graph' in RDF/SPARQL terminology. 
If missing, contect IRI will be built by concataining `context_base_IRI` and `name`
""",
"system": """A list of system command. 
This is a simple convenience provided by kgsteward which is not meant to be a replacement 
for serious Make-like system as for example git/dvc.
""",
"file": """List of files containing RDF data. 
Wildcard `*` can be used.
The strategy used to load these files will depends on if a file server is used (see `file_server_port` option`). 
With GraphDB, there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. 
Using a file server, these limitations are overcomed, but see the security warning described above. 
""",
"url": """List of url from which to load RDF data""",
"zenodo": """Do not use!
Fetch turtle files from zenodo. 
This is a completely ad hoc command developped for ENPKG (), that will be suppressed sooner or later
""",
"update": """List of files containing SPARQL update commands. 
Wildcard are not supported here!
""",
"source": """Path to another kgsteward YAML file from which the graphs list of record will be extracted 
and inserted in the current graphs list.
""",
    "parent": """A list of names to declare dependency between graph records. 
Updating the parent datset will provoke the update of its children.
""",
    "stamp": """List of paths to files which last modification dates will used.
The file contents are ignored.
Wildcard `*` can be used.
""",
    "replace": """Dictionary to perform string substitution in SPARQL queries from `update` list.
Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context.
"""
}

def describe( term ):
    if term in description:
        return description[ term ].replace( "\n", " " ).strip()
    else:
        return "No description"

class GraphDBConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "graphdb" ] = Field( title = "GraphDB brand", description = describe( "server_brand" ))
    location          : str = Field( default = "http://localhost:7200", title = "Server URL", description = describe( "location" ))
    server_config     : str = Field( title = "Server config file", description = describe( "server_config" ))
    file_server_port  : Optional[ int ] = Field( 0, title = "file_server_port", description = describe( "file_server_port" ))
    username          : Optional[ str ] = Field( None, title = "Username", description = describe( "username" ))
    password          : Optional[ str ] = Field( None, title = "Password", description = describe( "password" ))
    prefixes          : Optional[ list[str]]  = Field( None, title = "GraphDB namespace", description = describe( "prefixes" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))

class FusekiConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "fuseki" ] = Field( title = "Fuseki brand", description = describe( "server_brand" ))
    location          : str = Field( default = "http://localhost:3030", title = "Server URL", description = describe( "location" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))
    file_server_port  : Optional[ int ]  = Field( 0, title = "file_server_port", description = describe( "file_server_port" ))

class RDF4JConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "rdf4j" ] = Field( title = "RDF4J brand", description = describe(  "server_brand" ))
    location          : str = Field( default = "http://localhost:3030", title = "Server URL", description = describe( "location" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))
    file_server_port  : Optional[ int ]  = Field( 0, title = "file_server_port", description = describe( "file_server_port" ))

class GraphConf( BaseModel ):
    name     : str = Field( pattern = r"^[a-zA-Z]\w{0,31}$", title = "Short name of a graphs reccord", description = describe( "name" ))
    context  : Optional[ str ]        = Field( None,  title = "Full IRI of a context/named graph", description = describe(  "context" ))
    parent   : Optional[ List[ str ]] = Field( None,  title = "Parent(s) of a graphs record", description = describe(  "parent" ))
    frozen   : Optional[ bool ]       = Field( False, title = "Frozen graphs record", description ="Frozen record, use -d <name> can update it manually, -C has no effect" )
    system   : Optional[ List[ str ]] = Field( None,  title = "UNIX system command(s)", description = describe(  "system" ))
    file     : Optional[ list[ str ]] = Field( None,  title = "Load RDF from file(s)", description = describe(  "file" ))
    url      : Optional[ list[ str ]] = Field( None,  title = "Load RDF from URL(s)", description = describe(  "url" ))
    stamp    : Optional[ list[ str ]] = Field( None,  title = "Stamp file(s)", description = describe(  "stamp" ))
    replace  : Optional[ dict [ str, str ]] = Field( None, title = "String subtitution in SPARQL update(s)", description = describe(  "replace" ))
    update   : Optional[ list[ str ]] = Field( None,  title = "SPARQL update file(s)", description = describe(  "update" ))
    zenodo   : Optional[ list[ int ]] = Field( None,  title = "Ignore me", description = describe(  "zenodo" ))

class GraphSource( BaseModel ):
    source : str = Field( 
        title = "Path to a yaml file",
        # description = describe( 
        # "source" ),
    )

class KGStewardConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    version           : Literal[ "kgsteward2.0" ] = Field( title = "YAML syntax version", description = describe( "This fixed value determines the admissible YAML syntax" ))
    server            : Union[ GraphDBConf, RDF4JConf, FusekiConf ]
    dataset           : list[ Union[ GraphConf, GraphSource ]] = Field( required=True, title = "Knowledge Graph content", description = describe( "graphs" ))
    context_base_IRI  : Optional[ str ] = Field( "http://example.org/context/", description = "toto" )
    queries           : Optional[ list[ str ]]  = Field( None, title = "GraphDB queries", description = describe( "queries" ))
    validations       : Optional[ list[ str ]]  = Field( None, title = "Validation queries", description = describe( "validations" ))

class SourceGraphConf( BaseModel ):
    graphs            : list[ Union[ GraphConf, GraphSource ]] = Field( required=True, title = "Knowledge Graph content", description = describe( "graphs" ))

def parse_yaml_conf( path : str ):
    """Parsing kgsteward YAML config file(s) is a three step process:
    1. Parse YAML file(s) and execute !include directive
    2. Test YAML version
    3. Content-aware validation through pydantic
    """
    dir_yaml, filename = os.path.split( os.path.abspath( path ))
    file = open( path )
    yaml.add_constructor( "!include", yaml_include.Constructor( base_dir = dir_yaml ))
    with open( path ) as f:
        data = yaml.full_load(f)
    if "version" not in data:
        stop_error( "Key 'version' not found! you should upgrade YAML syntax to a recent one!" ) 
    try:
        config = KGStewardConf( **data ).model_dump( exclude_none = True )
    except ValidationError as e:
        stop_error( "YAML syntax error in file " + path + ":\n" + pformat( e.errors() ))

    config["kgsteward_yaml_directory"] = dir_yaml
    config["kgsteward_yaml_filename"]  = filename
    if "username" in config["server"] and not "password" in config["server"] :
        config["server"]["password"] = getpass.getpass( prompt = "Enter password : " )

    graphs = list()
    seen   = []
    for item in config["dataset"] :
        if item["name"] in seen:
            stop_error( "Duplicated name: " +  item["name"] )
        if "parent" in item:
            for parent in item["parent"]:
                if parent == "*":
                    item["parent"] = seen.copy()
                    break
                else:
                    if not parent in seen:
                        stop_error( "Parent not previously defined: " + parent )
        seen.append( item["name"] )
        if "context" not in item:
            item["context"] = str( config["context_base_IRI"] ) + str( item["name"] )
        graphs.append( item )
    config["dataset"] = graphs
    return config 

def save_json_schema( path ):
    schema = KGStewardConf.model_json_schema()
    schema["description"] = describe( "schema" )
    with open( path, "w" ) as f:
        f.write( dumps( schema, indent=2 ))
