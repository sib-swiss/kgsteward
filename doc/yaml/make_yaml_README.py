import sys
import json
import jsonschema_markdown
from kgsteward.yamlconfig import KGStewardConf

main_model_schema = KGStewardConf.model_json_schema()
main_model_schema["description"] = "Top level YAML keys"

with open( "kgsteward.schema.json", "w" ) as f:
	f.write( json.dumps( main_model_schema, indent=2 ))

with open( "kgsteward.schema.md", "w" ) as f:
    f.write( """<sup>back to [TOC](../README.md)</sup>

# YAML syntax of kgsteward config file (version 2)

## Preambule
            
* YAML 1.1 syntax is supported. 

* A single YAML extension is supported: `!include <filename>`. 
This directive will insert in place the content of `filename`.
The path of `<filename>` is interpreted with the directory of the parent YAML file as default directory. 
This inclusion mechanism is executed early, before the YAML configuration is validated.  

* Within the YAM config file(s), UNIX environment variables can by referred to using `${...}` syntax. 
Evaluation of these is performed late, i.e. at the time of command execution. 
Hence `${...}` syntax cannot be used in `!include` directive.
The use of UNIX environment variables is recommended to ensure portability of the YAML config files.
These variable are usually encoded with uppercase strings.

* In addition to UNIX environment variables, `kgsteward` creates temporary variables reflecting the content of the YAML config file.
For example `${kgsteward_server_brand}` contains the ... server brand, e.g. `graphdb`.
The most useful of these variables is certainly `${kgsteward_dataset_context"}` that contains the IRI of the current target context.
These variable are encoded with lowercase strings.

* The terminology adopted here is a compromise. Different server brands utilise different namings for the same conecpt. 
For example, 'context' in RDF4J/GraphDB terminology is the same as 'named graph' in RDF/SPARQL terminology.
In this respect, `kgsteward` utilises 'context', because of the too many usages of '[graph](https://en.wikipedia.org/wiki/Graph)'.  

## YAML syntax

The entry point (top level keys) is [KGStewardConf](#kgstewardconf).

""" )
    txt = jsonschema_markdown.generate( main_model_schema, hide_empty_columns = True )
    big_space = "&nbsp;" * 40
    txt = txt.replace( "| Description |",  "|" + big_space + "Description" + big_space + "|" ) # dirty patch to improve table layout
    
    f.write( txt + "\n\n<sup>back to [TOC](../README.md)</sup>" )
