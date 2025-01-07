# First steps with `kgsteward`

1. Clone kgsteward from GitHub. 
   Create an environement variable `${KGSTEWARD_ROOT_DIR}` that point to its root directory:

```sh
cd [where you like to clone from github]
git clone https://github.com/sib-swiss/kgsteward.git kgsteward
export KGSTEWARD_ROOT_DIR=`pwd`/kgsteward
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

By default, the user interface of Fuseki becomes available at http://localhost:3030.

</details>

3. Install `kgsteward` globally as a cli tool, following the instructions. 
   Or if you have `uv` installed, you may try temporarily 

```sh
alias kgsteward="uv run $KGSTEWARD_ROOT_DIR"
```

4. Create and populate the repository

<details>
<summary>GraphDB</summary>

```sh
cd $KGSTEWARD_ROOT_DIR/example/first_steps_graphdb
kgsteward first_steps_graphdb.yaml -I # rewrite repository
kgsteward first_steps_graphdb.yaml -C # populate repository
kgsteward first_steps_graphdb.yaml -V # validate repository
```

</details>

<details>
<summary>Fuseki</summary>

```sh
cd $KGSTEWARD_ROOT_DIR/example/first_steps_graphdb
kgsteward first_steps_fuseki.yaml -I # rewrite repository
kgsteward first_steps_fuseki.yaml -C # populate repository
kgsteward first_steps_fuseki.yaml -V # validate repository
```

</details>

Congratulations: you have populated a repository using kgsteward :-) 


