import sys
import json
import jsonschema_markdown
from kgsteward.yamlconfig import KGStewardConf

main_model_schema = KGStewardConf.model_json_schema()
main_model_schema["description"] = "Decription of the YAML syntax supported by kgsteward"

with open( "kgsteward.schema.json", "w" ) as f:
	f.write( json.dumps( main_model_schema, indent=2 ))

with open( "kgsteward.schema.md", "w" ) as f:
    f.write( """
# kgsteward config file: supported YAML syntax

Full YAML 2.0 syntax is supported. 

A single YAML extension is implemented: the `!include <filename>` directive, that will insert in place the content of `filename`.
The path of `<filename>` is interpreted with directory of the parent YAML file as default. 
This inclusion mechanism is executed early, before the full YAML configuration is checked.  

Within the YAM config file(s), UNIX environment variables can by referred to using `${...}` syntax. 
Their evaluation is performed late, at the time of command execution. 
`${...}` syntax cannot be used in `!include`directive.

# kgsteward YAML syntax

""" )
    txt = jsonschema_markdown.generate( main_model_schema )
    big_space = "&nbsp;" * 30
    txt = txt.replace( "| Description |",  "|" + big_space + "Description" + big_space + "|" ) # dirty patch to improve table layout
    f.write( txt )
