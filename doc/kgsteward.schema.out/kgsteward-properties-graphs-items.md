# Untitled object in undefined Schema

```txt
https://example.com/schema.json#/properties/graphs/items
```



| Abstract            | Extensible | Status         | Identifiable | Custom Properties | Additional Properties | Access Restrictions | Defined In                                                                        |
| :------------------ | :--------- | :------------- | :----------- | :---------------- | :-------------------- | :------------------ | :-------------------------------------------------------------------------------- |
| Can be instantiated | No         | Unknown status | No           | Forbidden         | Allowed               | none                | [kgsteward.schema.json\*](../../out/kgsteward.schema.json "open original schema") |

## items Type

`object` ([Details](kgsteward-properties-graphs-items.md))

# items Properties

| Property                                        | Type     | Required | Nullable       | Defined by                                                                                                                                                                         |
| :---------------------------------------------- | :------- | :------- | :------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [dataset](#dataset)                             | `string` | Required | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-dataset.md "https://example.com/schema.json#/properties/graphs/items/properties/dataset")                           |
| [parent](#parent)                               | `string` | Optional | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-parent.md "https://example.com/schema.json#/properties/graphs/items/properties/parent")                             |
| [target\_graph\_context](#target_graph_context) | `string` | Optional | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-target_graph_context.md "https://example.com/schema.json#/properties/graphs/items/properties/target_graph_context") |
| [system](#system)                               | `array`  | Optional | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-system.md "https://example.com/schema.json#/properties/graphs/items/properties/system")                             |
| [file](#file)                                   | `array`  | Optional | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-file.md "https://example.com/schema.json#/properties/graphs/items/properties/file")                                 |
| [url](#url)                                     | `array`  | Optional | cannot be null | [Untitled schema](kgsteward-properties-graphs-items-properties-url.md "https://example.com/schema.json#/properties/graphs/items/properties/url")                                   |

## dataset

Mandatory name for this record. If `file`, `url`, `zenodo` or `update` are supplied, `TARGET_GRAPH_CONTEXT` will be created  as a RDF named graph/context by concataining `<dataset_base_IRI>` and `<dataset>`.

`dataset`

* is required

* Type: `string` ([dataset](kgsteward-properties-graphs-items-properties-dataset.md))

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-dataset.md "https://example.com/schema.json#/properties/graphs/items/properties/dataset")

### dataset Type

`string` ([dataset](kgsteward-properties-graphs-items-properties-dataset.md))

## parent

A comma-separated list of previously encountered dataset names

`parent`

* is optional

* Type: `string` ([parent](kgsteward-properties-graphs-items-properties-parent.md))

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-parent.md "https://example.com/schema.json#/properties/graphs/items/properties/parent")

### parent Type

`string` ([parent](kgsteward-properties-graphs-items-properties-parent.md))

## target\_graph\_context

An optional IRI for named graph, that overloads the default concatanation of `<dataset_base_IRI>` and `<dataset>`

`target_graph_context`

* is optional

* Type: `string` ([target\_graph\_context](kgsteward-properties-graphs-items-properties-target_graph_context.md))

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-target_graph_context.md "https://example.com/schema.json#/properties/graphs/items/properties/target_graph_context")

### target\_graph\_context Type

`string` ([target\_graph\_context](kgsteward-properties-graphs-items-properties-target_graph_context.md))

## system



`system`

* is optional

* Type: `string[]`

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-system.md "https://example.com/schema.json#/properties/graphs/items/properties/system")

### system Type

`string[]`

### system Constraints

**minimum number of items**: the minimum number of items for this array is: `1`

## file



`file`

* is optional

* Type: `string[]`

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-file.md "https://example.com/schema.json#/properties/graphs/items/properties/file")

### file Type

`string[]`

### file Constraints

**minimum number of items**: the minimum number of items for this array is: `1`

## url



`url`

* is optional

* Type: `string[]`

* cannot be null

* defined in: [Untitled schema](kgsteward-properties-graphs-items-properties-url.md "https://example.com/schema.json#/properties/graphs/items/properties/url")

### url Type

`string[]`

### url Constraints

**minimum number of items**: the minimum number of items for this array is: `1`
