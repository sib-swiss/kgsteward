# first steps with Fuseki

Install fuseki locally (with homebrew on OSX):

```{sh}
brew install fuseki
```

Clone kgsteward GitHub repository and change dir to fuseki demo 

```
[change dir to where you would like to clone from github]
git clone https://github.com/sib-swiss/kgsteward.git
export GITHUB_KGSTEWARD_DIR=`pwd`/kgsteward
```

Open a new terminal and launch Fuseki server:

```
cd $GITHUB_KGSTEWARD_DIR/example/first_steps_fuseki
fuseki-server --localhost --port 3030 --config=config-fuseki-tdb2.ttl
```

The file `config-fuseki-tdb2.ttl` contains the configuration of a fuseki repository:

* named "TEST",

* with full read/write permissions,

* which files are saved in the TDB2 sub-directory (in .gitignore),

* the union of all graphs is set as default with `tdb2:unionDefaultGraph true`

Please refer to the (fuseki documentation)[] for more about fuseki configuration files.

You can connect to fuseki API at `http://localhost:3030`

In another terminal with GITHUB_KGSTEWARD_DIR defined as before:

```
cd $GITHUB_KGSTEWARD_DIR/example/first_steps_fuseki
kgsteward first_steps_fuseki.yaml -I # rewrite repository
kgsteward first_steps_fuseki.yaml -C # populate repository

```








