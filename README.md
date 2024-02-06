# kgsteward - Knowledge Graph Steward

A command line tool to help manage RDF store (GraphDB). Written in python.

## Installation

The code only depends on very standard Python packages.
Its installation should straightforward.
The easiest option is to install `kgsteward` with `pip3`:

```shell
pip3 install git+https://github.com/sib-swiss/kgsteward

# To update your installation to a newer version.
pip3 install --upgrade git+https://github.com/sib-swiss/kgsteward
```

Alternatively, you can also clone/download the content of this repo to your
local machine, and then run kgsteward using the script `./kgsteward`.

**Important:** if the above installation fails or does not build properly
(e.g. the package name is set to `UNKNOWN`), make sure that your versions of
`pip` and `setuptools` are up-to-date:

```shell
pip install --upgrade pip
pip install --upgrade setuptools
```

## Running kgsteward

```shell
kgsteward -h
```
