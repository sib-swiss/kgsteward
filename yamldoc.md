
# Kgsteward config file

## >Expected YAML syntax


* `repository_id` - the name of the repository in the triplestore (the SPARQL endpoint is )

* __setup_base_IRI__ - base IRI to name the RDF graphs   

* `__graphdb_config__` - filname with the triplestore configutation, possibly a turtle file

* __`graphs`__ - dataset configuration

* queries - SPARQL queries to add to the repository

* validations - path(s) to sparql queries used to validate the repsository. 
By convention a valid result return nothing, while the first five returned lines
represent an excerpt of the problems



