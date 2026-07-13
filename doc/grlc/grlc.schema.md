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
| summary | `string` or `null` |  | string | Short one-line summary of the query, shown next to its name. Mandatory when a query uses grlc notation. Emitted as rdfs:label. |
| description | `string` or `null` |  | string | Longer human-readable description of what the query does. Emitted as rdfs:comment (falls back to summary when absent). |
| endpoint | `string` or `null` |  | string | SPARQL endpoint the query is meant to run against. Takes precedence over any endpoint supplied by kgsteward when documenting the query (schema:target). |
| endpoint_in_url | `boolean` or `null` |  | boolean | Whether the endpoint may be overridden through a URL parameter. grlc HTTP-API option, not reflected in the RDF documentation. |
| endpoint-method | `string` or `null` |  | `GET` `POST` | HTTP method used to send the query to the endpoint (GET or POST). grlc HTTP-API option, not reflected in the RDF documentation. |
| method | `string` or `null` |  | `GET` `POST` | HTTP method exposed by the generated API operation (GET or POST). grlc HTTP-API option, not reflected in the RDF documentation. |
| pagination | `integer` or `null` |  | integer | Page size for paginated results. grlc HTTP-API option, not reflected in the RDF documentation. |
| tags | `array` or `null` |  | string | List of tags used to group related queries. Emitted as schema:keywords. |
| defaults | `array` or `null` |  | object | List of single-key mappings giving default values for grlc parameters (?_name). Applied by substitution into the returned query; parameters without a default are left untouched. |
| enumerate | `array` or `null` |  | object | List of parameters offered as an enumerated choice. grlc HTTP-API option, not reflected in the RDF documentation. |
| transform | `object` or `null` |  | object | SPARQLTransformer structure used to reshape results. grlc option, not reflected in the RDF documentation. |
| source | `string` or `null` |  | string | Provenance of the query (e.g. an upstream sparql-examples file). Emitted as dct:source. |
| citation | `string` or `null` |  | string | Bibliographic citation to credit when using the query. Emitted as schema:citation. |
| param | `array` or `null` |  | object | Standalone parameter mechanism (list of single-key mappings). Recognised and preserved; substitution semantics are left to the parameter mechanism. |
| selector | `array` or `null` |  | [AutocompleteWidget](#autocompletewidget) or [CheckboxWidget](#checkboxwidget) or [SelectWidget](#selectwidget) or [SliderWidget](#sliderwidget) or [TextWidget](#textwidget) | Reusable input widgets that populate form fields. Declared on the query that provides the option values. |
| form | `array` or `null` |  | [FormFieldConf](#formfieldconf) | Declares this query as a dynamic input form: a list of string substitutions, each binding a target string to a selector widget. |


---

# Definitions

## AutocompleteWidget

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| id | `string` | ✅ | string |  | Widget identifier, minted as kgsteward:<id>. |
| prompt | `string` | ✅ | string |  | Human-readable label shown for the widget (kgsteward:prompt). |
| options | `string` or `null` |  | string |  | Name of the query returning the option rows. Defaults to the query the selector is declared on (kgsteward:selectQuery). |
| valueIndex | `integer` or `string` |  | integer and/or string | `1` | 1-based column of the option query's projection used as the value. A string is interpreted as a variable name (emitted as kgsteward:valueVar). |
| nameIndex | `integer` or `string` |  | integer and/or string | `2` | 1-based column of the option query's projection used as the label. A string is interpreted as a variable name (emitted as kgsteward:nameVar). |
| type | `const` |  | `autocomplete` | `"autocomplete"` | Widget kind: select, checkbox, autocomplete (all query-backed), text (free text, optional regexp) or slider (numeric range). |

## CheckboxWidget

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| id | `string` | ✅ | string |  | Widget identifier, minted as kgsteward:<id>. |
| prompt | `string` | ✅ | string |  | Human-readable label shown for the widget (kgsteward:prompt). |
| options | `string` or `null` |  | string |  | Name of the query returning the option rows. Defaults to the query the selector is declared on (kgsteward:selectQuery). |
| valueIndex | `integer` or `string` |  | integer and/or string | `1` | 1-based column of the option query's projection used as the value. A string is interpreted as a variable name (emitted as kgsteward:valueVar). |
| nameIndex | `integer` or `string` |  | integer and/or string | `2` | 1-based column of the option query's projection used as the label. A string is interpreted as a variable name (emitted as kgsteward:nameVar). |
| type | `const` |  | `checkbox` | `"checkbox"` | Widget kind: select, checkbox, autocomplete (all query-backed), text (free text, optional regexp) or slider (numeric range). |

## FormFieldConf

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ----------- |
| target | `string` | ✅ | string | Verbatim string in the query body to be replaced (kgsteward:targetStr). |
| widget | `string` | ✅ | string | Identifier of the selector widget providing the value (kgsteward:replaceWith). |
| default | `string` or `null` |  | string | Optional default value used when the field is left unset (kgsteward:default). |

## SelectWidget

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| id | `string` | ✅ | string |  | Widget identifier, minted as kgsteward:<id>. |
| prompt | `string` | ✅ | string |  | Human-readable label shown for the widget (kgsteward:prompt). |
| options | `string` or `null` |  | string |  | Name of the query returning the option rows. Defaults to the query the selector is declared on (kgsteward:selectQuery). |
| valueIndex | `integer` or `string` |  | integer and/or string | `1` | 1-based column of the option query's projection used as the value. A string is interpreted as a variable name (emitted as kgsteward:valueVar). |
| nameIndex | `integer` or `string` |  | integer and/or string | `2` | 1-based column of the option query's projection used as the label. A string is interpreted as a variable name (emitted as kgsteward:nameVar). |
| type | `const` |  | `select` | `"select"` | Widget kind: select, checkbox, autocomplete (all query-backed), text (free text, optional regexp) or slider (numeric range). |

## SliderWidget

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| id | `string` | ✅ | string |  | Widget identifier, minted as kgsteward:<id>. |
| prompt | `string` | ✅ | string |  | Human-readable label shown for the widget (kgsteward:prompt). |
| min | `number` | ✅ | number |  | Lower bound of a slider (kgsteward:min). |
| max | `number` | ✅ | number |  | Upper bound of a slider (kgsteward:max). |
| type | `const` |  | `slider` | `"slider"` | Widget kind: select, checkbox, autocomplete (all query-backed), text (free text, optional regexp) or slider (numeric range). |
| step | `number` |  | number | `1` | Step of a slider (kgsteward:step). |

## TextWidget

No description provided for this model.

#### Type: `object`

| Property | Type | Required | Possible values | Default |&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Description&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|
| -------- | ---- | -------- | --------------- | ------- | ----------- |
| id | `string` | ✅ | string |  | Widget identifier, minted as kgsteward:<id>. |
| prompt | `string` | ✅ | string |  | Human-readable label shown for the widget (kgsteward:prompt). |
| type | `const` |  | `text` | `"text"` | Widget kind: select, checkbox, autocomplete (all query-backed), text (free text, optional regexp) or slider (numeric range). |
| pattern | `string` or `null` |  | string |  | Regular expression validating a free-text field (text widget only; kgsteward:pattern). |


---

Markdown generated with [jsonschema-markdown](https://github.com/elisiariocouto/jsonschema-markdown).


<sup>back to [TOC](../README.md)</sup>