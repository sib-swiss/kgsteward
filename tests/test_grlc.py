"""Unit tests for the grlc decorator parser in src/kgsteward/grlc.py.

Covers the core, backend-agnostic behaviour: parsing the `#+` decorator block,
grlc parameter `defaults` substitution, query-form detection, and the
sparql-examples RDF documentation (including the `#+ endpoint:` injection).
No server or docker needed -- pure functions over strings and rdflib graphs.
"""
import pytest
from rdflib import Literal, URIRef, RDF, RDFS

from src.kgsteward.grlc import (
    parse_decorators, apply_defaults, detect_form, strip_comments,
    build_graph, parse_query, subject_iri, SH, SCH, DCT,
)
from src.kgsteward.special import make_query_description


# --------------------------------------------------------------------------- #
# decorator parsing
# --------------------------------------------------------------------------- #

def test_parse_decorators_reads_known_keys():
    d = parse_decorators(
        "#+ summary: A query\n"
        "#+ tags:\n#+   - x\n#+   - y\n"
        "#+ method: GET\n"
        "SELECT * WHERE { ?s ?p ?o }"
    )
    assert d.summary == "A query"
    assert d.tags == [ "x", "y" ]
    assert d.method == "GET"


def test_no_decorator_block_returns_none():
    assert parse_decorators( "SELECT * WHERE { ?s ?p ?o }" ) is None


def test_malformed_yaml_is_lenient():
    """A '#+' block that is not valid YAML yields an empty decorator set, not a
    crash (grlc-lenient); a decorated file therefore never breaks parsing."""
    d = parse_decorators( "#+ : : not: valid: yaml:\nSELECT * WHERE { ?s ?p ?o }" )
    assert d is not None
    assert d.summary is None


def test_unknown_keys_are_preserved():
    d = parse_decorators( "#+ summary: s\n#+ novel_key: kept\nSELECT * WHERE {?s ?p ?o}" )
    assert ( d.model_extra or {} ).get( "novel_key" ) == "kept"


# --------------------------------------------------------------------------- #
# defaults substitution
# --------------------------------------------------------------------------- #

def test_defaults_substitution_by_type():
    q = (
        "#+ defaults:\n"
        "#+   - a: blue\n#+   - n: 5\n#+   - who: http://ex.org/Alice\n#+   - lbl: Voiture\n"
        "SELECT * WHERE { ?x p ?_a . ?x q ?_n_integer . ?x r ?_who_iri . ?x s ?_lbl_fr . ?x t ?__opt }"
    )
    out = apply_defaults( q, parse_decorators( q ) )
    assert '"blue"' in out and "?_a " not in out       # plain literal
    assert " 5 " in out                                 # bare number, unquoted
    assert "<http://ex.org/Alice>" in out               # IRI
    assert '"Voiture"@fr' in out                        # language tag
    assert "?__opt" in out                              # no default -> untouched


def test_defaults_leave_query_body_and_decorators_intact():
    q = "#+ summary: s\nSELECT * WHERE { ?s ?p ?o }"
    out = apply_defaults( q, parse_decorators( q ) )
    assert out == q                                     # no defaults -> unchanged, comments kept


# --------------------------------------------------------------------------- #
# query-form detection
# --------------------------------------------------------------------------- #

def test_detect_form_basic():
    assert detect_form( "SELECT * WHERE { ?s ?p ?o }" )                    == "SELECT"
    assert detect_form( "ASK { ?s ?p ?o }" )                               == "ASK"
    assert detect_form( "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }" )      == "CONSTRUCT"
    assert detect_form( "DESCRIBE <http://x>" )                            == "DESCRIBE"
    assert detect_form( "PREFIX e:<http://x#> INSERT DATA { <a> e:p 1 }" ) == "UPDATE"
    assert detect_form( "" )                                               is None


def test_detect_form_ignores_traps():
    """A keyword inside a comment, a string literal, or a prefix IRI must not be
    mistaken for the query form."""
    assert detect_form( "# construct the answer\nASK { ?s ?p ?o }" ) == "ASK"
    assert detect_form( 'SELECT ?x WHERE { ?x rdfs:label "CONSTRUCT" }' ) == "SELECT"
    assert detect_form( "PREFIX p: <http://x#describe>\nSELECT * { ?s ?p ?o }" ) == "SELECT"


def test_strip_comments_preserves_iris_and_literals():
    s = strip_comments( 'SELECT ?x { ?x p <http://a#b> ; q "a # b" } # tail' )
    assert "<http://a#b>" in s          # '#' in IRI kept
    assert '"a # b"' in s               # '#' in literal kept
    assert "tail" not in s              # trailing comment removed


# --------------------------------------------------------------------------- #
# sparql-examples RDF documentation
# --------------------------------------------------------------------------- #

def test_build_graph_sparql_examples_core():
    q = (
        "#+ summary: sum\n#+ description: desc\n#+ tags: [t1, t2]\n"
        "#+ endpoint: https://own.example.org/sparql\n"
        "SELECT * WHERE { ?s ?p ?o }"
    )
    g = build_graph( q, "q1", parse_decorators( q ),
                     endpoint = "https://passed.example.org/sparql", form = "SELECT" )
    subj = subject_iri( "q1", "https://passed.example.org/sparql" )
    assert ( subj, RDF.type, SH.SPARQLSelectExecutable ) in g
    # rdfs:label comes from summary
    assert ( subj, RDFS.label, Literal( "sum" ) ) in g
    # rdfs:comment prefers description over summary
    assert ( subj, RDFS.comment, Literal( "desc" ) ) in g
    # tags -> one schema:keywords Text literal each
    kw = { str( o ) for o in g.objects( subj, SCH.keywords ) }
    assert kw == { "t1", "t2" }
    # schema:target: the query's own '#+ endpoint' wins over the passed one
    assert ( subj, SCH.target, URIRef( "https://own.example.org/sparql" ) ) in g


