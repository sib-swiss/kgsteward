"""Unit tests for the kgsteward query-form extension in src/kgsteward/grlc.py.

Covers the `selector` / `form` decorators (a kgsteward extension over grlc, not
part of grlc itself): the five widget kinds, the InputForm string-substitution
model, their RDF in the kgsteward vocabulary, and the accumulating GrlcCatalog
with its cross-query check(). Pure rdflib, no server/docker.
"""
from rdflib import Literal, RDF
from rdflib.namespace import XSD
from rdflib.collection import Collection

from src.kgsteward.grlc import GrlcCatalog, build_graph, parse_decorators, KG, DCT


def _graph( text, name, endpoint = None ):
    return build_graph( text, name, parse_decorators( text ), endpoint = endpoint, form = "SELECT" )


# --------------------------------------------------------------------------- #
# widgets
# --------------------------------------------------------------------------- #

WIDGETS = """#+ summary: list
#+ selector:
#+   - id: w_select
#+     type: select
#+     prompt: pick one
#+   - id: w_check
#+     type: checkbox
#+     prompt: pick many
#+   - id: w_auto
#+     type: autocomplete
#+     prompt: type
#+     options: other_query
#+   - id: w_text
#+     type: text
#+     prompt: enter
#+     pattern: "^[0-9]+$"
#+   - id: w_slider
#+     type: slider
#+     prompt: threshold
#+     min: 0
#+     max: 10
#+     step: 2
#+   - id: w_default_type
#+     prompt: no explicit type
SELECT ?a ?b WHERE { ?a p ?b }
"""

def test_widget_classes():
    g = _graph( WIDGETS, "list_q" )
    assert ( KG.w_select,  RDF.type, KG.SelectParam )       in g
    assert ( KG.w_check,   RDF.type, KG.CheckboxParam )     in g
    assert ( KG.w_auto,    RDF.type, KG.AutocompleteParam ) in g
    assert ( KG.w_text,    RDF.type, KG.TextParam )         in g
    assert ( KG.w_slider,  RDF.type, KG.SliderParam )       in g


def test_widget_without_type_defaults_to_select():
    g = _graph( WIDGETS, "list_q" )
    assert ( KG.w_default_type, RDF.type, KG.SelectParam ) in g


def test_query_backed_widget_options_default_and_explicit():
    g = _graph( WIDGETS, "list_q" )
    # options omitted -> selectQuery is the declaring query
    assert ( KG.w_select, KG.selectQuery, KG.list_q ) in g
    # options given -> selectQuery is that query
    assert ( KG.w_auto, KG.selectQuery, KG.other_query ) in g


def test_value_index_defaults_and_types():
    g = _graph( WIDGETS, "list_q" )
    # defaults: valueIndex 1, nameIndex 2 as xsd:integer
    assert ( KG.w_select, KG.valueIndex, Literal( 1, datatype = XSD.integer ) ) in g
    assert ( KG.w_select, KG.nameIndex,  Literal( 2, datatype = XSD.integer ) ) in g


def test_value_index_as_variable_name():
    q = ("#+ selector:\n#+   - id: w\n#+     prompt: p\n#+     valueIndex: mnet\n"
         "SELECT ?mnet WHERE { ?mnet a t }")
    g = _graph( q, "list_q" )
    assert ( KG.w, KG.valueVar, Literal( "mnet" ) ) in g          # string -> valueVar
    assert not list( g.objects( KG.w, KG.valueIndex ) )          # not the integer predicate


def test_text_pattern_and_slider_bounds():
    g = _graph( WIDGETS, "list_q" )
    assert any( str( o ) == "^[0-9]+$" for o in g.objects( KG.w_text, KG.pattern ) )
    assert ( KG.w_slider, KG.min,  Literal( 0.0 ) ) in g
    assert ( KG.w_slider, KG.max,  Literal( 10.0 ) ) in g
    assert ( KG.w_slider, KG.step, Literal( 2.0 ) ) in g


# --------------------------------------------------------------------------- #
# input form
# --------------------------------------------------------------------------- #

FORM = """#+ summary: report
#+ form:
#+   - target: "reconx:A"
#+     widget: w_select
#+   - target: "reconx:B"
#+     widget: w_auto
#+     default: "reconx:def"
SELECT * WHERE { ?x p reconx:A ; q reconx:B }
"""

