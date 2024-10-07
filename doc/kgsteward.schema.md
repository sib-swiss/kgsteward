# KGStewardConf

This is main description

### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| repository_id | `string` | ✅ | [`\w+`](https://regex101.com/?regex=%5Cw%2B) |  |  | The name of the repository (graphdb) or dataset (fuseki) in the triplestore. |  |
| graphs | `array` | ✅ | [GraphConf](#graphconf) and/or object |  |  |  |  |
| server_brand | `string` |  | string |  | `"graphdb"` | One of 'graphdb' or 'fuseki' ( 'graphdb' by default). |  |
| server_url | `string` |  | string |  | `"http://localhost:7200"` | URL of the server. The SPARL endpoint is different and server specific. |  |
| context_base_IRI | `string` |  | string |  | `"http://example.org/context/"` |  |  |
| dataset_graph_IRI | `string` |  | string |  |  |  |  |
| setup_graph_IRI | `string` |  | string |  |  |  |  |
| username | `string` or `null` |  | string |  |  |  |  |
| password | `string` or `null` |  | string |  |  |  |  |
| file_server_port | `integer` or `null` |  | integer |  | `8000` |  |  |
| use_file_server | `boolean` or `null` |  | boolean |  |  |  |  |
| prefixes | `array` |  | string |  |  |  |  |
| queries | `array` |  | string |  |  |  |  |
| validations | `array` |  | string |  |  |  |  |


---

# Definitions

## GraphConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Deprecated | Default | Description | Examples |
| -------- | ---- | -------- | --------------- | ---------- | ------- | ----------- | -------- |
| dataset | `string` | ✅ | [`[a-zA-Z]\w{0,31}`](https://regex101.com/?regex=%5Ba-zA-Z%5D%5Cw%7B0%2C31%7D) |  |  | Mandatory name of a graphs record. |  |
| parent | `array` or `null` |  | string |  |  | A list of name to encode dependency between datasets. 
Updating the parent datset will provoke the update of its children. |  |
| context | `string` or `null` |  | string |  |  | IRI for 'context' in RDF4J/GraphDB terminology, or IRI for 'named graph' in RDF/SPARQL terminology. 
If missing, contect IRI will be built by concataining `context_base_IRI` and `dataset` |  |
| system | `array` or `null` |  | string |  |  | A list of system command. 
This is a simple convenience provided by kgsteward which is not meant to be a replacement 
for serious Make-like system as for example git/dvc. |  |
| file | `array` or `null` |  | string |  |  | Optional list of files containing RDF data. 
Wild card "*" can be used.
The strategy used to load these files will depends on the `use_file_server` Boolean value. 
With GraphDB, if `use_file_server` is `false` there might be a maximum file size (200 MB by default (?)) and compressed files may not be supported. With `use_file_server` set to `true` these limitations are overcomed, but see the security warning described above. |  |
| url | `array` or `null` |  | string |  |  | Optional list of url from which to load RDF data |  |
| stamp | `array` or `null` |  | string |  |  | Optional list of paths to files which last modification dates will used.
The file contents are ignored.
Wild card "*" can be used. |  |
| replace | `array` or `null` |  | object |  |  | Optional dictionary to perform string substitution in SPARQL queries from `update` list.
Of uttermost interest is the `${TARGET_GRAPH_CONTEXT}` which permit to restrict updates to the current context. |  |
| update | `array` or `null` |  | string |  |  | Optional list files containing SPARQL update commands. 
Wild card `*` can be supplied in the path. |  |
| zenodo | `array` or `null` |  | integer |  |  | Do not use!
Fetch turtle files from zenodo. 
This is a completely ad hoc command developped for ENPKG (), that will be suppressed sooner or later |  |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).
