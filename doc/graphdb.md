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

## First step with GraphDb

You can install (the Free version of) GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu). 
Launch it. 
By default, the GraphDB user interface is available at http://localhost:7200

```{bash}
cd <github-kgsteward-root>/example/example_1
kgstward graphdb.yaml
```

## First step with Fuseki

As an alternative to GraphDB, you can install [Fuseki](https://jena.apache.org/documentation/fuseki2). If you are using homebrew on OSX, just type

```{bash}
brew install fuseki
```

Install the latest Fuseki distribution, for example pn OSX `brew install fuskeki`