def test_input_form_structure():
    g = _graph( FORM, "report_q" )
    form = KG[ "form_report_q" ]
    assert ( form, RDF.type, KG.InputForm ) in g
    assert ( form, KG.selectQuery, KG.report_q ) in g
    # ordered inputField list of 2 blank nodes
    lst = next( g.objects( form, KG.inputField ) )
    members = list( Collection( g, lst ) )
    assert len( members ) == 2
    targets = { str( o ) for o in g.objects( None, KG.targetStr ) }
    assert targets == { "reconx:A", "reconx:B" }
    assert ( None, KG.replaceWith, KG.w_select ) in g
    assert ( None, KG.default, Literal( "reconx:def" ) ) in g


# --------------------------------------------------------------------------- #
# GrlcCatalog
# --------------------------------------------------------------------------- #

def _catalog():
    cat = GrlcCatalog()
    cat.parse( WIDGETS, "list_q" )
    cat.parse( "#+ summary: other\nSELECT ?a ?b WHERE { ?a p ?b }", "other_query" )
    cat.parse( FORM, "report_q" )
    return cat


def test_catalog_accumulates_into_one_graph():
    cat = _catalog()
    # widget defined in list_q and referenced by report_q resolve to the same IRI
    assert ( KG.w_select, RDF.type, KG.SelectParam ) in cat.graph
    assert ( KG[ "form_report_q" ], RDF.type, KG.InputForm ) in cat.graph


def test_catalog_list_and_get():
    cat = _catalog()
    names = { e[ "name" ] for e in cat.list() }
    assert names == { "list_q", "other_query", "report_q" }
    assert cat.get( "report_q" ).form == "SELECT"
    assert cat.get( "missing" ) is None


def test_catalog_search_by_text_and_tag():
    cat = GrlcCatalog()
    cat.parse( "#+ summary: metabolic networks\n#+ tags: [report]\nSELECT * WHERE {?s ?p ?o}", "a" )
    cat.parse( "#+ summary: something else\nSELECT * WHERE {?s ?p ?o}", "b" )
    assert [ q.name for q in cat.search( text = "metabolic" ) ] == [ "a" ]
    assert [ q.name for q in cat.search( tags = [ "report" ] ) ] == [ "a" ]
    assert cat.search( tags = [ "absent" ] ) == []


def test_check_is_clean_for_consistent_catalog():
    assert _catalog().check() == []


def test_check_flags_dangling_widget_and_missing_target():
    cat = GrlcCatalog()
    cat.parse(
        "#+ form:\n#+   - target: \"NOPE\"\n#+     widget: ghost\nSELECT * WHERE { ?s ?p ?o }",
        "bad",
    )
    problems = cat.check()
    assert any( "undefined widget 'ghost'" in p for p in problems )
    assert any( "targetStr 'NOPE' not found" in p for p in problems )


def test_check_flags_unknown_option_query_and_duplicate_id():
    cat = GrlcCatalog()
    cat.parse( "#+ selector:\n#+   - id: dup\n#+     prompt: p\n#+     options: nowhere\n"
               "SELECT * WHERE {?s ?p ?o}", "q1" )
    cat.parse( "#+ selector:\n#+   - id: dup\n#+     prompt: p\nSELECT * WHERE {?s ?p ?o}", "q2" )
    problems = cat.check()
    assert any( "options query 'nowhere' not found" in p for p in problems )
    assert any( "duplicate selector id 'dup'" in p for p in problems )


def test_check_flags_target_absent_only_in_body_not_comment():
    """A targetStr that appears only in the '#+' block (not the executable body)
    is still flagged -- the check runs against the comment-stripped body."""
    cat = GrlcCatalog()
    cat.parse(
        "#+ selector:\n#+   - id: w\n#+     prompt: p\n"
        "#+ form:\n#+   - target: \"reconx:X\"\n#+     widget: w\n"
        "SELECT * WHERE { ?s ?p ?o }",          # 'reconx:X' only in the #+ block above
        "q",
    )
    assert any( "targetStr 'reconx:X' not found" in p for p in cat.check() )
