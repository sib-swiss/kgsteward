from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, ValidationError
from pydantic_yaml import parse_yaml_raw_as, to_yaml_str
import json

from common import *

class UpdateConf( BaseModel ):#
    sparql_update_file : list[ str ]
    replace            : list[ dict [ str, str ]]

class GraphConf ( BaseModel ):
    dataset  : Optional[ str ] = None
    parent   : Optional[ str ] = None
    source   : Optional[ str ] = None
    system   : Optional[ list[ str ]] = None
    file     : Optional[ list[ str ]] = None
    url      : Optional[ list[ str ]] = None
    stamp    : Optional[ list[ str ]] = None
    update   : Optional[ Union[ list[ UpdateConf ], list[ str ]]] = None
    zenodo   : Optional[ list[ int ]] = None

class KGStewardConf( BaseModel ):
    server_url        : int = Field( 
        "http://localhost:7200",
        title = "Server URL",
        description = "URL of the server. The SPARL endpoint is different and server specific.",
    )
    server_config     : Optional[ str ] = None
    graphdb_config    : Optional[ str ] = None
    endpoint          : Optional[ str ] = Field( 
        None,
        title       = "Server URL",
        description = "endpoint is deprecated, use server_url",
    )
    repository_id     : str = None
    dataset_base_IRI  : str = "http.//example.org/context"
    username          : str = None
    password          : str = None
    use_file_server   : Optional[ bool ] = False 
    graphs            : list[ GraphConf ]
    prefixes          : list[str]  = None
    queries           : list[str]  = None
    validations       : list[str]  = None


def parse_yaml_conf( path : str ) -> KGStewardConf:
    file = open( path )
    try:
        conf = parse_yaml_raw_as( KGStewardConf, file.read())
    except ValidationError as e:
        stop_error( "YAML syntax error(): " + e.errors())
    return conf.model_dump()

c1 = parse_yaml_conf( "/Users/mpagni/gitlab.com/ReconXKG/reconxkg.yaml" )
print( c1 )
# main_model_schema = KGStewardConf.model_json_schema()  # (1)!
# print(json.dumps(main_model_schema, indent=2))  # (2)!

# for graph in c1.graphs:
#     print(graph.dataset)

#c2 = parse_yaml_conf( "/Users/mpagni/gitlab.sib.swiss/sinergiawolfender/common/data/config/jlw.yaml" )
#print( c2 )