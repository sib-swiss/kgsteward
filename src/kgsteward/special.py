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
    """Write a dataset dependency graph as an SVG file using pure Python.

    No external binaries are required. Datasets are laid out left-to-right
    by depth (roots on the left, derived datasets to the right). Each node
    shows the dataset name and its triple count (from the server). Directed
    edges go from parent to child.

    Args:
        config:   The parsed kgsteward config dict (after update_config).
        server:   A live triplestore client (used to retrieve triple counts).
        filename: Output SVG file path (should end with '.svg').
    """
    from collections import defaultdict
    import xml.sax.saxutils as saxutils

    if not filename.endswith( ".svg" ):
        filename = filename + ".svg"

    datasets  = config["dataset"]
    name2item = { item["name"]: item for item in datasets }

    # ---- compute node depth (roots = 0, children = parent_depth + 1) ----
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

    max_depth = max( depth_cache.values() ) if depth_cache else 0

    # ---- group nodes by column ----
    columns = defaultdict( list )
    for item in datasets:
        columns[ depth_cache[ item["name"] ] ].append( item["name"] )

    # ---- layout constants ----
    NODE_W  = 190
    NODE_H  = 52
    H_GAP   = 80
    V_GAP   = 28
    MARGIN  = 40
    FONT    = "Helvetica, Arial, sans-serif"

    # ---- compute centre positions ----
    pos = {}
    for col_idx in range( max_depth + 1 ):
        nodes = columns[col_idx]
        cx    = MARGIN + col_idx * (NODE_W + H_GAP) + NODE_W // 2
        total = len(nodes) * NODE_H + max(0, len(nodes) - 1) * V_GAP
        start = MARGIN + NODE_H // 2
        for row_idx, name in enumerate( nodes ):
            cy = start + row_idx * (NODE_H + V_GAP)
            pos[name] = (cx, cy)

    max_col  = max( len(v) for v in columns.values() ) if columns else 1
    svg_w = MARGIN + (max_depth + 1) * (NODE_W + H_GAP) - H_GAP + MARGIN
    svg_h = MARGIN + max_col * NODE_H + max(0, max_col - 1) * V_GAP + MARGIN

    # ---- build SVG ----
    lines = []
    lines.append( '<?xml version="1.0" encoding="UTF-8"?>' )
    lines.append( f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{svg_h}">' )
    lines.append( '  <defs>' )
    lines.append( '    <marker id="arrow" markerWidth="10" markerHeight="7"' )
    lines.append( '            refX="10" refY="3.5" orient="auto">' )
    lines.append( '      <polygon points="0 0,10 3.5,0 7" fill="#336699"/>' )
    lines.append( '    </marker>' )
    lines.append( '  </defs>' )
    lines.append( f'  <rect width="{svg_w}" height="{svg_h}" fill="white"/>' )

    # edges: parent → child (left to right)
    for item in datasets:
        child = item["name"]
        cx, cy = pos[child]
        if "parent" in item:
            for parent in item["parent"]:
                px, py = pos[parent]
                x1 = px + NODE_W // 2   # right edge of parent box
                x2 = cx - NODE_W // 2   # left  edge of child  box
                lines.append(
                    f'  <line x1="{x1}" y1="{py}" x2="{x2}" y2="{cy}"'
                    f' stroke="#336699" stroke-width="1.5"'
                    f' marker-end="url(#arrow)"/>'
                )

    # nodes
    for item in datasets:
        name  = item["name"]
        count = item.get( "count", "" )
        cx, cy = pos[name]
        x = cx - NODE_W // 2
        y = cy - NODE_H // 2
        safe_name = saxutils.escape( name )
        lines.append(
            f'  <rect x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}"'
            f' rx="6" ry="6" fill="#d6eaf8" stroke="#336699" stroke-width="1.5"/>'
        )
        if count:
            lines.append(
                f'  <text x="{cx}" y="{cy - 6}" text-anchor="middle"'
                f' font-family="{FONT}" font-size="13" font-weight="bold">{safe_name}</text>'
            )
            lines.append(
                f'  <text x="{cx}" y="{cy + 13}" text-anchor="middle"'
                f' font-family="{FONT}" font-size="11" fill="#555">{count} triples</text>'
            )
        else:
            lines.append(
                f'  <text x="{cx}" y="{cy + 5}" text-anchor="middle"'
                f' font-family="{FONT}" font-size="13" font-weight="bold">{safe_name}</text>'
            )

    lines.append( '</svg>' )

    with open( filename, "w", encoding="utf-8" ) as f:
        f.write( "\n".join( lines ) + "\n" )
    report( "write file", filename )

