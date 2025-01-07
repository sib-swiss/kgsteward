# First steps with `kgsteward`

1. ## Clone kgsteward from GitHub.
   
   This is is to access the first-steps data and config files.
   One create an environement variable `${KGSTEWARD_ROOT_DIR}` that point to its root directory.

```sh
# change dir to where you like to clone kgsteward
git clone https://github.com/sib-swiss/kgsteward.git kgsteward
export KGSTEWARD_ROOT_DIR=`pwd`/kgsteward
```

2. ## Install a supported triplestore. 

	If you are new to RDF/SPARQL, you may opt for GraphDB, because of its rich documentation and convenient user interface.

<details>
<summary>GraphDB</summary>

Install (the free version of) GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu), following the vendor instructions. Launch GraphDB, using the application icon or the command line. By default, the user interface of GraphDB becomes available at http://localhost:7200.

Alternatively, you may use Docker ...

</details>

<details>
<summary>Fuseki through brew (OSX)</summary>


```sh
brew install fuseki
export FUSEKI_DIR=~/scratch/fuseki # FIXME: update path to where you would like to store the db
mkdir -p $FUSEKI_DIR
( cd $FUSEKI_DIR && fuseki-server --config $FIRST_STEPS_DIR/fuseki.config.ttl > $FUSEKI_DIR/logs.txt )&
```

By default, the user interface of Fuseki becomes available at http://localhost:3030.

</details>

3. ## Install `kgsteward` 

   You can install `kgsteward` globally, following the [instructions](https://github.com/sib-swiss/kgsteward). 
   Or alternatively, if you have `uv` installed, you may define an alias

```sh
alias kgsteward="uv run $KGSTEWARD_ROOT_DIR/kgsteward"
```

4. ## Create and populate the repository. 

The different stores are accessed through different YAML config file. The description of the dataset to be stored is shared by the different configs.

<details>
<summary>GraphDB</summary>

```sh
export GRAPHDB_USERNAME=admin  # default of GraphDB fresh installation
export GRAPHDB_PASSWORD=root   # default of GraphDB fresh installation
cd $KGSTEWARD_ROOT_DIR/doc/first_steps
kgsteward graphdb.yaml -I # rewrite repository
kgsteward graphdb.yaml -C # populate repository
kgsteward graphdb.yaml -V # validate repository
```

</details>

<details>
<summary>Fuseki</summary>

```sh
cd $KGSTEWARD_ROOT_DIR/doc/first_steps
kgsteward fuseki.yaml -I # rewrite repository
kgsteward fuseki.yaml -C # populate repository
kgsteward fuseki.yaml -V # validate repository
```

</details>

Congratulations: you have populated a repository using `kgsteward` :-) 

5. ## Details

The following files have been used

* [dataset.yaml](dataset.yaml) describes the content of a repository, independantly from a particular store engine. This file was manually created. A diversity of syntax possiblities are shown.  

* [graphdb.yaml](graphdb.yaml) describes how to access GraphDB, and include a links to [dataset.yaml](dataset.yaml). This file was manually edited. 

* [graphdb.config.ttl](graphdb.config.ttl) describes the configuration from a GraphDB repository. This file was exported from the GraphDB user interface, it can be manually modifed to some extent. It permits to re-create the same configuration in another server instance.

* [fuseki.yaml](fuseki.yaml) describes how to access Fuseki, and include a links to [dataset.yaml](dataset.yaml) . This file was manually edited.

* [rdf4j.yaml](rdf4j.yaml) describes how to access Fuseki, and include a links to [dataset.yaml](dataset.yaml) . This file was manually created.

* [rdf4j.config.ttl](rdf4j.config.ttl) describes the configuration of a RDF4J repository. This file was exported from the RDF4J user interface, it can be manually modified to some extent. It permits to re-create the same configuration in another server instance.


