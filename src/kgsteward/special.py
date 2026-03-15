import re
from .common import *

# Unsolved problem catch_key_value_rq is a particular case of catch_key_value_ttl
catch_key_value_ttl = re.compile( r"\@prefix\s+(\S*):\s+<([^>]+)>\s*\.", re.IGNORECASE )
catch_key_value_rq  = re.compile( r"PREFIX\s+(\S*):\s+<([^>]+)>",  re.IGNORECASE )

def make_void_description( context ):
    return """PREFIX void:     <http://rdfs.org/ns/void#>
PREFIX void-ext: <http://ldf.fi/void-ext#>

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

def make_query_description( context, filenames ):
    sparql = []
    seen = {}
    for filename in filenames:
        report( "read query", filename )
        comment  = []
        query    = [] # i.e. the SPARQL query itself
        more_ttl = []
        name     = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
        name     = re.sub( r"\W", "_", name )
        if name in seen:
            stop_error( "Duplicated query name: " + name)
        else:
            seen[name] = True
        with open( filename ) as file:
            for line in file:
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
            rdfs:comment \"\"\"""" + "\n".join( comment ) + """\"\"\" ;
            sh:select \"\"\"""" + "\n".join( query ) + """\"\"\" .            
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

def write_dependency_graph( config, server, filename ):
    """Write an interactive dataset dependency graph as an HTML file.

    Uses Vis.js Network (loaded from CDN) to render a hierarchical,
    interactive graph. No external binaries or Python packages required.
    The output file is self-contained (open in any browser).

    Each node shows the dataset name and triple count (from the server).
    Directed edges go from parent to child.

    Args:
        config:   The parsed kgsteward config dict (after update_config).
        server:   A live triplestore client (used to retrieve triple counts).
        filename: Output HTML file path (should end with '.html').
    """
    import json

    if not filename.endswith( ".html" ):
        filename = filename + ".html"

    datasets = config["dataset"]

    # ---- build Vis.js nodes and edges ----
    nodes = []
    edges = []
    for item in datasets:
        name  = item["name"]
        count = item.get( "count", "" )
        label = f"{name}\n{count} triples" if count else name
        nodes.append({ "id": name, "label": label })
        for parent in item.get( "parent", [] ) or []:
            edges.append({ "from": parent, "to": name, "arrows": "to" })

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
          direction:        "LR",
          sortMethod:       "directed",
          levelSeparation:  220,
          nodeSpacing:      100
        }}
      }},
      nodes: {{
        shape:     "box",
        margin:    10,
        font:      {{ size: 14, face: "Helvetica, Arial, sans-serif", multi: true }},
        color:     {{ background: "#d6eaf8", border: "#336699",
                     highlight:  {{ background: "#aed6f1", border: "#1a5276" }} }},
        borderWidth: 2,
        shadow:    true
      }},
      edges: {{
        color:  {{ color: "#336699", highlight: "#1a5276" }},
        width:  2,
        smooth: {{ type: "cubicBezier", forceDirection: "horizontal" }},
        arrows: {{ to: {{ scaleFactor: 0.8 }} }}
      }},
      physics: {{ enabled: false }},
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