def test_label_summary_fallback_and_absence():
    # summary only: label == comment (comment falls back to summary)
    q = "#+ summary: only sum\nSELECT * WHERE {?s ?p ?o}"
    g = build_graph( q, "q", parse_decorators( q ), form = "SELECT" )
    subj = subject_iri( "q" )
    assert ( subj, RDFS.label, Literal( "only sum" ) ) in g
    assert ( subj, RDFS.comment, Literal( "only sum" ) ) in g
    # no summary: no rdfs:label emitted
    q2 = "#+ description: only desc\nSELECT * WHERE {?s ?p ?o}"
    g2 = build_graph( q2, "q2", parse_decorators( q2 ), form = "SELECT" )
    assert list( g2.objects( subject_iri( "q2" ), RDFS.label ) ) == []


def test_source_and_citation_triples():
    q = "#+ summary: s\n#+ source: MetaNetX 1.ttl\n#+ citation: GigaScience 2024\nSELECT * WHERE {?s ?p ?o}"
    g = build_graph( q, "q", parse_decorators( q ), form = "SELECT" )
    subj = subject_iri( "q" )
    assert ( subj, DCT.source, Literal( "MetaNetX 1.ttl" ) ) in g
    assert ( subj, SCH.citation, Literal( "GigaScience 2024" ) ) in g


def test_subject_iri_endpoint_vs_fallback():
    assert str( subject_iri( "q", "https://e.org/sparql" ) ) == \
        "https://e.org/sparql/.well-known/sparql-examples/q"
    assert str( subject_iri( "q" ) ) == "https://purl.expasy.org/kgsteward/query/q"


def test_sh_select_holds_query_as_authored():
    """The stored query keeps its '#' / '#+' comment lines (query as authored)."""
    q = "#+ summary: s\nSELECT * WHERE { ?s ?p ?o } # trailing"
    g = build_graph( q, "q", parse_decorators( q ), form = "SELECT" )
    sel = str( next( g.objects( None, SH.select ) ) )
    assert "#+ summary: s" in sel and "# trailing" in sel


# --------------------------------------------------------------------------- #
# '#+ endpoint:' injection
# --------------------------------------------------------------------------- #

def test_endpoint_directive_prepended_when_absent():
    q = "#+ summary: s\nSELECT * WHERE { ?s ?p ?o }"
    g = build_graph( q, "q", parse_decorators( q ),
                     endpoint = "https://pub.example.org/sparql", form = "SELECT" )
    sel = str( next( g.objects( None, SH.select ) ) )
    assert sel.startswith( "#+ endpoint: https://pub.example.org/sparql\n" )
    assert "#+ summary: s" in sel


def test_endpoint_directive_not_doubled_when_query_owns_one():
    q = "#+ endpoint: https://own.example.org/sparql\n#+ summary: s\nSELECT * WHERE {?s ?p ?o}"
    g = build_graph( q, "q", parse_decorators( q ),
                     endpoint = "https://pub.example.org/sparql", form = "SELECT" )
    sel = str( next( g.objects( None, SH.select ) ) )
    assert sel.count( "#+ endpoint:" ) == 1 and "own.example.org" in sel


def test_no_endpoint_no_directive():
    q = "#+ summary: s\nSELECT * WHERE { ?s ?p ?o }"
    g = build_graph( q, "q", parse_decorators( q ), form = "SELECT" )
    sel = str( next( g.objects( None, SH.select ) ) )
    assert "#+ endpoint:" not in sel


# --------------------------------------------------------------------------- #
# single-query convenience wrapper
# --------------------------------------------------------------------------- #

def test_parse_query_wrapper_returns_query_and_graph():
    q = "#+ defaults:\n#+   - a: v\nSELECT * WHERE { ?x p ?_a }"
    executable, graph = parse_query( q, "q" )
    assert '"v"' in executable                 # defaults applied in returned query
    assert len( graph ) > 0                    # graph populated


def test_no_decorator_query_passthrough():
    plain = "SELECT * WHERE { ?s ?p ?o }"
    executable, _ = parse_query( plain, "q" )
    assert executable == plain


# --------------------------------------------------------------------------- #
# summary is mandatory when a query uses grlc notation (enforced at upload)
# --------------------------------------------------------------------------- #

def test_grlc_summary_mandatory( tmp_path ):
    # grlc notation without a summary -> hard stop
    no_sum = tmp_path / "no_summary.rq"
    no_sum.write_text( "#+ description: has a description but no summary\nSELECT * WHERE {?s ?p ?o}" )
    with pytest.raises( SystemExit ):
        make_query_description( "http://ctx", [ str( no_sum ) ] )
    # grlc notation with a summary -> accepted
    ok = tmp_path / "ok.rq"
    ok.write_text( "#+ summary: fine\nSELECT * WHERE {?s ?p ?o}" )
    out = make_query_description( "http://ctx", [ str( ok ) ] )
    assert out and "INSERT DATA" in out[ 0 ]
    # non-grlc file (no '#+') is unaffected by the requirement
    legacy = tmp_path / "legacy.rq"
    legacy.write_text( "# just a comment\nSELECT * WHERE {?s ?p ?o}" )
    out2 = make_query_description( "http://ctx", [ str( legacy ) ] )
    assert out2 and "sh:select" in out2[ 0 ]
