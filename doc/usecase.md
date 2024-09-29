# Use cases

## "Sinergia Wolfender" and "ENPKG"

kgsteward was initiated in the context of a Swiss collaborative research project, involving five different groups phsyically located throughout Switerland. A knowledge graph (KG) was initally proposed as a way to collect and integrate the experimental data produced by the different groups, together with reference informatch fteched from public database. The inital idea was to use git to share share some RDF data and a common configuration file, permitting to locally deploy instances of GraphDB. The concept proved effective, to share information among developers as well as to maintain a common production server (not yet public). 

ENPKG is a sub-project that "forked" from the inital one, leading to its own software development and publications (ref enpkg).

## Ongoing development

SPARQL updates support was first introduced in kgsteward to perform quick patch on the imported data produced by others. Dependency graph arise as an ovbious way to automatate the application of these patches. As this strategy proved extremely convenient, further interest for SPARQL updates were required. 
