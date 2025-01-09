<sup>back to [TOC](../README.md)</sup>

# Scaling Up

In a perfect world, if the content of an RDF repository is specified strictly following W3C recommendations, one could expect to obtain the same resource whatever the store brand, although the performances may differ. In the real world, it is a little bit more complicated than that. The examples proposed in the first steps yield exactly the same results.


## GraphDB

* `kgsteward` was developed using GraphDB as server.
  GraphDB free edition proved to be robust (it never crashed),
  very well aligned with W3C specifications for RDF/SPARQL and
  effortless with respect to software updates.

* "Context index" should be turned ON (the default if off) to
  increase the reactivity of `kgsteward`


## RDF4J

* GraphDB was built on top of RDF4J, hence one could have expected that
  the migration from GraphDB to RDF4J would be effortless. It was not
  really the case.

## Fuseki


## Other servers

* Many servers were de facto excluded because they were not supporting
  SPARQL update and/or named graph (AKA context)

<sup>back to [TOC](../README.md)</sup>
