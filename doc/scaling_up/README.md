<sup>back to [TOC](../README.md)</sup>

# Scaling Up

## Maturity level

__`kgsteward`__ as a client for GraphDB was developped over several years to gather and manage experimental data from chemistry (LC-MS/MS) and biology (bio-activities), together with reference chemical structures derived from public database (LOTUS, Wikidata). This was published in [A Sample-Centric and Knowledge-Driven Computational Framework for Natural Products Drug Discovery](https://doi.org/10.1021/acscentsci.3c00800). Two other complex research projects which RDF data are managed by __`kgsteward`__ are currently ongoing. 

__`kgsteward`__ as a client for Fuseki and RDF4J is currently under developpement.

## Objective

In a perfect world, if the content of an RDF repository is specified strictly following W3C recommendations, one could expect to obtain the same resource whatever the store brand, although the performances may differ. In the real world, it is a little bit more complicated than that. The examples proposed in the first steps yield exactly the same results, but they are realized on very small datasets.

## Production-proven backends

* `kgsteward` was developed using GraphDB as its server. Over the last few years,
  GraphDB free edition proved (i) extremely robust (it never crashes),
  (ii) very well aligned with the W3C RDF/SPARQL specifications and
  (iii) trouble-free across software updates.
* The Fuseki, RDF4J and qlever drivers came later and are less battle-tested.

## How each driver works

For the mechanics of every backend — live HTTP stores (GraphDB, RDF4J, Fuseki)
versus the static-index qlever, their ingestion models, the tuning knobs
(GraphDB context index, Fuseki TDB vs TDB2), and qlever's checkpoint/`READY`
workflow — see [triplestore drivers](../drivers/README.md).

## Other servers

* Many servers were de facto excluded because they were not supporting
  SPARQL update and/or named graph (AKA context)

<sup>back to [TOC](../README.md)</sup>
