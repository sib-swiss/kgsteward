"""Unit tests for TSV serialization helpers in src/kgsteward/common.py.

The cross-backend --dump comparison writes SPARQL results as TSV and diffs
them.  SPARQL literals routinely carry TAB / CR / NEWLINE (rdfs:comment,
labels), which — written raw — would split a value across columns or rows and
silently corrupt the comparison.  These tests pin the escaping that prevents it.
"""
from src.kgsteward.common import tsv_escape, write_sorted_tsv


def test_tsv_escape_neutralizes_grid_breakers():
    """TAB / CR / NEWLINE / backslash are escaped; the result has no raw grid
    characters left, so it can never span more than one cell."""
    assert tsv_escape( "a\tb" )   == "a\\tb"
    assert tsv_escape( "a\nb" )   == "a\\nb"
    assert tsv_escape( "a\r\nb" ) == "a\\r\\nb"
    assert tsv_escape( "a\\b" )   == "a\\\\b"          # backslash doubled
    assert tsv_escape( "a\\tb" )  == "a\\\\tb"         # literal backslash-t, NOT a tab
    for ch in ( "\t", "\n", "\r" ):
        assert ch not in tsv_escape( f"x{ch}y" ), f"raw {ch!r} must not survive"


def test_tsv_escape_is_reversible():
    """The escaping is unambiguous: a correct single-pass reader recovers the
    original.  (A backslash escape must be consumed atomically — sequential
    global replaces would confuse an escaped backslash '\\\\' followed by 't'
    with a real tab escape '\\t', which is exactly why we escape backslash
    first on the way out.)"""
    def unescape( s ):
        out, i = [], 0
        while i < len( s ):
            if s[i] == "\\" and i + 1 < len( s ):
                out.append( { "n": "\n", "r": "\r", "t": "\t", "\\": "\\" }
                            .get( s[i + 1], s[i + 1] ))
                i += 2
            else:
                out.append( s[i] )
                i += 1
        return "".join( out )
    for original in ( "plain", "a\tb", "a\nb", "a\\b", "tricky\\t\tmix\n" ):
        assert unescape( tsv_escape( original )) == original


def test_write_sorted_tsv_keeps_grid_intact( tmp_path ):
    """A literal with an embedded tab and newline must stay one cell on one row:
    the file has exactly header + N data lines, each with the same column count."""
    header = [ "s", "p", "o" ]
    rows = [
        [ "<x>", "<label>", "line1\nline2" ],   # embedded newline
        [ "<y>", "<note>",  "col\tinside" ],     # embedded tab
    ]
    write_sorted_tsv( str( tmp_path ), "dump", header, rows )
    lines = ( tmp_path / "dump.tsv" ).read_text( encoding = "utf-8" ).splitlines()
    assert len( lines ) == 1 + len( rows ), "embedded newline must not add a row"
    for line in lines:
        assert line.count( "\t" ) == len( header ) - 1, "every row keeps 3 columns"
    assert "line1\\nline2" in lines[2] or "line1\\nline2" in lines[1]
    assert "col\\tinside"  in lines[1] or "col\\tinside"  in lines[2]


def test_write_sorted_tsv_orders_on_raw_values( tmp_path ):
    """Rows are sorted before escaping, so ordering follows the raw values."""
    write_sorted_tsv( str( tmp_path ), "d", [ "v" ], [ [ "b" ], [ "a" ], [ "c" ] ] )
    body = ( tmp_path / "d.tsv" ).read_text().splitlines()[1:]
    assert body == [ "a", "b", "c" ]
