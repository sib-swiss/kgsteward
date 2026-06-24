<sup>back to [TOC](../README.md)</sup>

# User guide

Practical advice for running real `kgsteward` projects. For the internal
mechanics of each backend, see [triplestore drivers](../drivers/README.md);
this page is about how to work effectively, not how the drivers work.

## Maturity level

`kgsteward` as a client for GraphDB was developed over several years to gather
and manage experimental data from chemistry (LC-MS/MS) and biology
(bio-activities), together with reference chemical structures derived from
public databases (LOTUS, Wikidata). This was published in [A Sample-Centric and
Knowledge-Driven Computational Framework for Natural Products Drug
Discovery](https://doi.org/10.1021/acscentsci.3c00800). Several other complex
research projects whose RDF data are managed by `kgsteward` are currently
ongoing, including collaborations with the industry.

The Fuseki, RDF4J and qlever drivers came later and are less battle-tested than
the GraphDB one.

## Portability across stores

In a perfect world, if the content of an RDF repository is specified strictly
following W3C recommendations, one could expect to obtain the same resource
whatever the store brand, although the performances may differ. In the real
world it is a little more complicated. The examples in [first
steps](../first_steps/README.md) yield exactly the same results, but on very
small datasets.

## Develop on GraphDB, deploy where you need

A practical workflow that has worked well: **author and debug a project against
GraphDB, then point the same YAML at the production backend.**

The reason is the ingestion model (detailed in [triplestore
drivers](../drivers/README.md)). On a live backend like GraphDB each `update:`
is sent and persisted immediately, so when you iterate you see every SPARQL
statement run — and fail — at its own position, which makes locating an error in
a long update straightforward (especially with `-v`). qlever, by contrast,
stages files and queues updates for a deferred index rebuild, so the
develop-fix-rerun loop is heavier. GraphDB free edition is also extremely
robust, well aligned with the W3C RDF/SPARQL specifications, and trouble-free
across software updates — which is why it remains the recommended backend for
the authoring phase.

## Other servers

Many stores were *de facto* excluded because they do not support SPARQL update
and/or named graphs (a.k.a. contexts), both of which `kgsteward` relies on.

<sup>back to [TOC](../README.md)</sup>
