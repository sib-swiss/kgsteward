<sup>back to [TOC](../README.md)</sup>

# YAML syntax of kgsteward config file (version 2)

## Preambule
            
* YAML 1.1 syntax is supported. 

* A single YAML extension is supported: `!include <filename>`. 
This directive will insert in place the content of `filename`.
The path of `<filename>` is interpreted with the directory of the parent YAML file as default directory. 
This inclusion mechanism is executed early, before the YAML configuration is validated.  

* Within the YAM config file(s), UNIX environment variables can by referred to using `${...}` syntax. 
Evaluation of these is performed late, i.e. at the time of command execution. 
Hence `${...}` syntax cannot be used in `!include` directive.
The use of UNIX environment variables is recommended to ensure portability of the YAML config file(s).
These variable are usually encoded with uppercase strings.

* In addition to UNIX environment variables, `kgsteward` creates temporary variables reflecting the content of the YAML config file.
For example `${kgsteward_server_brand}` contains the ... server brand, e.g. `graphdb`.
The most useful of these variables is certainly `${kgsteward_dataset_context"}` that contains the IRI of the current target context.
These variable are encoded with lowercase strings.

* The terminology adopted here is a compromise. Different server brands utilise different namings for the same concept. 
For example, 'context' in RDF4J/GraphDB terminology is the same as 'named graph' in RDF/SPARQL terminology.
In this respect, `kgsteward` utilises 'context', because of the too many usages of '[graph](https://en.wikipedia.org/wiki/Graph)'.  

## YAML syntax

