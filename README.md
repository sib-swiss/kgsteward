# kgsteward - Knowledge Graph Steward

[![Tests](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml/badge.svg)](https://github.com/sib-swiss/kgsteward/actions/workflows/tests.yml)

A command line tool to manage the content of RDF store (GraphDB, Fuseki, RDF4J...). Written in python.

## Installation

kgsteward is available from [PyPI](https://pypi.org/project/kgsteward/).
It depends on rather standard Python packages.
Its installation should be straightforward.

The recommended option is to install `kgsteward` with [`uv`](https://docs.astral.sh/uv/)

```shell
uv tool install kgsteward
```

and to ugrade it to the latest version with

```shell
uv tool upgrade kgsteward
```

or alternatively, it can be intalled with `pip3`:

```shell
pip3 install kgsteward
```

You can also clone this repo, and launch kgsteward using the script `./kgsteward` at its root

```shell
uv run ./kgsteward
```

## Usage

See the [documentation](doc/README.md)

## Development

Requirements:

- [`uv`](https://docs.astral.sh/uv/) for development.

- [Docker](https://docs.docker.com/engine/install/) installed (we use [`testcontainers`](https://github.com/testcontainers/testcontainers-python) to deploy triplestores for testing)

- Install uv pre-commit hooks (once):

```sh
uv tool install pre-commit --with pre-commit-uv --force-reinstall
```

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
