# kgsteward - Knowledge Graph Steward

[![Tests](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml/badge.svg)](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml)

A command line tool to help manage the content of RDF store (GraphDB, Fuseki, RDF4J...). Written in python.

## Installation

The code is available frpm PyPI and only depends on very standard Python packages. Its installation should be straightforward.

The standard option is to install `kgsteward` with `pip3`:

```shell
pip3 install kgsteward
```
or alternatively, if you don't like to play yourself with virtual environment and package dependencies

```shell
uv tool install kgsteward
```
You can also clone/download the content of this repo to your local machine, and then
run kgsteward using the script `./kgsteward` at its root, or alternatively

```shell
uv run ./kgsteward
```
that should manage the python environment for you.

## Documentation

See the [documentation website](https://sib-swiss.github.io/kgsteward)


## Development

Requirements:

- [`uv`](https://docs.astral.sh/uv/) for development.

- [Docker](https://docs.docker.com/engine/install/) installed (we use [`testcontainers`](https://github.com/testcontainers/testcontainers-python) to deploy triplestores for testing)

Run tests, `-s` will print all outputs:

```bash
uv run pytest -s
```

With HTML coverage report:

```bash
uv run pytest -s --cov --cov-report html
python -m http.server 3000 --directory ./htmlcov
```

Start documentation website in development:

```bash
uv run mkdocs serve
```

## References

__`kgsteward`__ was developped to manage experimental chemical data (LC-MS2) and experimental biological data (bio-activity) data together with reference chemical structures derived from public database (LOTUS, wikidata) as reported in [A Sample-Centric and Knowledge-Driven Computational Framework for Natural Products Drug Discovery](https://doi.org/10.1021/acscentsci.3c00800).
