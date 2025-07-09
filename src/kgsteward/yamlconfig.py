# https://stackoverflow.com/questions/58703926/how-do-i-generate-yaml-containing-local-tags-with-ruamel-yaml$
# https://app.soos.io/research/packages/Python/-/pydantic-yaml-parser/

import yaml
import yaml_include
from dumper        import dump
from enum          import Enum
from typing        import List, Optional, Union, Literal
from pprintpp      import pformat
from pydantic      import BaseModel, Field, ValidationError, ConfigDict
import json
from .common       import *

description = {
    "schema": """
    Configuration file follows YAML syntax.
    UNIX environmenent variables can be accessed anywhere in the YAML config through the `${<env-var>}` syntax.
    The use of UNIX environment variables permits the portability of kgsteward config file, as local path are supplied through variables.
    For security reason, kgsteward checks that every used variable exists and is not an empty string.
    In addition, to the environment variables available at statup of kgsteward, a certain number of variables are defined at run-time:
    `${}`, `${}` and `${}`.
    Especially useful is `${dataset.name}` that can be used in be used in `dataset.replace` clause to indicate the current "active" context/named graph.
""",
    "server_brand": """String identifying the server brand. One of 'graphdb', 'rdf4j', 'fuseki' """,
    "location" :  """URL of the server. The SPARQL endpoint locations for queries, updates and stores are specific to a server brand.""" ,
    "repository": """The name of the 'repository' (GraphDB/RDF4J naming) or 'dataset' (fuseki) in the triplestore.""",
    "username":      """The name of a user with write-access rights in the triplestore.""",
    "password":      """The password of a user with write-access rights to the triplestore.
It is recommended that the value of this variable is passed trough an environment variable.
By this way the password is not stored explicitely in the config file.
Alternatively `?` can be used and the password will be asked interactively at run time.""",
    "context_base_IRI": """Base IRI to construct the graph context. In doubt, give `http://example.org/context/` a try.""",
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
This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively,
thus permitting to reproduce the repository configuration elsewhere.
This file is used by the `-I` and `-F` options.
Beware that the repository ID could be hard-coded in the config file and should be maintained in sync with `repository`.
""",
    "dataset": "Mandatory key to specify the content of the knowledge graph in the triplestore.",
    "queries": """A list of paths to files with SPARQL queries to be add to the repository user interface.
Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint,
with a short timeout.
The query result is not itself checked.
Wildcards `*` can be used.
""",
    "validations": """A list of paths to files contining SPARQL queries used to validate the repository.
Wildcards `*` can be used.
By convention, a valid result should be empty, i.e. no row is returned.
Failed results should return rows permitting to diagnose the problems.
""",
    "name": """Mandatory name of a dataset record.""",
    "context": """ The IRI of the target context.
If missing, it will be built by concataining `context_base_IRI` and `name`.
""",
"system": """A list of system command.
This is a simple convenience provided by kgsteward, which is not meant to be a replacement
for serious Make-like system as for example git/dvc.
""",
"file": """List of files containing RDF data.
Wildcards `*` can be used.
The strategy used to load these files will depends on if a file server is used (see `file_server_port` option`).
With GraphDB, there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported.
Using a file server, these limitations are overcome, but see the security warning described above.
""",
"url": """List of url from which to load RDF data""",
"frozen": "Frozen record, can only be updated explicitely with the `-d <name>` option. The option `-C` has no effect",
"zenodo": """Do not use!
Fetch turtle files from zenodo.
This is a completely ad hoc command developed for ENPKG, that will be suppressed sooner or later.
""",
"update": """List of files containing SPARQL update commands.
Wildcards are not recommended here, as the order of the SPARQL updates possibly matters!
""",
#"source": """Path to another kgsteward YAML file from which the graphs list of record will be extracted
#and inserted in the current graphs list.
#""",
    "parent": """A list of dataset names to declare dependency between dataset records.
Updating the parent datset will provoke the update of its children, unless it is frozen.
""",
    "stamp": """List of file paths or URLs to which last modification dates will used.
The file contents are ignored.
Wildcards `*` can be used.
""",
    "replace": """Dictionary to perform string substitution in SPARQL queries from `update` list.
Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context.
""",
    "prefixes": """
        A list of Turtle files from which prefix definitions can be obtained.
        This list will used to update the namespace definitions in GraphDB and RDF4J.
        Otherwise it is ignored
    """,
    "sparql_file_loader" : """Files are loaded using the SPARQL update statement: "LOAD <file://<file-path> INTO...". This strategy is likely to failed for large files, or worst silently truncate them.""",
    "store_file_loader"  : """Files are loaded using the graph store protocol. This strategy is likely to failed for large files, or worst silently truncate them. """,
    "http_file_server"   : """Files are exposed through a temporary HTTP server. This is the recommended method with GraphDB, however CORS mut be enabled.""",
    "riot_chunk_store"   : """Files are parsed through riot (part of JENA distribution), and submitted by chunks using graph store protocol. This is the recommended method with Fuseki. """,
    "sparql_url_loader"  : """URL are loaded using the SPARQL update statement: "LOAD <url> INTO...". This strategy could fail for large files, or worst silently truncate them. """,
    "curl_riot_chunk_store" : """URL are downloaded using curl to a temporary file, which is then loaded with `riot_chunk_store` method.""",
    "name_query": "Mandatory name of a set queries",
    "file_query": """List of files containing one SPARQL query each.
Wildcards `*` can be used, and implied file names will be sorted alphabetically.
The file name of each file is interpreted as the query label.
In each file, lines starting with "#" are considered as the query documentation (comment)""",
"collection_queries": """Structured list of SPARQL queries.""",
    "special": """A list of special dataset records. Supported values are "sib_swiss_void"."""
}


description["location_graphdb"] = description["location"] + " GraphDB has location 'http://localhost:7200' by default"
description["location_fuseki"]  = description["location"] + " Fuseki has location 'http://localhost:3030' by default"
description["location_rdf4j"]   = description["location"] + " RDF4J has location 'http://localhost:8080' by default"

def describe( term ):
    if term in description:
        return description[ term ].replace( "\n", " " ).strip()
    else:
        stop_error( "No description for: " + term )

class GraphDBConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "graphdb" ] = Field( title = "GraphDB brand", description = describe( "server_brand" ))
    location          : str = Field( title = "Server URL", description = describe( "location_graphdb" ))
    server_config     : str = Field( title = "Server config file", description = describe( "server_config" ))
    file_server_port  : Optional[ int ] = Field( None, title = "file_server_port", description = describe( "file_server_port" ))
    username          : Optional[ str ] = Field( None, title = "Username", description = describe( "username" ))
    password          : Optional[ str ] = Field( None, title = "Password", description = describe( "password" ))
    prefixes          : Optional[ List[str]]  = Field( None, title = "GraphDB namespace", description = describe( "prefixes" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))

class FusekiConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "fuseki" ] = Field( title = "Fuseki brand", description = describe( "server_brand" ))
    location          : str = Field( title = "Server URL", description = describe( "location_fuseki" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))
    file_server_port  : Optional[ int ]  = Field( 0, title = "file_server_port", description = describe( "file_server_port" ))

class RDF4JConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    brand             : Literal[ "rdf4j" ] = Field( title = "RDF4J brand", description = describe(  "server_brand" ))
    location          : str = Field( title = "Server URL", description = describe( "location_rdf4j" ))
    repository        : str= Field( pattern = r"^\w{1,32}$", title = "Repository ID", description = describe( "repository" ))
    file_server_port  : Optional[ int ]  = Field( 0, title = "file_server_port", description = describe( "file_server_port" ))

class SpecialEnum( str, Enum ):
    sib_swiss_void   = 'sib_swiss_void'
    sib_swiss_prefix = 'sib_swiss_prefix'
    sib_swiss_query  = 'sib_swiss_query'

class DatasetConf( BaseModel ):
    name     : str = Field( pattern = r"^[a-zA-Z]\w{0,31}$", title = "Short name of a dataset record", description = describe( "name" ))
    context  : Optional[ str ]        = Field( None,  title = "Full IRI of a context/named graph", description = describe(  "context" ))
    parent   : Optional[ List[ str ]] = Field( None,  title = "Parent(s) of a dataset record", description = describe(  "parent" ))
    frozen   : Optional[ bool ]       = Field( False,  title = "Frozen dataset record", description = describe( "frozen") )
    system   : Optional[ List[ str ]] = Field( None,  title = "UNIX system command(s)", description = describe(  "system" ))
    file     : Optional[ List[ str ]] = Field( None,  title = "Load RDF from file(s)", description = describe(  "file" ))
    url      : Optional[ List[ str ]] = Field( None,  title = "Load RDF from URL(s)", description = describe(  "url" ))
    stamp    : Optional[ List[ str ]] = Field( None,  title = "Stamp file(s)", description = describe(  "stamp" ))
    replace  : Optional[ dict [ str, str ]] = Field( None, title = "String substitution in SPARQL update(s)", description = describe(  "replace" ))
    update   : Optional[ List[ str ]] = Field( None,  title = "SPARQL update file(s)", description = describe(  "update" ))
    zenodo   : Optional[ List[ int ]] = Field( None,  title = "Ignore me", description = describe(  "zenodo" ))
    special  : Optional[ List[ SpecialEnum ]] = Field( None, title = "Special dataset", description = describe(  "special" ))

class SparqlFileLoader( BaseModel ):
    method : Literal[ "sparql_load" ] = Field( title = "sparql file loader", description = describe( "sparql_file_loader" ) )
class StoreFileLoader( BaseModel ):
    method : Literal[ "file_store" ] = Field( title = "store file loader", description = describe( "store_file_loader" ) )
class HttpServerFileLoader( BaseModel ):
    method : Literal[ "http_server" ] = Field( title = "HTTP file server", description = describe( "http_file_server" ))
    port : Optional[ int ] = Field( 8000, title = "file_server_port", description = describe( "file_server_port" ))
class RiotChunkStoreFileLoader( BaseModel ):
    method : Literal[ "riot_chunk_store" ] = Field( title = "riot/store file loader", description = "riot_chunk_store" )
    size : Optional[ int ] = Field( 100_000_000, title = "chunk size", description = "chunk size" )

class SparqlUrlLoader( BaseModel ):
    method : Literal[ "sparql_load" ] = Field( title = "direct url loader", description = describe( "sparql_url_loader" ))
class CurlRiotChunkStoreUrlLoader( BaseModel ):
    method : Literal[ "curl_riot_chunk_store" ] = Field( title = "curl/riot/store URL loader", description = describe( "curl_riot_chunk_store" ))
    tmp_dir : Optional[ str ] = Field( "/tmp", title = "temporary directory", description = "temporary directory" )
    size : Optional[ int ] = Field( 100_000_000, title = "chunk size", description = "chunk size" )

#class AssertEnum( str, Enum ):
#    nothing   = 'nothing'
#    something = 'something'

class TestConf( BaseModel ):
    min_row_count : Optional[ int ] = Field( None, title = "Minimal number of rows to expect" )
    max_row_count : Optional[ int ] = Field( None, title = "Maximal number of rows to expect" )
#    min_unbound_count = Optional[ int ] = Field( None, title = "Minimal number of unbound values to expect" )
#    max_unbound_count = Optional[ int ] = Field( None, title = "Maximal number of unbound values to expect" )

class QueryConf( BaseModel ):
    name     : str = Field( pattern = r"^[a-zA-Z]\w{0,31}$", title = "Short name of a query set", description = describe( "name_query" ))
    system   : Optional[ List[ str ]] = Field( None, title = "UNIX system command(s)", description = describe(  "system" ))
    test     : Optional[ TestConf ] = Field( None, title = "Assertion to be tested", description = "assert nothing/something" )
    public   : Optional[ bool ]       = Field( True, title = "Should query be published", description= "no description" )
    file     : Optional[ List[ str ]] = Field( None, title = "Load queries from files", description = describe(  "file_query" ))

class KGStewardConf( BaseModel ):
    model_config = ConfigDict( extra='allow' )
    version           : Literal[ "kgsteward_yaml_3" ] = Field( title = "YAML syntax version", description = "This mandatory fixed value determines the admissible YAML syntax" )
    server            : Union[ GraphDBConf, RDF4JConf, FusekiConf ] = Field( discriminator = 'brand' )
    file_loader       : Union[ SparqlFileLoader, StoreFileLoader, HttpServerFileLoader, RiotChunkStoreFileLoader ]
    url_loader        : Union[ SparqlUrlLoader, CurlRiotChunkStoreUrlLoader ]
    dataset           : List[ DatasetConf ] = Field( title = "Knowledge Graph content", description = describe( "dataset" ))
    context_base_IRI  : str = Field( title = "context base IRI", description = describe( "context_base_IRI" ) )
    queries           : Optional[ List[ QueryConf ]] = Field( title = "Collection of SPARQL queries", description = describe( "collection_queries" ))
    validations       : Optional[ List[ str ]]  = Field( None, title = "Validation queries", description = describe( "validations" ))

def parse_yaml_conf( path : str ):
    """Parsing kgsteward YAML config file(s) is a four step process:
    1. Parse YAML file(s) and execute !include directive
    2. Test YAML version
    3. Content-aware validation through pydantic
    4. Additional validations at runtime
    """
    dir_yaml, filename = os.path.split( os.path.abspath( path ))
    file = open( path )
    yaml.add_constructor( "!include", yaml_include.Constructor( base_dir = dir_yaml ))
    try:
        with open( path ) as f:
            data = yaml.full_load(f)
    except Exception as e:
        stop_error( "Something goes wrong with YAML parsing: " + repr( e ))
    if "version" not in data:
        stop_error( 'Key "version" not found in YAML file: ' + path )
    try:
        config = KGStewardConf( **data ).model_dump( exclude_none = True )
    except ValidationError as e:
        stop_error( "YAML syntax error in file " + path + ":\n" + pformat( e.errors() ))

    config["kgsteward_yaml_directory"] = dir_yaml
    config["kgsteward_yaml_filename"]  = filename
    if "username" in config["server"] and not "password" in config["server"] :
        config["server"]["password"] = getpass.getpass( prompt = "Enter password : " )

    dataset = list()
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
        dataset.append( item )
    config["dataset"] = dataset
    return config

def save_json_schema( path ):
    schema = KGStewardConf.model_json_schema()
    schema["description"] = describe( "schema" )
    with open( path, "w" ) as f:
        f.write( dumps( schema, indent=2 ))
