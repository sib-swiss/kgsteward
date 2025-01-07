# First steps with `kgsteward`

1. Clone kgsteward from GitHub to access the first-steps files. 
   Create an environement variable `${FIRST_STEPS_DIR}` that point to the first-steps directory:

```sh
cd [where you like to clone from github]
git clone https://github.com/sib-swiss/kgsteward.git kgsteward
export FIRST_STEPS_DIR=`pwd`/kgsteward/doc/first_steps
```

2. Install a supported triplestore (see below). If you are new to RDF/SPARQL, you may opt for GraphDB, because of its rich documentation and convenient user interface.

<details>
<summary>GraphDB</summary>

Install (the free version of) GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu), following the vendor instructions. Launch GraphDB, using the application icon or the command line. By default, the user interface of GraphDB becomes available at http://localhost:7200.

Alternatively, you may use Docker ...

</details>

<details>
<summary>Fuseki</summary>


```sh
brew install fuseki
export FUSEKI_DIR=~/scratch/fuseki # FIXME: update path to where you would like to store the db
( cd $FUSEKI_DIR && fuseki-server --config $FIRST_STEPS_DIR/fuseki.config.ttl )
```

</details>

3. 

