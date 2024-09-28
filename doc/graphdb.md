# First steps


## Install examples

Clone this git repository and define an environment variable poinitng to its root dir 

```{bash}

export GITHUB_KGSTEWARD_ROOT_DIR=<absolute-path-to-dir>
git clone $GITHUB_KGSTEWARD_ROOT_DIR

```

## Install kgsteward

You can follow the instructions [here](https://github.com/sib-swiss/kgsteward) or
invoke it using `GITHUB_KGSTEWARD_ROOT_DIR/kgsteward`. 

## First step with GraphDb

Install (the Free version of) GraphDB from [Ontotext website](https://www.ontotext.com/products/graphdb/download/?ref=menu). 
Launch it. 
By default, the GraphDB user interface is available at http://localhost:7200



```{bash}
cd <github-kgsteward-root>/example/example_1
kgstward graphdb.yaml
```
## First step with GraphDb

Install the latest Fuseki distribution, for example pn OSX `brew install fuskeki`


