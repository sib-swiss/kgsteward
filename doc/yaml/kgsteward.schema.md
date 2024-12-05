# KGStewardConf

JSON Schema missing a description, provide it using the `description` key in the root of the JSON document.

| Property | Type | Required | Possible Values | Deprecated | Default | Description |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- |
| store | `object` | ✅ | [GraphDBConf](#graphdbconf) or [FusekiConf](#fusekiconf)|  |  |  |
| graphs | `object` | ✅ | [GraphConf](#graphconf) or [GraphSource](#graphsource)|  |  | Mandatory key to specify the content of the knowledge graph in the triplestore |
| context_base_IRI | `string` |  | string|  | `"http://example.org/context/"` |  |
| queries | `array` |  | string|  |  | A list of paths to files with SPARQL queries to be add to the repository user interface. Each query is first checked for syntactic correctness by being submitted to the SPARQL endpoint,  with a short timeout. The query result is not iteself checked.  Wildcard `*` can be used. |
| validations | `array` |  | string|  |  | A list of paths to files contining SPARQL queries used to validate the repsository. Wildcard `*` can be used. By convention, a valid result should be empty, i.e. no row is returned.  Failed results should return rows permitting to diagnose the problems. |


---

# Definitions



## FusekiConf



**Type:** `object`

| Property | Type | Required | Possible Values | Deprecated | Default | Description |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- |
| server_brand | `string` | ✅ | `fuseki`|  |  | No description |
| repository | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24)|  |  | The name of the 'repository' (GraphDB naming) or 'dataset' (fuseki) in the triplestore. |
| server_url | `string` |  | string|  | `"http://localhost:3030"` | URL of the server. The SPARL endpoint is different and server specific. |
| file_server_port | `integer` |  | integer|  |  | Integer, `0` by default, i.e. the file server is turned off.  When set to a positive integer, say `8000`, local files will be exposed through a temporary  HTTP server and loaded from it. Support for different RDF file types and their compressed  version depend on the tripelstore. The benefit is the that RDF data from `file` are processed  with the same protocol as those supplied remotely through `url`. Essentially for GraphDB,  file-size limits are suppressed and compressed formats are supported.  Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details).  This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |


## GraphConf



**Type:** `object`

| Property | Type | Required | Possible Values | Deprecated | Default | Description |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- |
| name | `string` | ✅ | [`^[a-zA-Z]\w{0,31}$`](https://regex101.com/?regex=%5E%5Ba-zA-Z%5D%5Cw%7B0%2C31%7D%24)|  |  | Mandatory name of a graphs record. |
| parent | `array` |  | string|  |  | A list of name to encode dependency between datasets.  Updating the parent datset will provoke the update of its children. |
| context | `string` |  | string|  |  | IRI for 'context' in RDF4J/GraphDB terminology, or IRI for 'named graph' in RDF/SPARQL terminology.  If missing, contect IRI will be built by concataining `context_base_IRI` and `name` |
| system | `array` |  | string|  |  | A list of system command.  This is a simple convenience provided by kgsteward which is not meant to be a replacement  for serious Make-like system as for example git/dvc. |
| file | `array` |  | string|  |  | List of files containing RDF data.  Wildcard `*` can be used. The strategy used to load these files will depends on if a file server is used (see `file_server_port` option`).  With GraphDB, there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported.  Using a file server, these limitations are overcomed, but see the security warning described above. |
| url | `array` |  | string|  |  | List of url from which to load RDF data |
| stamp | `array` |  | string|  |  | List of paths to files which last modification dates will used. The file contents are ignored. Wildcard `*` can be used. |
| replace | `array` |  | string|  |  | Dictionary to perform string substitution in SPARQL queries from `update` list. Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context. |
| update | `array` |  | string|  |  | List of files containing SPARQL update commands.  Wildcard `*`can be used. |
| zenodo | `array` |  | integer|  |  | Do not use! Fetch turtle files from zenodo.  This is a completely ad hoc command developped for ENPKG (), that will be suppressed sooner or later |


## GraphDBConf



**Type:** `object`

| Property | Type | Required | Possible Values | Deprecated | Default | Description |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- |
| server_brand | `string` | ✅ | `graphdb`|  |  | One of 'graphdb' or 'fuseki' ( 'graphdb' by default). |
| server_config | `string` | ✅ | string|  |  | Filename with the triplestore configuration, possibly a turtle file.  `graphdb_config` is a deprecated synonym.  This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively,  thus permitting to reproduce the repository configuration elsewhere.  This file is used by the `-I` and `-F` options.  Beware that the repository ID could be hard-coded in the config file and  should be maintained in sync with `repository`. |
| repository | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24)|  |  | The name of the 'repository' (GraphDB naming) or 'dataset' (fuseki) in the triplestore. |
| server_url | `string` |  | string|  | `"http://localhost:7200"` | URL of the server. The SPARL endpoint is different and server specific. |
| file_server_port | `integer` |  | integer|  |  | Integer, `0` by default, i.e. the file server is turned off.  When set to a positive integer, say `8000`, local files will be exposed through a temporary  HTTP server and loaded from it. Support for different RDF file types and their compressed  version depend on the tripelstore. The benefit is the that RDF data from `file` are processed  with the same protocol as those supplied remotely through `url`. Essentially for GraphDB,  file-size limits are suppressed and compressed formats are supported.  Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details).  This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |
| username | `string` |  | string|  |  | The name of a user with write-access rights in the triplestore. |
| password | `string` |  | string|  |  | The password of a user with write-access rights to the triplestore.  It is recommended that the value of this variable is passed trough an environment variable.  By this way the password is not stored explicitely in the config file. Alternatively `?` can be used and the password will be asked interactively at run time. |
| prefixes | `array` |  | string|  |  | No description |


## GraphSource



**Type:** `object`

| Property | Type | Required | Possible Values | Deprecated | Default | Description |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- |
| source | `string` | ✅ | string|  |  |  |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown) 0.2.1 on 2024-11-19 17:00:48.