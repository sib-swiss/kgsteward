
# Kgsteward config file

## Supported YAML syntax

Environmental variable are reffered to using `$(...)`syntax

* __`repository_id`__ - the name of the repository in the triplestore (the SPARQL endpoint is )

* __`setup_base_IRI`__ - base IRI to name the RDF graphs   

* __`graphdb_config`__ - filname with the triplestore configutation, possibly a turtle fil

* __`graphs`__ - dataset configuration

* __`queries`__ - SPARQL queries to add to the repository

* __`validations`__ - path(s) to sparql queries used to validate the repsository. 
By convention a valid result return nothing, while the first five returned lines
represent an excerpt of the problems



