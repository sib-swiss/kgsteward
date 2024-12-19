import sys
import json
import jsonschema_markdown
from kgsteward.yamlconfig import KGStewardConf

main_model_schema = KGStewardConf.model_json_schema()

with open( "kgsteward.schema.json", "w" ) as f:
	f.write( json.dumps( main_model_schema, indent=2 ))

with open( "kgsteward.schema.md", "w" ) as f:
    f.write( """
# kgsteward YAML syntax


""" )
    txt = jsonschema_markdown.generate( main_model_schema )
    txt = txt.replace( "| Description |",  "| ____________Description____________ |" )
    f.write( txt )
# f.write( jsonschema_markdown.generate( main_model_schema ))
