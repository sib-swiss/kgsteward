<sup>back to [TOC](../README.md)</sup>

# First steps with `kgsteward`

1. ## Clone kgsteward from GitHub.

   This is to access the first-steps data and config files.
   One create an environment variable `${KGSTEWARD_ROOT_DIR}` that points to its root directory.

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

<details>
<summary>RDF4J through docker</summary>

```sh
# brew install --cask docker # work on OSX
docker pull eclipse/rdf4j-workbench:5.1.0 # you may try tag ":latest"

export RDF4J_DIR=$HOME/scratch/rdf4j
mkdir -p $RDF4J_DIR
docker run -d \
    -p 8080:8080 \
    -e JAVA_OPTS="-Xms1g -Xmx12g" \
    -v $RDF4J_DIR:/var/rdf4j \
    -v $RDF4J_DIR/logs:/usr/local/tomcat/logs \
	--memory=13G \
	--cpus=3 \
    eclipse/rdf4j-workbench:5.1.0
```

The user interface becomes available at [http://localhost:8080/rdf4j-workbench](http://localhost:8080/rdf4j-workbench)

</details>

<details>
<summary>QLever through docker</summary>

QLever manages its own Docker container internally via the `qlever` CLI.
You need Docker (or Podman), the `qlever` Python CLI, and Apache Jena's `riot` for RDF format conversion.

```sh
# Install qlever CLI (requires uv or pip)
uv tool install qlever

# Install Apache Jena (provides riot)
brew install jena          # macOS
# or: apt install jena     # Debian/Ubuntu

# Set the working directory for the qlever index (created automatically if absent)
export QLEVER_DIR=$HOME/scratch/qlever/first_steps

# Point kgsteward to the provided Qleverfile
export QLEVER_FILE=$KGSTEWARD_ROOT_DIR/doc/first_steps/Qleverfile
```

QLever exposes a SPARQL endpoint at http://localhost:7019 (as configured in `Qleverfile`).

</details>

3. ## Install `kgsteward`

   You can install `kgsteward` globally, following the [instructions](https://github.com/sib-swiss/kgsteward).
   Or alternatively, if you have `uv` installed, you may define an alias which will work as expected only from directory `$KGSTEWARD_ROOT_DIR`and below

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

<details>
<summary>RDF4J</summary>

```sh
cd $KGSTEWARD_ROOT_DIR/doc/first_steps
kgsteward rdf4j.yaml -I # rewrite repository
kgsteward rdf4j.yaml -C # populate repository
kgsteward rdf4j.yaml -V # validate repository
```

</details>

<details>
<summary>QLever</summary>

```sh
cd $KGSTEWARD_ROOT_DIR/doc/first_steps
kgsteward qlever.yaml -I # reset staging area, copy Qleverfile to QLEVER_DIR
kgsteward qlever.yaml -C # stage all files, build index, start server
kgsteward qlever.yaml -V # validate repository
```

> **Note:** QLever uses a static index. `-C` stages all RDF files and builds the index in one pass at the end. SPARQL updates from `update:` sections are applied after the index is built and then persisted with a `rebuild-index` step.

</details>

Congratulations: you have populated a repository using `kgsteward` :-)

5. ## Details

The following configuration files have been used:

* [dataset.yaml](dataset.yaml) describes the RDF data content of a repository, independently of a particular store engine. This file was manually created. It illustrates the diversity of supported syntaxes.

* [graphdb.yaml](graphdb.yaml) describes how to access GraphDB, and includes a link to [dataset.yaml](dataset.yaml). This file was manually edited.

* [graphdb.config.ttl](graphdb.config.ttl) describes the configuration from a GraphDB repository.
  This file was obtained from the GraphDB user interface.
  It can be manually modified to some extent.
  It permits to re-create the same GraphDB repository in another server instance.

* [fuseki.yaml](fuseki.yaml) describes how to access Fuseki, and includes a link to [dataset.yaml](dataset.yaml). This file was manually edited.

* [rdf4j.yaml](rdf4j.yaml) describes how to access RDF4J, and includes a link to [dataset.yaml](dataset.yaml). This file was manually created.

* [rdf4j.config.ttl](rdf4j.config.ttl) describes the configuration of a RDF4J repository. This file was exported from the RDF4J user interface, it can be manually modified to some extent. It permits to re-create the same configuration in another server instance.

* [qlever.yaml](qlever.yaml) describes how to access QLever, and includes a link to [dataset.yaml](dataset.yaml). The qlever server location, repository name, and access token are read from the `Qleverfile` rather than from this YAML.

* [Qleverfile](Qleverfile) is the native QLever configuration file (INI format). It specifies the dataset name, server port, access token, and Docker image. kgsteward copies this file to `$QLEVER_DIR` and patches it with `MULTI_INPUT_JSON` entries before building the index — the original file is never modified.

The full supported syntax of the above YAML files is documented [here](../yaml/kgsteward.schema.md)

<sup>back to [TOC](../README.md)</sup>
