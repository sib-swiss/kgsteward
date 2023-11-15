
# Kgsteward config file

## Supported YAML syntax

UNIX environment variable can by referred to using the `$(...)`syntax which is interpreted by `kgsteaward`. 

* __`endpoint`__ - The SPARQL endpoint url.

* __`username`__ - The name of a user with write access-rights in the triplestore.

* __`password`__ - The password of the abover user. It is highly recommended that the value of this variable is passed trough an environment variable, such as the password is not stored directly in the config file!  

    password: ${SECRET_PASSWORD}

* __`repository_id`__ - the name of the repository in the triplestore.

* __`setup_base_IRI`__ - base IRI to name the RDF graphs   

* __`graphdb_config`__ - filname with the triplestore configutation, possibly a turtle fil

* __`graphs`__ - dataset configuration, see details below

* __`queries`__ - A list of paths to files with SPARQL queries to be add to the repository user interface. Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint, with a short timeout. The query reusult is not iteself checked. Wild card can be supplied in the path. Example

```{yaml}
queries:
  - ${SOME_PATH}/query.sparql
  - ${PATH_TO_SPARQL_QUERIES}/*.rq
```

* __`validations`__ - path(s) to sparql queries used to validate the repsository. 
By convention a valid result return nothing, while the first five returned lines
represent an excerpt of the problems



