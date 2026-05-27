from dumper import dump
import configparser
import os
import re
import rdflib
import urllib

from .common import *
from .generic import GenericClient

# RDF formats and compression schemes that qlever can read natively (no riot needed)
QLEVER_NATIVE_FORMATS      = { ".nt", ".ttl", ".nq", ".trig" }
QLEVER_NATIVE_COMPRESSIONS = { "", ".gz" }

def _is_qlever_native( filename ):
    """Return True if qlever can read the file directly without riot conversion."""
    name = filename.lower()
    for comp in QLEVER_NATIVE_COMPRESSIONS:
        if comp and name.endswith( comp ):
            name = name[ :-len( comp ) ]
            break
    _, ext = os.path.splitext( name )
    return ext in QLEVER_NATIVE_FORMATS

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

        # Check that riot (Apache Jena) is installed and on PATH
        if shutil.which( "riot" ) is None:
            stop_error( "riot not found. Please install Apache Jena and make sure riot is on PATH." )

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
        self.qleverfile  = qleverfile
        self.qleverdir   = qleverdir
        self.qlever_cmd  = ["qlever"]  # prefix for all future qlever CLI calls

        # Probe the server: it may legitimately be stopped (e.g. before qlever index).
        # Record the state; do NOT treat a stopped server as a fatal error here.
        try:
            http_call( { 'method': 'GET', 'url': location }, [ 404 ], echo = echo )
            self.is_running = True
        except:
            self.is_running = False
        report( "qlever server", "running" if self.is_running else "stopped" )

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def server_start( self, echo = True ):
        """Start the qlever server (runs 'qlever start' in qleverdir)."""
        r = run_system_cmd( self.qlever_cmd + ["start"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever start failed" )
        self.is_running = True

    def server_stop( self, echo = True ):
        """Stop the qlever server (runs 'qlever stop' in qleverdir)."""
        r = run_system_cmd( self.qlever_cmd + ["stop"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever stop failed" )
        self.is_running = False

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #

    def stage_for_index( self, files, echo = True ):
        """Stage RDF files into qleverdir/input/ for qlever index.

        Files already in a natively supported format+compression are symlinked
        (zero copy cost). All others are converted to .nt.gz via riot.

        Returns a list of paths relative to qleverdir, suitable for
        INPUT_FILES in the Qleverfile [index] section.
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        os.makedirs( input_dir, exist_ok = True )
        staged = []
        for src in files:
            src = os.path.abspath( src )
            basename = os.path.basename( src )
            if _is_qlever_native( src ):
                # Symlink: no data duplication
                link = os.path.join( input_dir, basename )
                if os.path.lexists( link ):
                    os.remove( link )
                os.symlink( src, link )
                report( "symlink", link, echo )
                staged.append( os.path.join( "input", basename ))
            else:
                # Convert to .nt.gz via riot (handles any RDF format)
                stem = re.sub( r"\.(gz|bz2|xz)$", "", basename, flags = re.IGNORECASE )
                stem = os.path.splitext( stem )[0]
                out_name = stem + ".nt.gz"
                out_path = os.path.join( input_dir, out_name )
                report( "riot→nt.gz", f"{src} → {out_path}" )
                if echo:
                    print( colored( f"riot --output=ntriples {src} | gzip > {out_path}", "cyan" ), flush = True )
                riot = subprocess.Popen( ["riot", "--output=ntriples", src], stdout = subprocess.PIPE )
                with gzip.open( out_path, "wb" ) as gz_out:
                    shutil.copyfileobj( riot.stdout, gz_out )
                riot.wait()
                if riot.returncode != 0:
                    stop_error( f"riot conversion failed for: {src}" )
                staged.append( os.path.join( "input", out_name ))
        return staged

    def _patch_input_files( self, staged_files ):
        """Overwrite INPUT_FILES in the [index] section of the Qleverfile."""
        real_path = os.path.realpath( self.qleverfile )
        parser = configparser.ConfigParser()
        parser.read( real_path )
        if "index" not in parser:
            parser["index"] = {}
        parser["index"]["INPUT_FILES"] = " ".join( staged_files )
        with open( real_path, "w" ) as f:
            parser.write( f )
        report( "INPUT_FILES", " ".join( staged_files ))

    def rewrite_repository( self, files = None, echo = True ):
        """Re-index qlever from scratch.

        Steps:
          1. Wipe qleverdir/input/ (previous staged files)
          2. Stage all files (symlinks for native formats, riot→nt.gz otherwise)
          3. Patch [index] INPUT_FILES in the Qleverfile
          4. Stop the server if currently running
          5. qlever index
          6. Start the server
          7. Remove converted copies; keep symlinks (they are cheap)
        """
        if not files:
            print_warn( "rewrite_repository called with no files — nothing to index." )
            return

        # 1. Clean up previous staged input
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )

        # 2. Stage
        print_task( "Stage RDF files for qlever index" )
        staged = self.stage_for_index( files, echo = echo )

        # 3. Patch Qleverfile
        print_task( "Patch Qleverfile INPUT_FILES" )
        self._patch_input_files( staged )

        # 4. Stop server
        if self.is_running:
            print_task( "Stop qlever server before indexing" )
            self.server_stop( echo = echo )

        # 5. Index
        print_task( "Run qlever index" )
        r = run_system_cmd( self.qlever_cmd + ["index"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever index failed" )

        # 6. Start server
        print_task( "Start qlever server" )
        self.server_start( echo = echo )

        # 7. Remove converted copies (symlinks are kept — they cost nothing)
        for fname in os.listdir( input_dir ):
            full = os.path.join( input_dir, fname )
            if not os.path.islink( full ):
                os.remove( full )
                report( "cleanup", full )

    # ------------------------------------------------------------------ #
    # SPARQL
    # ------------------------------------------------------------------ #

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
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_query,
                'headers' : headers,
                'data'  : params,
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
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.sparql_update() is not available" )

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        stop_error( "Qlever server is supported read-only: QleverConf.drop_context() is not available" )