The entry point (top level keys) is [KGStewardConf](#kgstewardconf).

# KGStewardConf

Top level YAML keys

### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| version | `const` | ✅ | `kgsteward_yaml_2` | This mandatory fixed value determines the admissible YAML syntax |
| server | `object` | ✅ | [FusekiConf](#fusekiconf) or [GraphDBConf](#graphdbconf) or [RDF4JConf](#rdf4jconf) |  |
| file_loader | `object` | ✅ | [HttpServerFileLoader](#httpserverfileloader) and/or [RiotChunkStoreFileLoader](#riotchunkstorefileloader) and/or [SparqlFileLoader](#sparqlfileloader) and/or [StoreFileLoader](#storefileloader) |  |
| url_loader | `object` | ✅ | [CurlRiotChunkStoreUrlLoader](#curlriotchunkstoreurlloader) and/or [SparqlUrlLoader](#sparqlurlloader) |  |
| dataset | `array` | ✅ | [DatasetConf](#datasetconf) | Mandatory key to specify the content of the knowledge graph in the triplestore. |
| context_base_IRI | `string` | ✅ | string | Base IRI to construct the graph context. In doubt, give `http://example.org/context/` a try. |
| queries | `array` or `null` | ✅ | [QueryConf](#queryconf) | Structured list of SPARQL queries. |
| validations | `array` or `null` |  | string | A list of paths to files contining SPARQL queries used to validate the repository. Wildcards `*` can be used. By convention, a valid result should be empty, i.e. no row is returned. Failed results should return rows permitting to diagnose the problems. |


---

# Definitions

## CurlRiotChunkStoreUrlLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| method | `const` | ✅ | `curl_riot_chunk_store` |  | URL are downloaded using curl to a temporary file, which is then loaded with `riot_chunk_store` method. |
| tmp_dir | `string` or `null` |  | string | `"/tmp"` | temporary directory |
| size | `integer` or `null` |  | integer | `100000000` | chunk size |

## DatasetConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| name | `string` | ✅ | [`^[a-zA-Z]\w{0,31}$`](https://regex101.com/?regex=%5E%5Ba-zA-Z%5D%5Cw%7B0%2C31%7D%24) | Mandatory name of a dataset record. |
| context | `string` or `null` |  | string | The IRI of the target context. If missing, it will be built by concataining `context_base_IRI` and `name`. |
| parent | `array` or `null` |  | string | A list of dataset names to declare dependency between dataset records. Updating the parent datset will provoke the update of its children, unless it is frozen. |
| frozen | `boolean` or `null` |  | boolean | Frozen record, can only be updated explicitely with the `-d <name>` option. The option `-C` has no effect |
| system | `array` or `null` |  | string | A list of system command. This is a simple convenience provided by kgsteward, which is not meant to be a replacement for serious Make-like system as for example git/dvc. |
| file | `array` or `null` |  | string | List of files containing RDF data. Wildcards `*` can be used. The strategy used to load these files will depends on if a file server is used (see `file_server_port` option`). With GraphDB, there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. Using a file server, these limitations are overcome, but see the security warning described above. |
| url | `array` or `null` |  | string | List of url from which to load RDF data |
| stamp | `array` or `null` |  | string | List of file paths or URLs to which last modification dates will used. The file contents are ignored. Wildcards `*` can be used. |
| replace | `object` or `null` |  | object | Dictionary to perform string substitution in SPARQL queries from `update` list. Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context. |
| update | `array` or `null` |  | string | List of files containing SPARQL update commands. Wildcards are not recommended here, as the order of the SPARQL updates possibly matters! |
| zenodo | `array` or `null` |  | integer | Do not use! Fetch turtle files from zenodo. This is a completely ad hoc command developed for ENPKG, that will be suppressed sooner or later. |
| special | `array` or `null` |  | [SpecialEnum](#specialenum) | A list of special dataset records. Supported values are "sib_swiss_void". |

## FusekiConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| brand | `const` | ✅ | `fuseki` | String identifying the server brand. One of 'graphdb', 'rdf4j', 'fuseki' |
| location | `string` | ✅ | string | URL of the server. The SPARQL endpoint locations for queries, updates and stores are specific to a server brand. Fuseki has location 'http://localhost:3030' by default |
| repository | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24) | The name of the 'repository' (GraphDB/RDF4J naming) or 'dataset' (fuseki) in the triplestore. |
| file_server_port | `integer` or `null` |  | integer | Integer, `0` by default, i.e. the file server is turned off. When set to a positive integer, say `8000`, local files will be exposed through a temporary HTTP server and loaded from it. Support for different RDF file types and their compressed version depend on the tripelstore. The benefit is the that RDF data from `file` are processed with the same protocol as those supplied remotely through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |

## GraphDBConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| brand | `const` | ✅ | `graphdb` | String identifying the server brand. One of 'graphdb', 'rdf4j', 'fuseki' |
| location | `string` | ✅ | string | URL of the server. The SPARQL endpoint locations for queries, updates and stores are specific to a server brand. GraphDB has location 'http://localhost:7200' by default |
| server_config | `string` | ✅ | string | Filename with the triplestore configuration, possibly a turtle file. This file can be saved from the UI interface of RDF4J/GraphDB after a first repository was created interactively, thus permitting to reproduce the repository configuration elsewhere. This file is used by the `-I` and `-F` options. Beware that the repository ID could be hard-coded in the config file and should be maintained in sync with `repository`. |
| repository | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24) | The name of the 'repository' (GraphDB/RDF4J naming) or 'dataset' (fuseki) in the triplestore. |
| file_server_port | `integer` or `null` |  | integer | Integer, `0` by default, i.e. the file server is turned off. When set to a positive integer, say `8000`, local files will be exposed through a temporary HTTP server and loaded from it. Support for different RDF file types and their compressed version depend on the tripelstore. The benefit is the that RDF data from `file` are processed with the same protocol as those supplied remotely through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |
| username | `string` or `null` |  | string | The name of a user with write-access rights in the triplestore. |
| password | `string` or `null` |  | string | The password of a user with write-access rights to the triplestore. It is recommended that the value of this variable is passed trough an environment variable. By this way the password is not stored explicitely in the config file. Alternatively `?` can be used and the password will be asked interactively at run time. |
| prefixes | `array` or `null` |  | string | A list of Turtle files from which prefix definitions can be obtained.         This list will used to update the namespace definitions in GraphDB and RDF4J.         Otherwise it is ignored |

## HttpServerFileLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| method | `const` | ✅ | `http_server` |  | Files are exposed through a temporary HTTP server. This is the recommended method with GraphDB. |
| port | `integer` or `null` |  | integer | `8000` | Integer, `0` by default, i.e. the file server is turned off. When set to a positive integer, say `8000`, local files will be exposed through a temporary HTTP server and loaded from it. Support for different RDF file types and their compressed version depend on the tripelstore. The benefit is the that RDF data from `file` are processed with the same protocol as those supplied remotely through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |

## QueryConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| name | `string` | ✅ | [`^[a-zA-Z]\w{0,31}$`](https://regex101.com/?regex=%5E%5Ba-zA-Z%5D%5Cw%7B0%2C31%7D%24) |  | Mandatory name of a set queries |
| system | `array` or `null` |  | string |  | A list of system command. This is a simple convenience provided by kgsteward, which is not meant to be a replacement for serious Make-like system as for example git/dvc. |
| test | `object` or `null` |  | [TestConf](#testconf) |  | assert nothing/something |
| public | `boolean` or `null` |  | boolean | `true` | no description |
| file | `array` or `null` |  | string |  | List of files containing one SPARQL query each. Wildcards `*` can be used, and implied file names will be sorted alphabetically. The file name of each file is interpreted as the query label. In each file, lines starting with "#" are considered as the query documentation (comment) |

## RDF4JConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| brand | `const` | ✅ | `rdf4j` | String identifying the server brand. One of 'graphdb', 'rdf4j', 'fuseki' |
| location | `string` | ✅ | string | URL of the server. The SPARQL endpoint locations for queries, updates and stores are specific to a server brand. RDF4J has location 'http://localhost:8080' by default |
| repository | `string` | ✅ | [`^\w{1,32}$`](https://regex101.com/?regex=%5E%5Cw%7B1%2C32%7D%24) | The name of the 'repository' (GraphDB/RDF4J naming) or 'dataset' (fuseki) in the triplestore. |
| file_server_port | `integer` or `null` |  | integer | Integer, `0` by default, i.e. the file server is turned off. When set to a positive integer, say `8000`, local files will be exposed through a temporary HTTP server and loaded from it. Support for different RDF file types and their compressed version depend on the tripelstore. The benefit is the that RDF data from `file` are processed with the same protocol as those supplied remotely through `url`. Essentially for GraphDB, file-size limits are suppressed and compressed formats are supported. Beware that the used python-based server is potentially insecure (see [here](https://docs.python.org/3/library/http.server.html) for details). This should however pose no real treat if used on a personal computer or on a server that is behind a firewall. |

## RiotChunkStoreFileLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| method | `const` | ✅ | `riot_chunk_store` |  | riot_chunk_store |
| size | `integer` or `null` |  | integer | `100000000` | chunk size |

## SparqlFileLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| method | `const` | ✅ | `sparql_load` | Files are loaded using the SPARQL update statement: "LOAD <file://<file-path> INTO...". This strategy is likely to failed for large files, or worst silently truncate them. |

## SparqlUrlLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| method | `const` | ✅ | `sparql_load` | URL are loaded using the SPARQL update statement: "LOAD <url> INTO...". This strategy could fail for large files, or worst silently truncate them. |

## SpecialEnum

No description provided for this model.

#### Type: `string`

**Possible Values:** `sib_swiss_void` or `sib_swiss_prefix` or `sib_swiss_query`

## StoreFileLoader

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| method | `const` | ✅ | `file_store` | Files are loaded using the graph store protocol. This strategy is likely to failed for large files, or worst silently truncate them. |

## TestConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| min_row_count | `integer` or `null` |  | integer |  |
| max_row_count | `integer` or `null` |  | integer |  |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).


<sup>back to [TOC](../README.md)</sup>