# https://vos.openlinksw.com/owiki/wiki/VOS/VOSVirtSparqlProtocol
# https://vos.openlinksw.com/owiki/wiki/VOS/VirtOAuthSPARQL

from dumper import dump
import re
import hashlib
import os
from bs4 import BeautifulSoup
from .common import *
from .generic import GenericClient
from .fileserver import LocalFileServer

class VirtuosoClient( GenericClient ):

    def __init__( self, virtuoso_url = "http://localhost:8890", username = "dba", password = "dba", file_server_port = 8000 ):
        super().__init__(  
            virtuoso_url + "/sparql", 
            virtuoso_url + "/conductor/isql.vspx",
            "" # virtuoso_url + "/sparql-graph-crud-auth/"
        )
        self.virtuoso_url = virtuoso_url
        self.file_server_port = file_server_port
        self.fs = fs = LocalFileServer( port = file_server_port )
        r = http_call(
            {
                'method'  : 'GET',
                'url'     :  virtuoso_url + "/conductor/main_tabs.vspx"
            }
        )
        soup = BeautifulSoup( r.content.decode('utf-8') , features="html.parser" )
        field = { e['name']: e.get( 'value', '' ) for e in soup.find_all( 'input', { 'name': True})}
        field['username'] = 'dba'
        str = field['nonce'] + 'dba'                                      # emulate javascript effect 
        field['password'] = hashlib.md5( str.encode('utf-8')).hexdigest() # contd.
        print( field )
        r = http_call(
            {
                'method'  : 'GET',
                'url'     :  virtuoso_url + "/conductor/main_tabs.vspx",
                'data'    : field
            }
        )
        if re.search( "realm", r.content.decode('utf-8')):
            print( r.content.decode('utf-8'))
        else:
            print( "ko" )
        #print( r.status_code )
        #print( r.cookies )

        #soup = BeautifulSoup( r.content.decode('utf-8') , features="html.parser" )
        #field = { e['name']: e.get( 'value', '' ) for e in soup.find_all( 'input', { 'name': True})}
        #print( field )
        stop_error( "toto" )


    def ping( self, echo = True ):
        """ test if the server is responding """
#        print( "toto" )
        sparql = "SELECT * WHERE{ ?s ?p ?o } LIMIT 1"
#        if echo :
#            print( sparql, flush = True )
        r = self.sparql_query( sparql, echo = echo )

    def sparql_query( self, sparql, status_code_ok = [ 200 ], echo = True ) :
        if echo :
            print( colored( sparql, "green" ), flush = True )
        r = http_call(
            {
                'method'  : 'GET',
                'url'     : self.endpoint_query,
                # 'headers' : { 'Accept' : accept },
                'params'  : { 
                    'sid'   : self.sid,
                    'query' : sparql,
                    'format': 'application/sparql-results+json' 
                }
            },
            status_code_ok,
            echo = echo
        )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ) :
        if echo :
            print( colored( sparql, "green" ), flush = True )
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_update,
                'params'  : {
                    'sid'      : self.sid,
                    'realm'    : "virtuoso_admin",
                    'sql_text' : "SPARQL " + sparql,
                }
            },
            status_code_ok,
            echo = echo
        )
        dump( r  )
        return r

    def get_contexts( self, echo = True ) :
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g { ?s ?p ?o } }", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"] : 
            contexts.add( rec["g"]["value"] )
        return contexts

    def rewrite_repository( self, graphdb_config_filename ) :
        print_warn( "Not yet implemented: FusekiClient.rewrite_repository()" )

    def free_access( self ) :
        print_warn( "Not yet implemented: FusekiClient.free_access()" );

#    def sparql_query( self, sparql, accept='application/json', status_code_ok = [ 200 ], echo = True ) :
#        if echo :
#            print( sparql, flush=True )
#        r = http_call({
#            'method'  : 'GET',
#            'url'     : self.fuseki_url + "/" + self.repository_id + "/sparql",
#            'params'  : { 'query': sparql }
#        }, status_code_ok, echo )
#        return r
    
    def sparql_query_to_tsv( self, sparql, status_code_ok = [200], echo=True) :
        return self.sparql_query(
            sparql,
            accept='text/tab-separated-values',
            status_code_ok=status_code_ok,
            echo=echo,
        )
        
    def graphdb_call( self, request_args, status_code_ok = [ 200 ], echo = True ) :
        print_warn( "Not yet implemented: FusekiClient.graphdb_call()" )

    def validate_sparql_query( self, sparql, echo = False ):
        print_warn( "Not yet implemented: FusekiClient.validate_sparql_query ()" )
        r = http_call({
            'method'  : 'GET',
            'url'     : self.graphdb_url + "/repositories/" + self.repository_id,
            'headers' : {
                'Accept'        : 'text/tab-separated-values',
                'Authorization' : self.authorization
            },
            'params'  : {
                'query'   : sparql,
                "infer"   : True,
                "timeout" : 5       # 5 seems to solve a HTTP "problem" observed with a timout of 1 s ?!?
            }
        }, [ 503, 500, 400, 200 ], echo )
        if r.status_code == 503 :
            time.sleep( 1 )
            print( "\t" + "query timed out" )
        elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
            time.sleep( 1 )
            print( "\t" + "unknown error, maybe timeout" )
        elif r.status_code == 400 :
            raise RuntimeError( "Suspected SPARQL syntax error:\n" + sparql )
        else : #  r.status_code == 200 :
            n = r.text.count( "\n" )
            if n == 0 :
                print( "\t" + "!!! empty results !!!" )
            else :
                print( "\t" + str( n ) + " lines returned" )

    def load_from_url( self, url, context, tmpdir = "/tmp", echo = True ):
        if re.search( r"\.ttl$", url ):
            self.sparql_update( f"LOAD SILENT <{url}> INTO GRAPH <{context}>", echo = echo )
        elif re.search( r"\.(gz|bz2|xz)$", url  ):
            filename = tmpdir + "/" + url.split('/')[-1]
            if echo:
                report( 'write file', filename )
            download_file( url, filename )
            self.load_from_file( filename, context, echo = echo )
        else:
            stop_error( "Cannot handle this type of link with Fuseki: " + url )

    def load_from_file( self, file, context, echo = True ):
        """ use graph store protocol """
        if echo:
            report( 'load file', file )
        dir, file = os.path.split( file )
        self.fs.expose( dir  )
        path = "http://localhost:" + str( self.file_server_port ) + "/" + file
        self.sparql_update( f"LOAD <{path}> INTO GRAPH <{context}>" )
