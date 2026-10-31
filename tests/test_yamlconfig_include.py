"""`!include` used as a list item splices its sub-list in place.

Documented in doc/yaml/kgsteward.schema.md: "During the parsing of YAML, lists
are systematically flatten. This permit to use `!include <filename>` as a list
item, to import and insert a sub-list in place."  The string-valued fields get
this from DatasetConf/QueryConf, the `dataset` and `queries` lists from
KGStewardConf.  Pure parsing contract -- no server or docker needed."""

from src.kgsteward.yamlconfig import parse_yaml_conf

CONFIG = """
version: kgsteward_yaml_3
server:
  brand         : graphdb
  location      : http://localhost:7200
  server_config : config.ttl
  repository    : test
context_base_IRI: http://example.org/context/
file_loader:
  method: file_store
url_loader:
  method: sparql_load
dataset:
  - name: first
  - !include middle.yaml
  - name: last
queries:
  - !include query.yaml
"""

MIDDLE = """
  - name: middle_1
    update:
      - update_1.rq
      - !include more_update.yaml
  - name: middle_2
"""

MORE_UPDATE = """
  - update_2.rq
  - update_3.rq
"""

QUERY = """
  - name: included_query
"""


def _config( tmp_path ):
    ( tmp_path / "config.yaml"      ).write_text( CONFIG )
    ( tmp_path / "middle.yaml"      ).write_text( MIDDLE )
    ( tmp_path / "more_update.yaml" ).write_text( MORE_UPDATE )
    ( tmp_path / "query.yaml"       ).write_text( QUERY )
    return parse_yaml_conf( str( tmp_path / "config.yaml" ))


def test_included_datasets_are_spliced_in_place( tmp_path ):
    config = _config( tmp_path )
    assert [ item["name"] for item in config["dataset"]] == [
        "first", "middle_1", "middle_2", "last"
    ]


def test_included_queries_are_spliced_in_place( tmp_path ):
    config = _config( tmp_path )
    assert [ item["name"] for item in config["queries"]] == [ "included_query" ]


def test_nested_include_within_a_dataset_is_still_flatten( tmp_path ):
    config = _config( tmp_path )
    dataset = { item["name"]: item for item in config["dataset"] }
    assert dataset["middle_1"]["update"] == [
        "update_1.rq", "update_2.rq", "update_3.rq"
    ]
