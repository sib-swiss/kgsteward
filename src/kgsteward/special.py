import re
from .common import *

catch_key_value_ttl = re.compile( r"@prefix\s+(\S*):\s+<([^>]+)>", re.IGNORECASE )
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
    for filename in filenames :
        report( "parse file", filename )
        prefix = {}
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
    counter = 0
    query_IRI = context + "/query"
    sparql = []
    prefix = {}
    for filename in filenames:
        report( "read query", filename )
        counter = counter + 1
        comment = []
        select  = [] # i.e. the SPARQL query itself
        name    = re.sub( r'(.*/|)([^/]+)\.\w+$', r'\2', filename )
        with open( filename ) as file:
            for line in file:
                if re.match( "^#", line ):
                    comment.append( re.sub( r"^#\s*", "", line.rstrip() ))
                else:
                    select.append( line.rstrip().replace( "\t", "    "))
                    match = catch_key_value_rq.search( line )
                    if match:
                        prefix[match.group( 1 )] = match.group( 2 )
        iri = query_IRI + "/" + str( counter ).rjust( 4, '0' )
        com = "<b>" + name.replace( "_", " ") + "</b>\n<br>\n" + "\n".join( comment )
        sparql.append( """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sh:   <http://www.w3.org/ns/shacl#>
                      
INSERT DATA{
    GRAPH <""" + context + """> { 
        <""" + iri + """> a sh:SPARQLExecutable, sh:SPARQLSelectExecutable ;
            rdfs:label '""" + name.replace( "_", " ") + """' ;
            rdfs:comment \"\"\"""" + com + """\"\"\" ;
            sh:select \"\"\"""" + "\n".join( select ) + "\n" + """\"\"\" ;
    }
}""" )
    return sparql
