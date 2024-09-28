# First steps

## Install examples

Clone this git repository and define an environment variable pointng to its root dir 

```{bash}
export GITHUB_KGSTEWARD_ROOT_DIR=<absolute-path-to-dir>
git clone $GITHUB_KGSTEWARD_ROOT_DIR
```
This environment variable `GITHUB_KGSTEWARD_ROOT_DIR` will be used through all the examples.

## Install kgsteward

You can follow the instructions [here](https://github.com/sib-swiss/kgsteward) or
create an alias 

```{bash}
alias kgsteward=GITHUB_KGSTEWARD_ROOT_DIR/kgsteward
```
In the latter case some python packages might need to be installed. 

## First step with GraphDB

Install (the Free version of) of GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu), following the vendor instructions, and launch it. 

By default, the user interface of GraphDB becomes available at http://localhost:7200

## First step with Fuseki (alternative)

As an alternative to GraphDB, you can install [Fuseki](https://jena.apache.org/documentation/fuseki2). If you are using homebrew on OSX, just type

```{bash}
brew install fuseki
```
and launch it with

```{bash}
fuseki-server ..
```
By default, the user interface of Fuseki becomes available at http://localhost:xxxx


## Run first example

Here below are the three commands to run. If you are using fuseki, just replace graphdb.example_1.yaml with fuseki.example_1.yaml in the code below

```{bash}
cd $GITHUB_KGSTEWARD_ROOT_DIR/examples/example_1
kgsteward graphdb.example_1.yaml -I # create a new repository named EXAMPLE_1 and erase its content
kgsteward graphdb.example_1.yaml -C # populate the EXAMPLE_1 repository
```

If everything went well, you shoud see something like this.

Congratulation you have populated your first triplestore.











