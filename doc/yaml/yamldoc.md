# Kgsteward config file: YAML syntax

## Server config parameters

Within the YAM config file(s), UNIX environment variables can by referred to using `${...}`syntax. This is meant to faciliate the sharing of config files, as variable values remain stored in the local environment.


* __`server_type`__ 

Only one values is currently supported: `GraphDB` and it is the defaults. This key is currently optional 

```{yaml}
    server_type: GraphDB
```

* __`server_url`__ - The server URL. This key is optional and the user is prompted for it if it is not defined. This key is stored in the execution environment and can be accessed through  `${server_url}`. `endpoint` is a deprecated synonym for `server_url` which is misleading as the real SPARQL endpoint is located at `${server_url}/repositories/${repository_id}` in RDF4J and GraphDB servers. For example the default server URL of a GraphDB instance can be set as:

```{yaml}
    server_url: http://localhost:7200
```

* __`repository_id`__ - the name of the repository in the triplestore. This key is stored in the execution environment and can be accessed through ${repository_id}. 

```{yaml}
    repository_id: TEST
```

* __`username`__ - The name of a user with write-access rights to the triplestore. This key is optional and when it is absent the server is expected to be accessed in write more without authentication. For example:

```{yaml}
    username: admin
```

* __`password`__ - The password of a user with write-access rights to the triplestore. It is recommended that the value of this variable is passed trough an environment variable, such as the password is not stored directly in the config file! Alternatively if this key is absent and `username` is defined, a password will be prompted for interactively, which is more secure. 

```{yaml}
    password: ${SECRET_PASSWORD}
```

* __`dataset_base_IRI`__ - base IRI to construct the name the RDF graphs/context. `setup_base_IRI` is a deprecated synonym. See `graphs` below for how it is used. For example 

```{yaml}
    setup_base_IRI: http://www.example.com/context/
```
* __`use_file_server`__ - Boolean, `false` by default. When turned `true`: local files will be exposed in a temporary HTTP server and loaded from it. The benefit is the that RDF data from `file`are processed with the same protocol as those supplied through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall.

* __`file_server_port`__  - Optional integer, default to 8000.

* __`server_config`__ - filename with the triplestore configuration, possibly a turtle file. `graphdb_config` is a deprecated synonym. This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively, thus permitting to reproduce the repository configuration elsewhere. This file is used by the `-I` and `-F` options. Beware that the repository ID could be hard-coded in the config file and should be maintained in sync with `repository_id`. 

```{yaml}
    server_config: config.ttl
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

## Datasets / RDF graphs /contexts syntax

 Values of the __`graphs`__ key consists in an ordered list of records that are processed in the supplied order. The following key is mandatory in every record:

* __`dataset`__ - Mandatory name for this record. If `file`, `url`, `zenodo` or `update` are supplied, `target_context` will be created  as a RDF named graph/context by concataining `<dataset_base_IRI>` and `<dataset>`. A list datasets to update can be supplied to kgsteard with the `-d` option.

At least one of the following keys should be supplied in every record. Note that they will always be executed in order `target_context`, `system`, `url`, `file`, `zenodo`, `update`. For a different order, use two datasets and a `parent` dependency. 

* __`target_context`__ An optional RDF named graph/context that will overwrite the default one produced by concataining `<dataset_base_IRI>` and `<dataset>`. __not yet implemented__

```{yaml}
target_context: http://www.example.com/context/mytestcontext
```

* __`system`__ - A list of system command. This is a simple convenience provided by kgsteward which is not meant to be a replacement for serious make-like system (as git/dvc).

```{yaml}
system:
  - rapper -c -i turtle input.ttl
```

* __`file`__ - Optional list of files containing RDF data. Wild card "*" can be used. The strategy to load the files depends on the `use_file_server` Boolean value. With GraphDB, if `use_file_server` is `false` there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. With `use_file_server` set to `true` these limitations are overcomed, but see the security warning described above. 

* __`url`__ - Optional list of url from which to load RDF data

* __`zenodo`__ - Fetch turtle files from zenodo. This is a completely ad hoc command developped for ENPKG (), that would deserve to be better implemented/documented.

* __`update`__ - Optional list of SPARQL updates command. Each list item is either a filename, or a record with two keys `file` and `replace`.

* __`source`__ A YAML file with the syntax described here. This has only been tested with the `graphs` key. This proved useful to sepparate server-specfic parameters in the outer YAML file, and datasets content in in the inner YAML file. 

* __`parent`__ A comma-separated list of dataset to encode dependency between datasets. Updating the parent datset will provoke the update of its children.
