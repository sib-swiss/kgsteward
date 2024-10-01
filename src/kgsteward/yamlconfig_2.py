""" YAML config """
# https://matthewpburruss.com/post/yaml/ # example of yaml.add_constructor
# https://gist.github.com/joshbode/569627ced3076931b02f # code for includue MUCH simpler than the one of yaml_include
# https://stackoverflow.com/questions/52412297/how-to-replace-environment-variable-value-in-yaml-file-to-be-parsed-using-python

import os
import yaml
import json
import jsonschema
from dumper import dump
from typing import Any, IO
from common import *


class Loader( yaml.SafeLoader ):
    """YAML Loader with `!include` constructor."""

    def __init__(self, stream: IO) -> None:
        """Initialise Loader."""

        try:
            self._root = os.path.split(stream.name)[0]
        except AttributeError:
            self._root = os.path.curdir

        super().__init__(stream)


def construct_include(loader: Loader, node: yaml.Node) -> Any:
    """Include file referenced at node."""

    filename = os.path.abspath(os.path.join(loader._root, loader.construct_scalar(node)))
    extension = os.path.splitext(filename)[1].lstrip('.')

    with open(filename, 'r') as f:
        return yaml.load(f, Loader)
 
yaml.add_constructor( '!include', construct_include, Loader)

def parse_yaml( file_yaml, file_schema_json = None ):

#    yaml.add_constructor( 
#        "!include", 
#        yaml_include.Constructor( base_dir = os.path.dirname( os.path.expandvars( file_yaml )))
#    )

    report( 'parse', file_yaml )
    with open( file_yaml, 'r' ) as f:
        config = yaml.load( f, Loader = yaml.Loader )
    dump( config )
    stop_error( "done" )

    report( 'parse', file_schema_json )
    with open( file_schema_json, 'r' ) as f:
        schema = json.load( f )
    dump( config )
    stop_error( "toto")
    # dump( config )
    # dump( schema )
    report( 'validate', 'config with json schema' )
    try:
        jsonschema.validate( config, schema )
    except jsonschema.ValidationError as e:
        stop_error( e.schema.get("error_msg", e.message))
    return config

def main():
    conf = parse_yaml( 
        "/Users/mpagni/github.com/kgsteward/test/test.yaml", 
        "/Users/mpagni/github.com/kgsteward/test/kgsteward.schema.json"
    )

if __name__ == "__main__":
    main()
