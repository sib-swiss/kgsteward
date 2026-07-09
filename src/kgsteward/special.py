import re
from .common import *
from . import grlc

# Unsolved problem catch_key_value_rq is a particular case of catch_key_value_ttl
catch_key_value_ttl = re.compile( r"\@prefix\s+(\S*):\s+<([^>]+)>\s*\.", re.IGNORECASE )
catch_key_value_rq  = re.compile( r"PREFIX\s+(\S*):\s+<([^>]+)>",  re.IGNORECASE )

def make_void_description( context ):
    return """PREFIX void:     <http://rdfs.org/ns/void#>
PREFIX void-ext: <http://ldf.fi/void-ext#>
PREFIX rdf:      <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

INSERT{
    GRAPH <""" + context + """> {
        ?cp void:class    ?class ;
            void:entities ?count .
    }
}
WHERE{
    {
        SELECT ?class ( COUNT( * ) AS ?count ) 
        WHERE{ 
            [] a ?class 
        }
        GROUP BY ?class
    }
    BIND( IRI( CONCAT( '""" + context + """/void/class_partition_', MD5( STR( ?class )))) AS ?cp )
}
;
INSERT{
    GRAPH <""" + context + """> {
        ?cps void:propertyPartition ?pp .
        ?pp void:property       ?prop  ;
            void:triples        ?count ;  
            void:classPartition ?cpo   .
    }
}
WHERE{
     { 
        SELECT ?c_s ?prop ?c_o ( COUNT( * ) AS ?count )
        WHERE{ 
            ?s ?prop ?o .
            ?s a ?c_s .
            ?o a ?c_o .
            FILTER( ?prop != rdf:type )
     	}
     	GROUP BY ?prop ?c_s ?c_o
    }
    BIND( IRI( CONCAT( '""" + context + """/void/class_partition_',    MD5( STR( ?c_s ))))  AS ?cps )
    BIND( IRI( CONCAT( '""" + context + """/void/class_partition_',    MD5( STR( ?c_o ))))  AS ?cpo )
    BIND( IRI( CONCAT( '""" + context + """/void/property_partition_', MD5( STR( ?prop )))) AS ?pp )
}
;
INSERT{
    GRAPH <""" + context + """> {
        ?cps void:propertyPartition ?pp .
        ?pp void:property       ?prop  ;
            void:triples        ?count ;  
            void-ext:datatypePartition ?dtp .
        ?dtp void-ext:datatype ?dt .
    }
}
WHERE{
     { 
        SELECT ?c_s ?prop ?dt ( COUNT( * ) AS ?count )
        WHERE{ 
            ?s ?prop ?o .
            ?s a ?c_s .
            FILTER( isLITERAL( ?o ))
            FILTER( ?prop != rdf:type )
            BIND( DATATYPE( ?o ) AS ?dt )
     	} 
     	GROUP BY ?prop ?c_s ?dt
    }
    BIND( IRI( CONCAT( '""" + context + """/void/class_partition_',    MD5( STR( ?c_s ))))  AS ?cps )
    BIND( IRI( CONCAT( '""" + context + """/void/datatype_partition_', MD5( STR( ?dt ))))   AS ?dtp )
    BIND( IRI( CONCAT( '""" + context + """/void/property_partition_', MD5( STR( ?prop )))) AS ?pp )
}"""

def make_prefix_description( context, filenames ):
    prefix = {}
    for filename in filenames :
        report( "parse file", filename )    
        file = open( replace_env_var( filename ))
        for line in file:
            match = catch_key_value_ttl.search( line )
            if match:
                if match.group( 1 ) in prefix:
                    print_warn( "Duplicate prefix: " + match.group( 1 ))
                else:
                    prefix[ match.group( 1 ) ] = match.group( 2 )
    iris = []
    ttl  = []
    prefix_IRI = context + "/prefix"
    for key in sorted( prefix.keys()):
        iri = prefix_IRI + "/" + key
        iris.append( f"<{iri}>" ) 
        ttl.append( f"<{iri}> sh:prefix '{key}' ; sh:namespace \"{prefix[key]}\"^^xsd:anyURI ." )
    
    # here one makes chunks not too have a long SPARQL statements
    sparql =[]
    for i in range(0, len( iris ), 10 ):
        sparql.append( f"""PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
INSERT DATA{{ 
    GRAPH <{context}> {{ 
        <{prefix_IRI}> sh:declare
            """ + " ,\n            ".join( iris[i:i+10] ) + f""" .
    }}
}}""" )
        sparql.append( f"""PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
INSERT DATA{{ 
    GRAPH <{context}> {{ 
        """ + "\n        ".join( ttl[i:i+10] ) + f"""
    }}
}}""" )
    return sparql

