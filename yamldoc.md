
# Kgsteward config file

## Supported YAML syntax

Within the YAM config file(s), UNIX environment variables can by referred to using `${...}`syntax. This is meant to faciliate the sharing of config files, as variable values remain stored in the local environment.

* __`endpoint`__ - The SPARQL endpoint url. This key is optional and the user is prompted for it if it is not defined

```{yaml}
    endpoint: http://localhost:7200
```
* __`username`__ - The name of a user with write access-rights in the triplestore. This key is optional and the user is prompted for it if it is not defined

```{yaml}
    username: admin
```

* __`password`__ - The password of the abover user. It is highly recommended that the value of this variable is passed trough an environment variable, such as the password is not stored directly in the config file! If this key is absent and the user will be prompted for a password, which might more secure.

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
  - dataset: pizza_data
    url: https://raw.githubusercontent.com/apache/jena/main/jena-examples/src/main/resources/data/pizza.owl.rdf
    update: ${PATH_TO_RDF_DATA}/remove_pizza_schema.sparql
  - dataset: pizzaschema
    file:    ${PATH_TO_RDF_DATA}/my_own_pizza_schema.ttl
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

### `graphs` syntax

It consist in an ordered list of records that will be considered in the supplied order. The following key is manadtory in every record

* __`dataset`__ - Mandatory name for this record. It will permit to create the RDF named graph <setup_base_IRI><dataset>

At least one of the following keys should be supplied. Note that the execution order will be the same as listed below

* __`file`__ - Optional list of files containing RDF data. Nota Bene: there is a maximal file size that is allowed. It is 200 MB for GraphDB.

* __`url`__ - Optional list of url from which to load RDF data

* __`zenodo`__

In addition, the following two keys permits

* __`source`__

* __`parent`__
