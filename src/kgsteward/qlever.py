from dumper import dump
import configparser
import os
import re
import rdflib
import urllib

from .common import *
from .generic import GenericClient

def parse_qleverfile( qleverfile ):
    """Read a Qleverfile (following symlinks) and return (location, repository, system).

    The Qleverfile is an INI-style file with at minimum:
      [data]
      NAME      = <dataset-name>     # used as the repository identifier
      [server]
      HOST_NAME = localhost           # optional, defaults to localhost
      PORT      = 7019               # optional, defaults to 7019
      [runtime]
      SYSTEM    = docker             # optional, one of docker | podman | native; defaults to docker
    """
    real_path = os.path.realpath( qleverfile )
    if not os.path.isfile( real_path ):
        stop_error( "Qleverfile not found: " + qleverfile )
    parser = configparser.ConfigParser()
    parser.read( real_path )
    if "data" not in parser or "NAME" not in parser["data"]:
        stop_error( "Missing [data] NAME in Qleverfile: " + real_path )
    repository = parser["data"]["NAME"]
    host   = parser.get( "server",  "HOST_NAME", fallback = "localhost" )
    port   = parser.get( "server",  "PORT",      fallback = "7019" )
    system = parser.get( "runtime", "SYSTEM",    fallback = "docker" )
    location = f"http://{host}:{port}"
    return location, repository, system

class QleverClient( GenericClient ):

    def __init__( self, qleverfile, qleverdir, echo = True ):

        # Check that the qlever CLI tool is installed and on PATH
        if shutil.which( "qlever" ) is None:
            stop_error( "qlever CLI not found. Please install it with: uv tool install qlever" )

        # Derive location, repository and container system from Qleverfile
        location, repository, system = parse_qleverfile( qleverfile )

        # Check the container runtime required by the Qleverfile
        if system in ( "docker", "podman" ):
            if run_system_cmd( [system, "info"], echo = echo, capture_output=True ).returncode != 0:
                stop_error( f"{system} daemon is not running. Please start it before using qlever." )
        elif system != "native":
            stop_error( f"Unknown [runtime] SYSTEM in Qleverfile: '{system}'. Expected docker, podman or native." )

        super().__init__( location, None, None )
        self.repository  = repository  # qlever has no repository concept; this is used as a label
        self.qleverdir   = qleverdir
        self.qlever_cmd  = ["qlever"]  # prefix for all future qlever CLI calls

        try:
            r = http_call({
                'method'  : 'GET', # not supported by qlever, but returns 404
                'url'     : location
                }, [ 404 ], echo = echo )
        except:
            stop_error( "Cannot contact qlever at location: " + location )

    def get_endpoint_update( self ):
        return ""

    def list_repository( self ):
        return [ self.repository ]

    def sparql_query( self, sparql, status_code_ok = [ 200, 400, 500 ], echo = True, timeout = None ):
        if echo :
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept' : 'application/json', 
            'Content-Type': 'application/x-www-form-urlencoded' 
        }
        params = { 'query' : sparql }
#        if timeout is not None:
#            if not 503 in status_code_ok: # returned by "normal" GraphDB timeout
#                status_code_ok.append( 503 ) 
#            if not 500 in status_code_ok: # returned by "service" GraphDB timeout
#                status_code_ok.append( 500 )
#            params["timeout"] = timeout
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_query,
                'headers' : headers,
                'data'  : params,
                # 'timeout' : 2 # timeout  # this timeout on the Python request client side unfortunately
            },
            status_code_ok,
            echo
        )
        # qlever may return 500 for execution errors  
        if r.status_code in [ 400, 500 ] and r.text :
            print_warn( r.text )
            return None
        if r.status_code != 200:
            dump( r )
            stop_error( "Unknown error" )
#        if timeout is not None:
#            if r.status_code == 503 :
#                time.sleep( 1 )
#                print_warn( "query timed out" )
#                return None
#            elif r.status_code == 500 : # is returned by GraphDB on timeout of SPARQL queries with a SERVICE clause ?!?
#                time.sleep( 1 )
#                print_warn( "unknown error, possibly timeout" )
#                return None
        return r
    
    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.sparql_update() is not available" )
        # the code below works with INSERT WHERE clause, but not with LOAD INTO ;-()
        if self.access_token is None:
            raise Exception( "Missing access token: QleverConf.sparql_update()" )
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept' : 'application/qlever-results+json', 
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Bearer ' + self.access_token
        }
        params = { 'update' : sparql }
        r = http_call(
            {
                'method'  : 'POST',  # allows for big query string
                'url'     : self.endpoint_update,
                'headers' : headers,
                'data'    : params,
                # 'cookies' : self.cookies
            },
            status_code_ok,
        )
        return r
        # raise Exception( "Not yet implemented: QleverConf.sparql_update()" )

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.drop_context() is not available" )
        # the code below is nevertheless working
        self.sparql_update( f"DROP GRAPH <{context}>", echo = echo )
