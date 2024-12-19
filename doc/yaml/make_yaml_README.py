import sys
import json
import jsonschema_markdown
from kgsteward.yamlconfig import KGStewardConf

main_model_schema = KGStewardConf.model_json_schema()
main_model_schema["description"] = "Top level YAML keys"

with open( "kgsteward.schema.json", "w" ) as f:
	f.write( json.dumps( main_model_schema, indent=2 ))

with open( "kgsteward.schema.md", "w" ) as f:
    f.write( """
# kgsteward config file: supported YAML syntax

YAML 1.1 syntax is supported. 

A YAML extension is available: `!include <filename>`. 
This directive will insert in place the content of `filename`.
The path of `<filename>` is interpreted with the directory of the parent YAML file as default directory. 
This inclusion mechanism is executed early, before the YAML configuration is validated.  

Within the YAM config file(s), UNIX environment variables can by referred to using `${...}` syntax. 
Evaluation of these is performed at the time of command execution. 
Hence `${...}` syntax cannot be used in `!include` directive.

# kgsteward YAML syntax

""" )
    txt = jsonschema_markdown.generate( main_model_schema )
    big_space = "&nbsp;" * 30
    txt = txt.replace( "| Description |",  "|" + big_space + "Description" + big_space + "|" ) # dirty patch to improve table layout
    f.write( txt )
