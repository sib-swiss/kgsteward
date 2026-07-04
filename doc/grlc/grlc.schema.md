<sup>back to [TOC](../README.md)</sup>

# grlc decorator syntax

`kgsteward` optionally understands [grlc](https://grlc.io) decorators in SPARQL
query files.

* A decorator is a line starting with `#+` (at the beginning of the line), for
example `#+ summary: Count all triples`. Because it is a SPARQL comment, the
file stays a valid SPARQL query.

* Every `#+` line in the file is collected and the remainder is parsed as a
single YAML document. A file without any `#+` line is handled exactly as
before (its query is used unchanged and only minimally documented).

* Query parameters written in grlc style (`?_name`, `?__name`, with optional
type suffixes `_iri`, `_number`, `_integer`, `_literal`, `_<prefix>_<datatype>`
or a language tag such as `_en`) receive their `defaults` value by
substitution. Parameters without a default are left as ordinary SPARQL
variables.

The recognised decorators are described below.

# GrlcDecorators

grlc decorators recognised in the `#+` comment block of a SPARQL query file

### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| summary | `string` or `null` |  | string | Short one-line summary of the query, shown next to its name. |
| description | `string` or `null` |  | string | Longer human-readable description of what the query does. |
| endpoint | `string` or `null` |  | string | SPARQL endpoint the query is meant to run against. Takes precedence over any endpoint supplied by kgsteward when documenting the query (schema:target). |
| endpoint_in_url | `boolean` or `null` |  | boolean | Whether the endpoint may be overridden through a URL parameter. grlc HTTP-API option, kept for compatibility but not reflected in the RDF documentation. |
| endpoint-method | `string` or `null` |  | `GET` `POST` | HTTP method used to send the query to the endpoint (GET or POST). grlc HTTP-API option, not reflected in the RDF documentation. |
| method | `string` or `null` |  | `GET` `POST` | HTTP method exposed by the generated API operation (GET or POST). grlc HTTP-API option, not reflected in the RDF documentation. |
| pagination | `integer` or `null` |  | integer | Page size for paginated results. grlc HTTP-API option, not reflected in the RDF documentation. |
| tags | `array` or `null` |  | string | List of tags used to group related queries. Emitted as schema:keywords. |
| defaults | `array` or `null` |  | object | List of single-key mappings giving default values for query parameters (?_name). Applied by substitution into the returned query; parameters without a default are left untouched. |
| enumerate | `array` or `null` |  | Any type | List of parameters offered as an enumerated choice. grlc HTTP-API option, not reflected in the RDF documentation. |
| transform | `object` or `null` |  | object | SPARQLTransformer structure used to reshape results. grlc option, not reflected in the RDF documentation. |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).


<sup>back to [TOC](../README.md)</sup>