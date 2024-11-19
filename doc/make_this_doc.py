import sys
import json

from kgsteward.yamlconfig import KGStewardConf

main_model_schema = KGStewardConf.model_json_schema()

with open( "kgsteward.schema.json", "w" ) as f:
	f.write( json.dumps( main_model_schema, indent=2 ))

#with open( "kgsteward.schema.md", "w" ) as f:
#    f.write( jsonschema_markdown.generate( main_model_schema ))

