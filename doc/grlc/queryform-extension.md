# grlc extension proposal: query-form decorators

Status: **draft / for discussion** — open questions resolved 2026-07-04, see §8.
Scope: an *extension* to the [grlc](https://grlc.io) decorator set that lets a
plain SPARQL query file declare a **dynamic input form** and the **selector
widgets** that populate it, so that a machine-readable RDF description of the
form is generated automatically while the query is parsed.

The generated RDF extends the **kgsteward vocabulary**
(`https://purl.expasy.org/kgsteward/`) and is merged into the same
documentation graph kgsteward already builds from the standard
grlc/sparql-examples decorators. It reproduces the structure ReconXKG currently
maintains by hand in `sparql/query/query_forms.ttl`.

---

## 1. Motivation

Standard grlc parameterises a query through `?_name` variables exposed as
Web-API query-string parameters, optionally with `defaults` and a flat
`enumerate` list. That is enough for a REST call, but not for an interactive
form where:

* a parameter's admissible values are the **result of another query** (e.g.
  "pick one of the metabolic networks currently loaded"),
* one option query feeds **several** forms (widgets are reusable),
* the substituted token is an **arbitrary string** in the query body (an IRI, a
  prefixed name, a filter constant) rather than a `?_name` variable, and
* the UI needs a **prompt**, a **widget kind** (single vs. multiple choice), and
  which result columns are the **value** and the **label**.

ReconXKG expresses all of this in RDF by hand in `query_forms.ttl`. This
proposal makes that RDF a **by-product of parsing decorators**, so the form
description cannot drift from the queries it refers to.

## 2. Relationship to existing grlc decorators

| concern | standard grlc | this extension |
| --- | --- | --- |
| substitution unit | `?_name` variable | arbitrary literal string (`targetStr`) |
| option source | static `enumerate` list | another query (`selector` → `selectQuery`) |
| reuse across queries | none | named widgets referenced by IRI |
| output | OpenAPI parameter | `kgsteward:` form RDF |

The extension is **additive**: the two new keys (`selector`, `form`) sit
alongside `summary`, `tags`, `defaults`, … and are ignored by a grlc that does
not understand them (they already survive today via `extra='allow'`).

## 3. Generated vocabulary

The terms **extend the kgsteward vocabulary** rather than introduce a separate
namespace (resolves Q1). `kgsteward:` = `https://purl.expasy.org/kgsteward/`,
the same namespace as `kgsteward:Dataset`, `kgsteward:checksum`, …

Form classes: `kgsteward:InputForm`.
Widget classes: `kgsteward:SelectParam`, `kgsteward:CheckboxParam`,
`kgsteward:AutocompleteParam`, `kgsteward:TextParam`, `kgsteward:SliderParam`
(the last provisional).
Properties: `kgsteward:prompt`, `kgsteward:selectQuery`,
`kgsteward:valueIndex`, `kgsteward:nameIndex` (column numbers) or
`kgsteward:valueVar`, `kgsteward:nameVar` (variable names, optional),
`kgsteward:pattern` (regexp validation), `kgsteward:min`, `kgsteward:max`,
`kgsteward:step` (slider bounds), `kgsteward:inputField`,
`kgsteward:targetStr`, `kgsteward:replaceWith`, `kgsteward:default`.

```
kgsteward:<widget> a kgsteward:SelectParam | kgsteward:CheckboxParam ;
    kgsteward:prompt      "…" ;
    kgsteward:selectQuery kgsteward:<options-query> ;
    kgsteward:valueIndex  <int> ;          # or kgsteward:valueVar "var"
    kgsteward:nameIndex   <int> .          # or kgsteward:nameVar  "var"

kgsteward:form_<query> a kgsteward:InputForm ;
    kgsteward:selectQuery kgsteward:<query> ;
    kgsteward:inputField ( [ kgsteward:targetStr  "…" ;
                             kgsteward:replaceWith kgsteward:<widget> ;
                             kgsteward:default     "…" ] … ) .   # default optional
```

Widget/query IRIs are `kgsteward:<name>`; form IRIs are `kgsteward:form_<name>`,
where `<name>` is the filename-derived query name kgsteward already computes.

## 4. New decorators

### 4.1 `selector` — declare reusable widget(s)

Named, reusable widgets only (resolves Q2 — no anonymous inline widgets). A
query-backed widget is placed on the **option query**, so `options` defaults to
*this* query.

```yaml
#+ selector:
#+   - id: select_one_MNet          # query-backed, single choice
#+     type: select
#+     prompt: Select a MNet
#+     valueIndex: 1                 # 1-based column of the option query's projection
#+     nameIndex: 2
#+   - id: pick_chebi                # free text + query-backed suggestions
#+     type: autocomplete
#+     prompt: ChEBI identifier
#+     options: list_chebi
#+     valueIndex: 1
#+     nameIndex: 2
#+   - id: enter_ec                  # free text, validated
#+     type: text
#+     prompt: EC number
#+     pattern: "^[0-9]+(\\.[0-9]+){3}$"
#+   - id: pick_threshold            # numeric range (provisional)
#+     type: slider
#+     prompt: Similarity threshold
#+     min: 0
#+     max: 1
#+     step: 0.05
```