def escape_sparql_long_string( text ):
    """Escape text for safe embedding in a SPARQL long-string literal (\"\"\"...\"\"\").

    The query/comment text is pasted into an INSERT DATA statement that the
    target store parses; without escaping, a backslash inside the literal is
    treated as an escape introducer, so an authored "\\\\" is decoded back to
    "\\". Escape backslash first (so we do not double-escape our own additions),
    then double-quotes (to prevent an accidental \"\"\" or trailing-quote from
    terminating the literal early).
    """
    return text.replace( "\\", "\\\\" ).replace( '"', '\\"' )

def make_query_description( context, filenames, endpoint = None ):
    sparql = []
    seen = {}
    for filename in filenames:
        report( "read query", filename )
        name     = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
        name     = re.sub( r"\W", "_", name )
        if name in seen:
            stop_error( "Duplicated query name: " + name)
        else:
            seen[name] = True
        with open( filename ) as file:
            text = file.read()
        # grlc parser path: activated when the file starts with a '#+' decorator.
        # The grlc parser turns the '#+' YAML block into valid RDF; the uploaded
        # query (sh:select) keeps its '#'/'#+' comment lines (query as authored).
        first = next(( ln for ln in text.splitlines() if ln.strip() != "" ), "" )
        if first.startswith( "#+" ):
            g = grlc.build_graph(
                text, name, grlc.parse_decorators( text ),
                endpoint = endpoint, form = grlc.detect_form( text )
            )
            sparql.append(
                "INSERT DATA {\n    GRAPH <" + context + "> {\n"
                + g.serialize( format = "nt" ) + "    }\n}"
            )
            continue
        # ---- legacy behaviour (preserved): '#+' lines are Turtle, '#' the comment ----
        comment  = []
        query    = [] # i.e. the SPARQL query itself
        more_ttl = []
        for line in text.splitlines():
            if re.match( r"^#\+", line ):
                l = re.sub( r"^#\+", "", line.rstrip() )
                more_ttl.append( l )
            elif re.match( r"^#", line ):
                comment.append( re.sub( r"^#\s*", "", line.rstrip() ))
            else:
                query.append( line.rstrip().replace( "\t", "    "))
        iri = "http://rdf.example.org/queryform/" + name
        sparql.append( """PREFIX sh: <http://www.w3.org/ns/shacl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
INSERT DATA{
    GRAPH <""" + context + """> { 
        <""" + iri + """> a sh:SPARQLExecutable, sh:SPARQLSelectExecutable ;
            rdfs:label \"""" + name.replace( "_", " " ) + """\" ;
            rdfs:comment \"\"\"""" + escape_sparql_long_string( "\n".join( comment )) + """\"\"\" ;
            sh:select \"\"\"""" + escape_sparql_long_string( "\n".join( query )) + """\"\"\" .
    }
}""" )
        if more_ttl:
            prefix = []
            triple = []
            for line in more_ttl:
                # print_warn( line )
                match = catch_key_value_rq.search( line )
                if match:
                    prefix.append( "PREFIX " + match.group( 1 ) + ": <" + match.group( 2 ) + ">" )
                else:
                    triple.append( line.replace( "$this", "<" + iri + ">" ))
            sparql.append( "\n".join( prefix ) + """
INSERT DATA {
    GRAPH <""" + context + """> {
    """ + "\n".join( triple ) + """
    }
}""" )
    return sparql

