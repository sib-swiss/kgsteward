# Kgsteward config file

## Supported YAML syntax

Within the YAM config file(s), UNIX environment variables can by referred to using `${...}`syntax. This is meant to faciliate the sharing of config files, as variable values remain stored in the local environment.


* __`server_type`__ 

Only one values is currently supported: `GraphDB` and it is the defaults. This key is currently optional 

```{yaml}
    server_type: GraphDB
```

* __`server_url`__ - The SPARQL endpoint url. This key is optional and the user is prompted for it if it is not defined

```{yaml}
    server_url: http://localhost:7200
```
`endpoint`is synonym for `server_url`. In addition of being deprecated, it is misleading as the SPARQL endpoint is actually located at `${server_url}/repositories/${repository_id}` for RDF4J and GraphDB servers. 

* __`repository_id`__ - the name of the repository in the triplestore.

```{yaml}
    repository_id: TEST
```

* __`username`__ - The name of a user with write access-rights in the triplestore. This key is optional and the user is prompted for it if it is not defined

```{yaml}
    username: admin
```

* __`password`__ - The password of the abover user. It is highly recommended that the value of this variable is passed trough an environment variable, such as the password is not stored directly in the config file! If this key is absent and the user will be prompted for a password, which might more secure.

```{yaml}
    password: ${SECRET_PASSWORD}
```

* __`setup_base_IRI`__ - base IRI to name the RDF graphs 

```{yaml}
    setup_base_IRI: http://www.example.com/
```
* __`use_file_server`__ - Boolean, `false` by default. When turned `true`: local files will be exposed in a temporary HTTP server and loaded from it. The benefit is the that RDF data from `file`are processed with the same protocol as those supplied through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. 

* __`config_file`__ - filename with the triplestore configutation, possibly a turtle file. This file can be saved from the UI interface of RDF4J/GraphDB after a first repository is created interactively. This file is only used with the `-I` and `-F` options.

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

* __`dataset`__ - Mandatory name for this record. It will permit to create the RDF named graph <setup_base_IRI><dataset> FIXME: rename this as `name`

At least one of the following keys should be supplied. Note that they will be executed in order `system`, `url`, `file`, `zenodo`, `update`. For a different order, use two datasets and a dependency. 

* __`system`__ - A system command.  

* __`file`__ - Optional list of files containing RDF data. Nota Bene: there might be a maximal file size that is allowed - it is 200 MB by default for GraphDB and compressed file format may not be supported 

* __`url`__ - Optional list of url from which to load RDF data

* __`zenodo`__ - Fetch turtle from zenodo. This is an ad hoc command developped for ENPKG.

* __`update`__ 

In addition, the following two keys are supported

* __`source`__ A

* __`parent`__ Create a dependency graph between resource
