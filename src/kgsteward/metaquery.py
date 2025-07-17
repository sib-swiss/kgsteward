from typing        import List, Optional, Union, Literal
from pydantic      import BaseModel, Field

class InputSelect( BaseModel ):
    type: Literal[ "select" ] = Field( title = "select", description = describe( "Checkbox input, value is unique" ) )
    sparql: str = Field( title = "SPARQL query name", description = "SPARQL query to be executed to create the checkboxes." )
    default: Optional[ str ] = Field( None, title = "Default value", description = "Optional default value" )

class InputCheckbox( BaseModel ):
    type: Literal[ "checkbox" ] = Field( title = "checkbox", description = describe( "Checkbox input, values are at least one" ) )
    sparql: str = Field( title = "SPARQL query name", description = "SPARQL query to be executed to create the checkboxes." )
    separator: Optional[ str ] = Field( " ", title = "Separator", description = "Optional separator to be used in the query, space by default." )
    default: Optional[ str ] = Field( None, title = "Default value", description = "Optional  default value" )

class QueryField( BaseModel ):
    # name: str = Field( ..., title = "Query Name", description = "The name of the query." )
    # description: str = Field( None, title = "Query Description", description = "A brief description of the query." )
    target: str = Field( title = "Target string to be replaced", description = "Target string to replace one or many times in a SPARQL query, typically a SPARQL variable." )
    value: Union[ InputCheckbox, InputRadio ] = Field( title = "Value", description = "The value to be used in the query." )

class MetaQueryConf( BaseModel ):
    name: str = Field( pattern = r"^[a-zA-Z]\w+$", title = "Query Name", description = "The name of the query." )
    documentation: str = Field( None, title = "Query Documentation", description = "An URL to overall doucumentation shared by many queries." )
    field: Optional[ List[ QueryField ]] = Field( None, title = "Load queries from files", description = describe(  "file_query" ))

class QueryParser():

    def __init__( self ):
        self.conf = conf
        self.queries = {}
        self.queryparser = None

    def parse_queries( self, txt: str ):
        yaml = "\n".join(
            line[2:].strip() for line in text.splitlines() if line.strip().startswith("##")
        )
        conf = MetaQueryConf.model_validate_yaml( meta )

toto = QueryParser.new()