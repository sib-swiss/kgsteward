
# Kgsteward config file

## Supported YAML syntax

Within the YAM config file(s), UNIX environment variables can by referred to using `$(...)`syntax. This is meant to faciliate the sharing of config files, as variable values remain stored in the local environment. 

* __`endpoint`__ - The SPARQL endpoint url.

```{yaml}
    endpoint: http://localhost:7200
```
* __`username`__ - The name of a user with write access-rights in the triplestore.

```{yaml}
    username: admin
```

* __`password`__ - The password of the abover user. It is highly recommended that the value of this variable is passed trough an environment variable, such as the password is not stored directly in the config file!  

```{yaml}
    password: ${SECRET_PASSWORD}
```

* __`repository_id`__ - the name of the repository in the triplestore.

```{yaml}
    repository_id: TEST
```

* __`setup_base_IRI`__ - base IRI to name the RDF graphs   

```{yaml}
    repository_id: https://www.example.com/
```

* __`graphdb_config`__ - filname with the triplestore configutation, possibly a turtle file

```{yaml}
    graphdb_config: config.ttl
```

* __`graphs`__ - Mandatory data graphs configuration, see details below. For example

```{yaml}
graphs:
  - dataset: schema
    file:    ${PATH_TO_RDF_DATA}/schema.ttl
    update:  ${PATH_TO_RDF_DATA}/fix_schema.sparql
  - dataset: pizza
    url: https://raw.githubusercontent.com/apache/jena/main/jena-examples/src/main/resources/data/pizza.owl.rdf
```

* __`queries`__ - A list of paths to files with SPARQL queries to be add to the repository user interface. Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint, with a short timeout. The query reusult is not iteself checked. Wild card can be supplied in the path. Example

```{yaml}
queries:
  - ${SOME_PATH}/query.sparql
  - ${PATH_TO_SPARQL_QUERIES}/*.rq
```

* __`validations`__ - path(s) to sparql queries used to validate the repsository. 
By convention a valid result return nothing, while the first five returned lines
represent an excerpt of the problems

```{yaml}
queries:
  - ${SOME_PATH}/query.sparql
  - ${PATH_TO_SPARQL_QUERIES}/*.rq
```