**Common fields** (every widget):

| field | type | default | meaning |
| --- | --- | --- | --- |
| `id` | string | *required* | widget identifier → `kgsteward:<id>` |
| `type` | see catalogue | `select` | selects the widget class + its extra fields |
| `prompt` | string | *required* | `kgsteward:prompt` |

**Widget catalogue** — `type` discriminates the class and its extra fields:

| `type` | class | extra fields | purpose |
| --- | --- | --- | --- |
| `select` | `SelectParam` | `options`, `valueIndex`, `nameIndex` | single choice from a query |
| `checkbox` | `CheckboxParam` | `options`, `valueIndex`, `nameIndex` | multiple choice from a query |
| `autocomplete` | `AutocompleteParam` | `options`, `valueIndex`, `nameIndex` | query-backed value list, filtered type-ahead |
| `text` | `TextParam` | `pattern?` | free text, optional regexp validation |
| `slider` | `SliderParam` | `min`, `max`, `step?` | numeric range (provisional) |

Extra-field semantics:

| field | type | default | meaning |
| --- | --- | --- | --- |
| `options` | string (query name) | *this query* | `kgsteward:selectQuery` |
| `valueIndex` | int \| string | `1` | column number → `kgsteward:valueIndex`; a string is a variable name → `kgsteward:valueVar` |
| `nameIndex` | int \| string | `2` | column number → `kgsteward:nameIndex`; a string is a variable name → `kgsteward:nameVar` |
| `pattern` | string (regexp) | — | `kgsteward:pattern`, client-side validation (`text` only) |
| `min` / `max` | number | *required for slider* | `kgsteward:min` / `kgsteward:max` |
| `step` | number | `1` | `kgsteward:step` |

Column numbers are the primary, easier-to-maintain form (resolves Q3);
`valueIndex` defaults to `1`. A string value is accepted and emitted as the
`…Var` variant for robustness against projection reordering.

### 4.2 `form` — declare this query as an input form

Placed on the **query to parameterise**. Each entry is one substitution and may
carry a default value (resolves Q4).

```yaml
#+ form:
#+   - target: "reconx:vmh2_Recon"
#+     widget: select_many_MNet
#+   - target: "reconx:equaSource"
#+     widget: select_one_mapping
#+     default: "reconx:someDefaultMapping"
```

| field | type | meaning |
| --- | --- | --- |
| `target` | string | `kgsteward:targetStr` — verbatim string replaced in the query body |
| `widget` | string (selector id) | `kgsteward:replaceWith` → `kgsteward:<widget>` |
| `default` | string (optional) | `kgsteward:default` — value used when the field is left unset; also usable by the standalone parameter mechanism |

Entry order is preserved as the order of the `inputField` RDF list.

## 5. Decorator → RDF mapping

For a file whose derived name is `Q`:

* each `selector[i]` →
  * `kgsteward:<id> a kgsteward:<class>` where `<class>` is `SelectParam`,
    `CheckboxParam`, `AutocompleteParam`, `TextParam` or `SliderParam` per `type`
  * `kgsteward:prompt "<prompt>"`
  * *query-backed* (`select`/`checkbox`/`autocomplete`): `kgsteward:selectQuery kgsteward:<options or Q>`,
    and `kgsteward:valueIndex <n>^^xsd:integer` if int else `kgsteward:valueVar "<n>"` (likewise `nameIndex`/`nameVar`)
  * *validated text* (`text`): `kgsteward:pattern "<regexp>"` when given
  * *slider*: `kgsteward:min <n>`, `kgsteward:max <n>`, `kgsteward:step <n>`
* if `form` present →
  * `kgsteward:form_<Q> a kgsteward:InputForm`
  * `kgsteward:selectQuery kgsteward:<Q>`
  * `kgsteward:inputField ( b1 … bn )`, each `bk` a blank node with
    `kgsteward:targetStr "<target>"`, `kgsteward:replaceWith kgsteward:<widget>`,
    and `kgsteward:default "<default>"` when given.

Because the parser accumulates every file's triples into one graph, a form in
`report/…` and the widget it references in `list/…` resolve to the same
`kgsteward:` IRI with no explicit import.

## 6. Worked example

`sparql/query/list/list_mnet.rq`

```sparql
#+ summary: List the metabolic networks
#+ selector:
#+   - id: select_one_MNet
#+     type: select
#+     prompt: Select a MNet
#+     valueIndex: 1
#+     nameIndex: 2
SELECT ?mnet ?label WHERE { … }
```

`sparql/query/report/report_duplicated_metabolites.rq`