def write_dependency_graph( config, filename ):
    """Write an interactive dataset dependency graph as an HTML file.

    Uses Vis.js Network (loaded from CDN) to render a hierarchical,
    interactive graph. No external binaries or Python packages required.
    The output file is self-contained (open in any browser).

    Each node shows the dataset name and triple count.
    Directed edges go from parent to child.

    Args:
        config:   The parsed kgsteward config dict (after update_config).
        filename: Output HTML file path (should end with '.html').
    """
    import json

    if not filename.endswith( ".html" ):
        filename = filename + ".html"

    datasets  = config["dataset"]
    name2item = { item["name"]: item for item in datasets }

    # ---- compute depth ----
    depth_cache = {}
    def get_depth( name ):
        if name in depth_cache:
            return depth_cache[name]
        item = name2item[name]
        if "parent" not in item or not item["parent"]:
            depth_cache[name] = 0
        else:
            depth_cache[name] = max( get_depth(p) for p in item["parent"] ) + 1
        return depth_cache[name]

    for item in datasets:
        get_depth( item["name"] )

    # ---- build Vis.js nodes and edges ----
    nodes = []
    edges = []

    # input  nodes: no parents  → bold, dark, prominent
    INPUT_COLOR   = { "background": "#1a5276", "border": "#0e2f44",
                      "highlight":  { "background": "#21618c", "border": "#0e2f44" } }
    INPUT_FONT    = { "size": 15, "color": "#ffffff", "face": "Helvetica, Arial, sans-serif",
                      "bold": { "color": "#ffffff" } }

    # derived nodes: have parents → light, muted, secondary
    DERIVED_COLOR = { "background": "#d6eaf8", "border": "#a9cce3",
                      "highlight":  { "background": "#aed6f1", "border": "#7fb3d3" } }
    DERIVED_FONT  = { "size": 12, "color": "#555555", "face": "Helvetica, Arial, sans-serif" }

    for item in datasets:
        name    = item["name"]
        count   = item.get( "count", "" )
        depth   = depth_cache[name]
        is_root = depth == 0

        label   = f"{name}\n{count} triples" if count else name
        node    = {
            "id":    name,
            "label": label,
            "level": depth,
            "color": INPUT_COLOR   if is_root else DERIVED_COLOR,
            "font":  INPUT_FONT    if is_root else DERIVED_FONT,
            "borderWidth": 2       if is_root else 1,
            "shadow": is_root,
        }
        nodes.append( node )

        for parent in item.get( "parent", [] ) or []:
            has_update = bool( item.get( "update" ) )
            edge = {
                "from":   parent,
                "to":     name,
                "arrows": "to",
                # solid arrow = child has a SPARQL update transforming the data
                # dashed arrow = pure dependency, no update statement
                "dashes": not has_update,
                "color":  { "color": "#888888", "highlight": "#336699" },
                "width":  2 if has_update else 1.5,
            }
            edges.append( edge )

    nodes_json = json.dumps( nodes, indent=2 )
    edges_json = json.dumps( edges, indent=2 )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>kgsteward dependency graph</title>
  <script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
  <style>
    body  {{ margin: 0; font-family: Helvetica, Arial, sans-serif; background: #f8f9fa; }}
    h1    {{ text-align: center; padding: 12px 0 4px; font-size: 1.1em; color: #336699; }}
    #graph {{ width: 100%; height: calc(100vh - 56px); border: none; }}
  </style>
</head>
<body>
  <h1>kgsteward &mdash; dataset dependency graph</h1>
  <div id="graph"></div>
  <script>
    const nodes = new vis.DataSet({nodes_json});
    const edges = new vis.DataSet({edges_json});
    const options = {{
      layout: {{
        hierarchical: {{
          direction:           "LR",
          sortMethod:          "directed",
          levelSeparation:     260,
          nodeSpacing:         120,
          treeSpacing:         200,
          blockShifting:       true,
          edgeMinimization:    true,
          parentCentralization: true
        }}
      }},
      nodes: {{
        shape:  "box",
        margin: 10
      }},
      edges: {{
        smooth: {{ type: "cubicBezier", forceDirection: "horizontal" }},
        arrows: {{ to: {{ scaleFactor: 0.7 }} }}
      }},
      physics:     {{ enabled: false }},
      interaction: {{ hover: true, navigationButtons: true, keyboard: true }}
    }};
    new vis.Network(
      document.getElementById("graph"),
      {{ nodes, edges }},
      options
    );
  </script>
</body>
</html>
"""

    with open( filename, "w", encoding="utf-8" ) as f:
        f.write( html )
    report( "write file", filename )



