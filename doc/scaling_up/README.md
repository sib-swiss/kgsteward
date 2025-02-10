<sup>back to [TOC](../README.md)</sup>

# Scaling Up

In a perfect world, if the content of an RDF repository is specified strictly following W3C recommendations, one could expect to obtain the same resource whatever the store brand, although the performances may differ. In the real world, it is a little bit more complicated than that. The examples proposed in the first steps yield exactly the same results, but they are realized on very small datasets.


## GraphDB

* `kgsteward` was developed using GraphDB as server.
  Over the last four years, GraphDB free edition proved to (i) extremely robust (it never crashes),
  (ii) extremelly well aligned with W3C specifications for RDF/SPARQL and (ii)
  troubleless with respect to software updates.

* "Context index" should be turned ON (the default if off) to
  increase the reactivity of `kgsteward`.

* 


## RDF4J

* GraphDB was built on top of RDF4J, hence one could have expected that
  the migration from GraphDB to RDF4J would be effortless. It was not
  really the case.

## Fuseki

* Fuseki comes with to different indexes that permit permanent storage: TCDB and TCDB2.
  Although TCDB2 is more modern and should permit faster queries, TCDB is currently a better choice with kgsteward.
  The copy-on-modify behaviour of TCDB2 indexes make their sizes grow rapidly, when exposed to many sequencial updates or deletions.
  TCDB indexes don't exhibit this behaviour. It is possible to compress TCDB2 indexes, but this is time-consuming and not very convenient
  as the index sizes are uncontrolled.

## Other servers

* Many servers were de facto excluded because they were not supporting
  SPARQL update and/or named graph (AKA context)

<sup>back to [TOC](../README.md)</sup>