```sparql
#+ summary: Report duplicated metabolites within a network
#+ form:
#+   - target: "reconx:vmh_Recon"
#+     widget: select_one_MNet
SELECT … WHERE { … reconx:vmh_Recon … }
```

Parsing both (in any order) yields:

```turtle
kgsteward:select_one_MNet a kgsteward:SelectParam ;
    kgsteward:prompt "Select a MNet" ;
    kgsteward:selectQuery kgsteward:list_mnet ;
    kgsteward:valueIndex 1 ;
    kgsteward:nameIndex 2 .

kgsteward:form_report_duplicated_metabolites a kgsteward:InputForm ;
    kgsteward:selectQuery kgsteward:report_duplicated_metabolites ;
    kgsteward:inputField ( [ kgsteward:targetStr "reconx:vmh_Recon" ;
                             kgsteward:replaceWith kgsteward:select_one_MNet ] ) .
```

— i.e. `query_forms.ttl`, regenerated from the queries themselves.

## 7. Parsing / integration

* Modelled as pydantic sub-models added to `GrlcDecorators`, so the reference
  doc stays autogenerated: `FormFieldConf`, and a **discriminated union** of
  widget models keyed on `type` (`SelectParam`/`CheckboxParam`/
  `AutocompleteParam`/`TextParam`/`SliderParam`), mirroring the existing
  `server.brand` union in `yamlconfig.py`. Per-type validation is therefore
  enforced (e.g. `slider` requires `min`/`max`; `text` forbids `options`).
* The form/widget triples are added to the accumulator graph during `parse`
  (alongside the sparql-examples triples), so a single serialisation of the
  graph after all files are parsed *is* the form catalogue.
* The accumulator's `check()` should flag, across the whole set:
  * a `form … widget: X` with **no** `selector id: X` declared anywhere,
  * a `selector options:` / implicit option query name **not** among the parsed queries,
  * a **duplicate** `selector id`,
  * a `targetStr` **absent** from the referring query's body (no-op substitution).

## 8. Resolved decisions

1. **Namespace** — extend the kgsteward vocabulary (`kgsteward:`), no separate namespace. ✅
2. **Inline vs. named widgets** — named, reusable widgets only. ✅
3. **`valueIndex`/`nameIndex`** — 1-based column numbers, `valueIndex` default `1`; variable names optionally supported (emitted as `valueVar`/`nameVar`). ✅
4. **Defaults** — `form` fields may carry an optional `default` (`kgsteward:default`), shared with the standalone parameter mechanism. ✅
5. **selector placement** — *left flexible pending decision*: `options` defaults
   to the declaring query (the common "declare on the list query" case) but may
   be given explicitly, so a standalone selector is already expressible. No
   syntax is foreclosed; can be tightened later.

## 9. Widget set

Beyond the query-backed `select`/`checkbox`, the widget catalogue (§4.1) covers:

* `autocomplete` — query-backed like `select`: runs its `options` query for the
  candidate values, filtered type-ahead (same `valueIndex`/`nameIndex` contract),
* `text` — free text with optional regexp validation (`pattern`),
* `slider` — numeric range (`min`/`max`/`step`), **provisional**.

The discriminated-union model makes adding further widgets (date picker, IRI
picker, …) a matter of adding one sub-model + one class, without disturbing the
existing ones.

## 10. Roadmap / non-goals

* **v1** (this document, implemented): flat `InputForm`s, raw string
  substitution, five widgets, scalar `prompt`, optional `source`/`citation`.
* **v2** (designed, not built): language-map `prompt`/`summary`/`description`
  (§ i18n), and **cascading / inter-field dependency** — a selector's option
  query parameterised by another field's value (`kgsteward:dependsOn` /
  `filterVar`). The v1 field blank-nodes are shaped so these can be added
  without breaking the flat case.

## 11. Consumption by an MCP server

The accumulator is designed as the **single backing store** for both the
sparql-editor (via `serialize()`) and an MCP server exposing the query
catalogue — not a serialise-only artefact.

* **Discovery** — `list()` / `search(text, tags)` back the MCP
  `list_example_queries` / `search_example_queries` tools; because the
  catalogue *is* an `rdflib.Graph`, search can equally be SPARQL over
  `schema:keywords` / `rdfs:comment`. No second index.
* **LLM-driven execution** — the `form`/`selector` metadata is a machine-readable
  **parameter contract**: which strings to substitute (`targetStr`), what each
  expects (widget), and where legal values come from (`options` → a query the
  MCP can run to enumerate valid inputs). An MCP `run_example_query(name, params)`
  reports parameters, resolves allowed values by running the option queries,
  substitutes (raw string), and executes.
* **Attribution** — `source` (`dct:source`) and `citation` (`schema:citation`)
  let the MCP surface provenance as structured data rather than prose buried in
  `description`.

Design guardrail: `GrlcCatalog`'s accessors are consumable in-process (import
the catalogue, query the graph); serialisation is one output, not the only one.
```
