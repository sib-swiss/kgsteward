
# Kgsteward config file

## Supported YAML syntax

UNIX environment variable can by referred to using the `$(...)`syntax which is interpreted by `kgsteaward`. 

* __`endpoint_url`__ - The SPARQL endpoint url.

* __`username`__ - The name of a user with write access-rights on the triplestore

* __`password`__ - The password of the abover user. It is highly recommended that the value of this variable is passed trough an environment variable, such as the password is not stored in the config file!  

<div align="center">
  `password: ${GRAPHDB_SECRET_PASSWORD}`
</div>

* __`repository_id`__ - the name of the repository in the triplestore (the SPARQL endpoint is )

* __`setup_base_IRI`__ - base IRI to name the RDF graphs   

* __`graphdb_config`__ - filname with the triplestore configutation, possibly a turtle fil

* __`graphs`__ - dataset configuration

* __`queries`__ - SPARQL queries to add to the repository

* __`validations`__ - path(s) to sparql queries used to validate the repsository. 
By convention a valid result return nothing, while the first five returned lines
represent an excerpt of the problems



