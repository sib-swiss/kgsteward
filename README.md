# kgsteward - Knowledge Graph Steward

[![Tests](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml/badge.svg)](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml)

A command line tool to help manage RDF store (GraphDB, Fuseki, RDF4J...). Written in python.

## Installation

The code only depends on very standard Python packages. Its installation should be straightforward.

The easiest option is to install `kgsteward` with `pip3`:

```shell
pip3 install kgsteward
```

Alternatively, you can also clone/download the content of this repo to your local machine, and then run kgsteward using the script `./kgsteward`.

**Important:** if the above installation fails or does not build properly (e.g. the package name is set to `UNKNOWN`), make sure that your versions of `pip` and `setuptools` are up-to-date:

```shell
pip install --upgrade pip
pip install --upgrade setuptools
```

## Running kgsteward

```shell
kgsteward -h
```

## Documentation

The syntax of the YAML configuration file is given [here](doc/yamldoc.md)

## Development

> Requirements:
>
> - [`uv`](https://docs.astral.sh/uv/) for development.
> - [Docker](https://docs.docker.com/engine/install/) installed (we use [`testcontainers`](https://github.com/testcontainers/testcontainers-python) to deploy triplestores for testing)

Run tests, `-s` will print all outputs:

```bash
uv run pytest -s
```

With HTML coverage report:

```bash
uv run pytest -s --cov --cov-report html
python -m http.server 3000 --directory ./htmlcov
```

## References

__`kgsteward`__ was developped to manage experimental chemical data (LC-MS2) and experimental biological data (bio-activity) data together with reference chemical structures derived from public database (LOTUS, wikidata) as reported in [A Sample-Centric and Knowledge-Driven Computational Framework for Natural Products Drug Discovery](https://doi.org/10.1021/acscentsci.3c00800).
