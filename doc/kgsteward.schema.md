This is the JSON schema to validate YAML files for kgstweard

## Properties

| Property     | Type                | Required | Description                                                                                                                                                                                                                                     |
|--------------|---------------------|----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `graphs`     | [object](#graphs)[] | **Yes**  |                                                                                                                                                                                                                                                 |
| `server_url` | string              | **Yes**  | The server URL. This key is stored in the execution environment and can be accessed through  `${server_url}`. `endpoint` is a deprecated synonym for `server_url` which is misleading as the real SPARQL endpoint location depend on the store. |

## graphs

### Properties

| Property               | Type     | Required | Description                                                                                                                                                                                                     |
|------------------------|----------|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `dataset`              | string   | **Yes**  | Mandatory name for this record. If `file`, `url`, `zenodo` or `update` are supplied, `TARGET_GRAPH_CONTEXT` will be created  as a RDF named graph/context by concataining `<dataset_base_IRI>` and `<dataset>`. |
| `file`                 | string[] | No       |                                                                                                                                                                                                                 |
| `parent`               | string   | No       | A comma-separated list of previously encountered dataset names                                                                                                                                                  |
| `system`               | string[] | No       |                                                                                                                                                                                                                 |
| `target_graph_context` | string   | No       | An optional IRI for named graph, that overloads the default concatanation of `<dataset_base_IRI>` and `<dataset>`                                                                                               |
| `url`                  | string[] | No       |                                                                                                                                                                                                                 |

