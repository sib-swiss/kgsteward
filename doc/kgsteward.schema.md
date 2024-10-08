# KGStewardConf

Configuration file follows YAML syntax.      `${<env-var>}` in YAML config will be replaced by the value of environment variable <env-var>.      The use of UNIX environment variables is recommended to ensure the portability of a config file, local path variables must be supplied asvariable.      For secuity reason, kgsteward checks that every used environment variable exitsts and is not an empty string.      In addition, to environment variables available available at statup,      kgsteward provides access to the following list of run-time variable: `${}`, `${}` and `${}`.     `${graphs.name}`is of uttermost to be used in replace clause.

### Type: `object`

| Property | Type | Required | Possible values | Default | Description |
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| repository_id | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24) |  | The name of the 'repository' (GraphDB naming) or 'dataset' (fuseki) in the triplestore. |
| graphs | `array` | ✅ | [GraphConf](#graphconf) |  | Mandatory key to specify the content of the knowledge graph in the triplestore |
| server_brand | `string` |  | string | `"graphdb"` | One of 'graphdb' or 'fuseki' ( 'graphdb' by default). |
| server_url | `string` |  | string | `"http://localhost:7200"` | URL of the server. The SPARL endpoint is different and server specific. |
| context_base_IRI | `string` |  | string | `"http://example.org/context/"` |  |
| dataset_graph_IRI | `string` |  | string |  |  |
| setup_graph_IRI | `string` |  | string |  |  |
| username | `string` or `null` |  | string |  | The name of a user with write-access rights in the triplestore. |
| password | `string` or `null` |  | string |  | The password of a user with write-access rights to the triplestore.  It is recommended that the value of this variable is passed trough an environment variable.  By this way the password is not stored explicitely in the config file. Alternatively `?` can be used and the password will be asked interactively at run time. |
| file_server_port | `integer` or `null` |  | integer | `8000` | File server port. |
| use_file_server | `boolean` or `null` |  | boolean |  | Boolean, `False` by default.  When set to `True`: local files will be exposed through a temporary HTTP server and loaded from it.  Support for different RDF file types and their compressed version depend on the triplstore.  The benefit is the that RDF data from `file`are processed with the same protocol as those supplied through `url`.  Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported.  Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details).  This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |
| prefixes | `array` |  | string |  | No description |
| queries | `array` |  | string |  | A list of paths to files with SPARQL queries to be add to the repository user interface. Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint,  with a short timeout. The query result is not iteself checked.  Wildcard `*` can be used. |
| validations | `array` |  | string |  | A list of paths to files contining SPARQL queries used to validate the repsository. Wildcard `*` can be used. By convention, a valid result should be empty, i.e. no row is returned.  Failed results should return rows permitting to diagnose the problems. |


---

# Definitions

## GraphConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Description |
| -------- | ---- | -------- | --------------- | ----------- |
| dataset | `string` | ✅ | [`^[a-zA-Z]\w{0,31}$`](https://regex101.com/?regex=%5E%5Ba-zA-Z%5D%5Cw%7B0%2C31%7D%24) | Mandatory name of a graphs record. |
| parent | `array` or `null` |  | string | A list of name to encode dependency between datasets.  Updating the parent datset will provoke the update of its children. |
| context | `string` or `null` |  | string | IRI for 'context' in RDF4J/GraphDB terminology, or IRI for 'named graph' in RDF/SPARQL terminology.  If missing, contect IRI will be built by concataining `context_base_IRI` and `dataset` |
| system | `array` or `null` |  | string | A list of system command.  This is a simple convenience provided by kgsteward which is not meant to be a replacement  for serious Make-like system as for example git/dvc. |
| file | `array` or `null` |  | string | List of files containing RDF data.  Wildcard `*` can be used. The strategy used to load these files will depends on the `use_file_server` Boolean value.  With GraphDB, if `use_file_server` is `false` there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. With `use_file_server` set to `true` these limitations are overcomed, but see the security warning described above. |
| url | `array` or `null` |  | string | List of url from which to load RDF data |
| stamp | `array` or `null` |  | string | List of paths to files which last modification dates will used. The file contents are ignored. Wildcard `*` can be used. |
| replace | `array` or `null` |  | object | Dictionary to perform string substitution in SPARQL queries from `update` list. Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context. |
| update | `array` or `null` |  | string | List of files containing SPARQL update commands.  Wildcard `*`can be used. |
| zenodo | `array` or `null` |  | integer | Do not use! Fetch turtle files from zenodo.  This is a completely ad hoc command developped for ENPKG (), that will be suppressed sooner or later |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).
